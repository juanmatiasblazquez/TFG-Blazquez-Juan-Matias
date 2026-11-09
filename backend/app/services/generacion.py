"""ServicioGeneracion (diagrama del motor, p. 47; secuencias de las pp. 43 y 44): del proyecto
guardado a una versión nueva, pasando por el motor (D30, D56).

    proyecto y parámetros vigentes → armar_solicitud (a metros) → MotorGeneracion.generar
        → registrar_version (a 4326, una transacción) → alternativa con su versión 1

    versión de origen → armar_fijados (lo que se conserva) → MotorGeneracion.recalcular
        → registrar_recalculo → la versión n + 1 de la misma alternativa

    versión elegida → copiar_version → la versión n + 1, copia de la elegida (volver a ella, D60)

Cada generación crea una alternativa NUEVA (A, B, C…) con su versión 1; la versión n + 1 de una
alternativa sale del recálculo (CU09) o de volver a una versión anterior. Nada se pisa: la base
rechaza modificar una versión (RNF04, migración 0002), y lo que se conserva se copia en filas nuevas.

Cada versión guarda la copia de las áreas reservadas con las que se generó (D59): las del proyecto al
generar y las de la versión de origen al recalcular o copiar.
"""

import time
from collections import defaultdict
from decimal import Decimal

import motor_trazados as mt
from geoalchemy2.shape import to_shape
from motor_trazados import coordenadas
from motor_trazados.exportar import geojson_geografico
from motor_trazados.geometria import TOLERANCIA, poligonos
from shapely import MultiPolygon, Point, Polygon, hausdorff_distance
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorApi
from app.models import (
    Alternativa,
    AreaReservadaVersion,
    Celda,
    ConjuntoParametros,
    Incumplimiento,
    Manzana,
    NodoRed,
    Proyecto,
    Terreno,
    TramoCirculacion,
    Usuario,
    VersionAlternativa,
)
from app.models.alternativa import EstadoAlternativa, TipoVersion
from app.models.observacion import de_la_alternativa, designaciones
from app.schemas.alternativa import (
    AlternativaOut,
    CapasOut,
    EstrategiaIn,
    EstrategiaOut,
    FijacionOut,
    IndicadoresOut,
    VersionOut,
)
from app.schemas.recalculo import RecalculoIn
from app.services import fijacion, proyectos, verificaciones
from app.services.conversiones import centesimos, coleccion, feature, geojson, guardable, numero
from app.services.solicitud import areas_de_version, armar_solicitud

# Para lo que el motor declara «todavía no implementado» sin una sugerencia propia.
SUGERENCIA_NO_IMPLEMENTADO = "Es una función prevista que todavía no está disponible en el prototipo."
# Largo de `celda.motivo_incumplimiento` en el ER; el detalle completo queda en `incumplimiento`.
LARGO_MOTIVO = 200


class ServicioGeneracion:
    def __init__(self, db: Session):
        self.db = db
        self.motor = mt.MotorGeneracion()

    def generar_alternativa(self, id_proyecto: int, estrategia: EstrategiaIn, usuario: Usuario) -> Alternativa:
        """CU06: genera y registra una alternativa nueva. Si el motor no puede, responde 422
        con causa y sugerencia, y no se guarda nada."""
        proyecto = proyectos.obtener(self.db, id_proyecto)
        conjunto = proyecto.parametros_vigentes()
        if conjunto is None or conjunto.loteo is None:
            raise ErrorApi(
                409,
                "El proyecto no tiene parámetros de loteo vigentes.",
                "Configurá los parámetros del proyecto antes de generar (CU05).",
            )
        # La duración incluye la conversión de coordenadas y el motor, no la persistencia.
        inicio = time.perf_counter()
        solicitud = self.armar_solicitud(proyecto, conjunto, estrategia)
        resultado = self._generar(solicitud, proyecto.srid_calculo)
        duracion_ms = round((time.perf_counter() - inicio) * 1000)

        alternativa = self.registrar_version(proyecto, conjunto, solicitud, resultado, usuario, duracion_ms)
        self.db.commit()
        return alternativa

    def recalcular(self, id_version: int, entrada: RecalculoIn, usuario: Usuario) -> VersionAlternativa:
        """CU09 (secuencia de la p. 44): conserva las manzanas elegidas de la versión, con sus celdas y
        sus calles, y recalcula el resto con la estrategia confirmada y los parámetros vigentes del
        proyecto. Registra la versión n + 1 de la misma alternativa; la de origen no cambia. 422 con
        causa y sugerencia si no queda nada que recalcular (3.a), si lo nuevo no se conecta con lo
        fijado (5.a) o si las jerarquías de calle cambiaron desde la versión de origen."""
        version = self.recalcular_sin_confirmar(fijacion.obtener_version(self.db, id_version), entrada, usuario)
        self.db.commit()
        return version

    def recalcular_sin_confirmar(
        self, origen: VersionAlternativa, entrada: RecalculoIn, usuario: Usuario
    ) -> VersionAlternativa:
        """El recálculo del CU09 sin confirmar la transacción: lo usa también la respuesta a una
        observación con un recálculo (CU12, 3.a), que guarda la versión y la respuesta juntas (D69)."""
        proyecto = origen.alternativa.proyecto
        conjunto = proyecto.parametros_vigentes()
        if conjunto is None or conjunto.loteo is None:
            raise ErrorApi(
                409,
                "El proyecto no tiene parámetros de loteo vigentes.",
                "Configurá los parámetros del proyecto antes de recalcular (CU05).",
            )
        _exigir_las_mismas_jerarquias(conjunto, origen.conjunto)
        inicio = time.perf_counter()
        # Las áreas reservadas son las de la versión de origen, aunque el proyecto haya cambiado las
        # suyas: lo fijado se generó con ellas (D59).
        reservadas = areas_de_version(origen, proyecto.srid_calculo)
        solicitud = self.armar_solicitud(proyecto, conjunto, entrada.estrategia, reservadas)
        fijados = self.armar_fijados(origen, entrada.manzanas)
        resultado = self._ejecutar(lambda: self.motor.recalcular(solicitud, fijados), proyecto.srid_calculo)
        duracion_ms = round((time.perf_counter() - inicio) * 1000)
        version = self.registrar_recalculo(origen, conjunto, solicitud, resultado, fijados, usuario, duracion_ms)
        self.db.flush()
        return version

    def armar_fijados(self, version: VersionAlternativa, manzanas: list[str]) -> mt.ElementosFijados:
        """`armarFijados(version, ids)` de la p. 47 (`services.fijacion`)."""
        return fijacion.armar_fijados(self.motor, version, manzanas)

    def armar_solicitud(
        self, proyecto: Proyecto, conjunto: ConjuntoParametros, estrategia: EstrategiaIn, reservadas=None
    ) -> mt.SolicitudGeneracion:
        """`armarSolicitud` del diagrama (p. 47): lo guardado más la estrategia confirmada. La
        traducción de lo guardado está en `services.solicitud` (copia única, D36). Sin `reservadas`,
        las áreas del proyecto."""
        return armar_solicitud(
            proyecto,
            conjunto,
            mt.Estrategia(mt.PatronRed(estrategia.patron_red), float(estrategia.orientacion_grados), estrategia.semilla),
            reservadas,
        )

    def _generar(self, solicitud: mt.SolicitudGeneracion, srid: int) -> mt.ResultadoGeneracion:
        return self._ejecutar(lambda: self.motor.generar(solicitud), srid)

    def _ejecutar(self, llamada, srid: int) -> mt.ResultadoGeneracion:
        """El motor, con sus errores traducidos al 422 de CU06 y de CU09."""
        try:
            return llamada()
        except mt.SinDominioRestante as error:
            raise ErrorApi(422, error.causa, error.sugerencia) from error
        except mt.NoImplementado as error:
            raise ErrorApi(422, error.causa, error.sugerencia or SUGERENCIA_NO_IMPLEMENTADO) from error
        except mt.SolicitudInvalida as error:
            raise ErrorApi(
                422,
                "Los datos del proyecto no permiten generar.",
                "Revisá el terreno y los parámetros señalados.",
                [(problema.campo, problema.mensaje) for problema in error.problemas],
            ) from error
        except mt.TerrenoSinLotes as error:
            raise ErrorApi(422, error.causa, error.sugerencia) from error
        except mt.ErrorConectividad as error:
            geometria = None
            if error.geometria is not None and not error.geometria.is_empty:
                geometria = geojson_geografico(coordenadas.a_geograficas(error.geometria, srid))
            raise ErrorApi(422, error.causa, error.sugerencia, geometria=geometria) from error

    def registrar_version(
        self,
        proyecto: Proyecto,
        conjunto: ConjuntoParametros,
        solicitud: mt.SolicitudGeneracion,
        resultado: mt.ResultadoGeneracion,
        usuario: Usuario,
        duracion_ms: int,
    ) -> Alternativa:
        """VersionAlternativa.crear(resultado, parámetros, estrategia, v = 1) de la p. 43: red,
        manzanas, celdas e incumplimientos, en 4326 y en la transacción del pedido."""
        # El código se calcula con el proyecto bloqueado: dos generaciones simultáneas del
        # mismo proyecto no pueden tomar la misma letra.
        self.db.execute(select(Proyecto.id_proyecto).where(Proyecto.id_proyecto == proyecto.id_proyecto).with_for_update())
        existentes = self.db.scalar(
            select(func.count()).select_from(Alternativa).where(Alternativa.id_proyecto == proyecto.id_proyecto)
        )
        version = self._version(proyecto, conjunto, solicitud, resultado, usuario, duracion_ms, numero=1)
        version.areas_reservadas = _copia_de_areas(proyecto.terreno.areas_reservadas, solicitud.reservadas)
        alternativa = Alternativa(
            proyecto=proyecto,
            codigo=codigo_alternativa(existentes + 1),
            estado=EstadoAlternativa.GENERADA,
            versiones=[version],
        )
        self.db.add(alternativa)
        return alternativa

    def registrar_recalculo(
        self,
        origen: VersionAlternativa,
        conjunto: ConjuntoParametros,
        solicitud: mt.SolicitudGeneracion,
        resultado: mt.ResultadoGeneracion,
        fijados: mt.ElementosFijados,
        usuario: Usuario,
        duracion_ms: int,
    ) -> VersionAlternativa:
        """VersionAlternativa.crear(resultado, origen, sector fijado, v = n + 1) de la p. 44: la
        versión nueva de la misma alternativa, con `id_version_origen`, `geom_fijada` y las marcas
        `fijada` / `fijado` (D56). Las celdas y manzanas fijadas, y los ejes de los tramos fijados que
        no se partieron, se copian de las filas de origen: lo fijado no cambia ni en un bit."""
        alternativa = origen.alternativa
        # El número se calcula con la alternativa bloqueada: dos recálculos simultáneos no pueden
        # tomar el mismo.
        self.db.execute(
            select(Alternativa.id_alternativa)
            .where(Alternativa.id_alternativa == alternativa.id_alternativa)
            .with_for_update()
        )
        ultimo = self.db.scalar(
            select(func.max(VersionAlternativa.numero)).where(VersionAlternativa.id_alternativa == alternativa.id_alternativa)
        )
        version = self._version(
            alternativa.proyecto, conjunto, solicitud, resultado, usuario, duracion_ms, (ultimo or 0) + 1, origen, fijados
        )
        version.areas_reservadas = _copia_de_areas(origen.areas_reservadas, solicitud.reservadas)
        version.alternativa = alternativa
        self.db.add(version)
        return version

    def copiar_version(self, id_version: int, usuario: Usuario) -> VersionAlternativa:
        """Volver a una versión anterior (p. 50; D60): la versión n + 1 de la misma alternativa, copia
        de la elegida. No corre el motor: copia sus filas (red, manzanas, celdas, incumplimientos y
        áreas reservadas) con su conjunto de parámetros, su estrategia, sus indicadores y la versión
        del motor que la generó. Lleva `id_version_origen` = la elegida y no tiene sector fijado, ni
        marcas de fijación: no es un recálculo.

        Nunca modifica ni reactiva una versión existente: la vigente es la de mayor número (D57), y la
        base rechaza modificar una versión (RNF04). 422 si la elegida ya es la vigente."""
        elegida = fijacion.obtener_version(self.db, id_version)
        alternativa = elegida.alternativa
        self.db.execute(
            select(Alternativa.id_alternativa)
            .where(Alternativa.id_alternativa == alternativa.id_alternativa)
            .with_for_update()
        )
        ultimo = self.db.scalar(
            select(func.max(VersionAlternativa.numero)).where(VersionAlternativa.id_alternativa == alternativa.id_alternativa)
        )
        if elegida.numero == ultimo:
            raise ErrorApi(
                422,
                f"La versión {elegida.numero} ya es la vigente de la alternativa {alternativa.codigo}.",
                "Elegí una versión anterior: volver a ella crea una versión nueva que la copia.",
            )
        nueva = _copia_de_version(elegida, usuario, ultimo + 1)
        nueva.alternativa = alternativa
        self.db.add(nueva)
        self.db.commit()
        return nueva

    def _version(
        self,
        proyecto: Proyecto,
        conjunto: ConjuntoParametros,
        solicitud: mt.SolicitudGeneracion,
        resultado: mt.ResultadoGeneracion,
        usuario: Usuario,
        duracion_ms: int,
        numero: int,
        origen: VersionAlternativa | None = None,
        fijados: mt.ElementosFijados | None = None,
    ) -> VersionAlternativa:
        """Las filas de una versión (red, manzanas, celdas e incumplimientos), en 4326. En un
        recálculo, lo fijado lleva su marca y se copia de la versión de origen."""
        srid = proyecto.srid_calculo

        def en_4326(geometrias) -> list:
            # Una conversión por grupo, no por geometría: cada una crea un Transformer.
            return [guardable(g) for g in coordenadas.a_geograficas_todas(geometrias, srid)]

        manzanas_fijas = {m.designacion for m in fijados.manzanas} if fijados else set()
        celdas_fijas = {c.designacion for c in fijados.celdas} if fijados else set()
        manzana_de_origen = {m.designacion: m for m in origen.manzanas} if origen else {}
        celda_de_origen = {c.designacion: c for c in origen.celdas} if origen else {}

        red = resultado.red
        claves = red.nodos()
        nodos = {
            clave: NodoRed(geom=geom) for clave, geom in zip(claves, en_4326([Point(c) for c in claves]), strict=True)
        }
        for acceso, punto in zip(proyecto.terreno.accesos, solicitud.accesos, strict=True):
            nodo = red.nodo_de_acceso(punto)
            if nodo is not None and nodos[nodo].punto_acceso is None:
                nodos[nodo].punto_acceso = acceso

        jerarquia_de_orden = {j.orden: j for j in conjunto.jerarquias}
        tramos_motor = red.tramos()
        ejes_4326 = coordenadas.a_geograficas_todas([t.eje for t in tramos_motor], srid)
        ejes = [guardable(e) for e in ejes_4326]
        if origen is not None:
            # El eje de un tramo fijado entero es el de origen, copiado (D56).
            de_origen = list(origen.tramos)
            ejes = [
                _eje_de_origen(eje_4326, de_origen) if tramo.fijado else eje
                for tramo, eje, eje_4326 in zip(tramos_motor, ejes, ejes_4326, strict=True)
            ]
        calles = en_4326([_multipoligono(c) for c in resultado.corredores])
        tramos = [
            TramoCirculacion(
                jerarquia=jerarquia_de_orden[tramo.jerarquia.orden],
                origen=nodos[tramo.origen],
                destino=nodos[tramo.destino],
                eje=eje,
                geom=None if corredor.is_empty else calle,
                longitud_m=centesimos(tramo.longitud),
                fijado=tramo.fijado,
            )
            for tramo, corredor, eje, calle in zip(tramos_motor, resultado.corredores, ejes, calles, strict=True)
        ]

        designaciones = [resultado.designacion_manzana(k) for k in range(1, len(resultado.manzanas) + 1)]
        manzanas = [
            Manzana(
                designacion=designacion,
                geom=manzana_de_origen[designacion].geom if designacion in manzanas_fijas else geom,
                superficie_m2=centesimos(m.area),
                fijada=designacion in manzanas_fijas,
            )
            for designacion, m, geom in zip(designaciones, resultado.manzanas, en_4326(resultado.manzanas), strict=True)
        ]

        detalles = defaultdict(list)
        for incumplimiento in resultado.incumplimientos:
            detalles[incumplimiento.elemento].append(incumplimiento.detalle)
        celdas = {
            c.designacion: Celda(
                manzana=manzanas[c.indice_manzana - 1],
                designacion=c.designacion,
                tipo=str(c.tipo),
                geom=celda_de_origen[c.designacion].geom if c.designacion in celdas_fijas else geom,
                superficie_m2=centesimos(c.geometria.area),
                frente_m=centesimos(c.frente),
                fondo_m=centesimos(c.fondo),
                cumple=c.designacion not in detalles,
                motivo_incumplimiento=_motivo(detalles.get(c.designacion)),
                fijada=c.designacion in celdas_fijas,
            )
            for c, geom in zip(resultado.celdas, en_4326([c.geometria for c in resultado.celdas]), strict=True)
        }

        geometrias = [i.geometria for i in resultado.incumplimientos]
        incumplimientos = [
            Incumplimiento(
                celda=celdas.get(i.elemento),
                tipo=str(i.tipo),
                elemento=i.elemento,
                detalle=i.detalle,
                geom=None if i.geometria is None or i.geometria.is_empty else geom,
            )
            for i, geom in zip(
                resultado.incumplimientos,
                en_4326([g if g is not None else Point() for g in geometrias]),
                strict=True,
            )
        ]

        indicadores = resultado.indicadores
        estrategia = solicitud.estrategia
        version = VersionAlternativa(
            conjunto=conjunto,
            usuario=usuario,
            numero=numero,
            tipo=TipoVersion.GENERADA if origen is None else TipoVersion.RECALCULADA,
            id_version_origen=None if origen is None else origen.id_version,
            geom_fijada=None if fijados is None else en_4326([_multipoligono(fijados.sector)])[0],
            patron_red=str(estrategia.patron_red),
            orientacion_grados=centesimos(estrategia.orientacion),
            semilla=estrategia.semilla,
            cumple_restricciones=resultado.cumple(),
            cantidad_celdas=indicadores.cantidad_celdas,
            superficie_aprovechable_m2=centesimos(indicadores.superficie_aprovechable),
            porcentaje_circulacion=centesimos(indicadores.porcentaje_circulacion),
            porcentaje_espacio_verde=centesimos(indicadores.porcentaje_espacio_verde),
            longitud_red_m=centesimos(indicadores.longitud_red),
            distancia_media_acceso_m=None
            if indicadores.distancia_media_acceso is None
            else centesimos(indicadores.distancia_media_acceso),
            superficie_espacio_verde_m2=centesimos(indicadores.superficie_espacio_verde),
            superficie_espacio_libre_m2=centesimos(indicadores.superficie_espacio_libre),
            porcentaje_cesion=None if indicadores.porcentaje_cesion is None else centesimos(indicadores.porcentaje_cesion),
            cantidad_lotes_grandes=indicadores.cantidad_lotes_grandes,
            porcentaje_avenidas=centesimos(indicadores.porcentaje_avenidas),
            distancia_media_verde_m=None
            if indicadores.distancia_media_verde is None
            else centesimos(indicadores.distancia_media_verde),
            distancia_maxima_verde_m=None
            if indicadores.distancia_maxima_verde is None
            else centesimos(indicadores.distancia_maxima_verde),
            superficie_verde_computable_m2=centesimos(indicadores.superficie_verde_computable),
            duracion_ms=duracion_ms,
            version_motor=mt.__version__,
            nodos=list(nodos.values()),
            tramos=tramos,
            manzanas=manzanas,
            celdas=list(celdas.values()),
            incumplimientos=incumplimientos,
        )
        return version


def obtener_alternativa(db: Session, id_alternativa: int) -> Alternativa:
    alternativa = db.get(Alternativa, id_alternativa)
    if alternativa is None:
        raise ErrorApi(404, f"No existe la alternativa {id_alternativa}.")
    return alternativa


def presentar_alternativa(alternativa: Alternativa, version: VersionAlternativa | None = None) -> AlternativaOut:
    """La alternativa con su versión vigente (o la pedida), en GeoJSON, leída de la base (el 201 de
    la generación y del recálculo dan lo mismo que el GET)."""
    version = version or alternativa.version_vigente()
    terreno = alternativa.proyecto.terreno
    acceso_de = {acceso.id_punto_acceso: d for d, acceso in proyectos.designaciones_de_accesos(alternativa.proyecto)}
    jerarquia_de = {j.id_jerarquia: j for j in version.conjunto.jerarquias}
    manzana_de = {m.id_manzana: m.designacion for m in version.manzanas}

    def de_tramo(tramo: TramoCirculacion) -> dict:
        jerarquia = jerarquia_de[tramo.id_jerarquia]
        return {
            "id_tramo": tramo.id_tramo,
            "jerarquia": jerarquia.nombre,
            "orden": jerarquia.orden,
            "fijado": tramo.fijado,
        }

    capas = CapasOut(
        ejes=coleccion([feature(t.eje, de_tramo(t) | {"longitud_m": float(t.longitud_m)}) for t in version.tramos]),
        calles=coleccion([feature(t.geom, de_tramo(t)) for t in version.tramos if t.geom is not None]),
        nodos=coleccion(
            [feature(n.geom, {"id_nodo": n.id_nodo, "acceso": acceso_de.get(n.id_punto_acceso)}) for n in version.nodos]
        ),
        manzanas=coleccion(
            [
                feature(
                    m.geom,
                    {
                        "id_manzana": m.id_manzana,
                        "designacion": m.designacion,
                        "superficie_m2": float(m.superficie_m2),
                        "fijada": m.fijada,
                    },
                )
                for m in version.manzanas
            ]
        ),
        celdas=coleccion(
            [
                feature(
                    c.geom,
                    {
                        "id_celda": c.id_celda,
                        "designacion": c.designacion,
                        "manzana": manzana_de.get(c.id_manzana),
                        "tipo": c.tipo,
                        "superficie_m2": float(c.superficie_m2),
                        "frente_m": float(c.frente_m),
                        "fondo_m": float(c.fondo_m),
                        "cumple": c.cumple,
                        "motivo_incumplimiento": c.motivo_incumplimiento,
                        "fijada": c.fijada,
                    },
                )
                for c in version.celdas
            ]
        ),
        incumplimientos=coleccion(
            [
                feature(i.geom, {"tipo": i.tipo, "elemento": i.elemento, "detalle": i.detalle})
                for i in version.incumplimientos
            ]
        ),
        areas_reservadas=coleccion(
            [
                feature(
                    a.geom,
                    {
                        "designacion": a.designacion,
                        "clase": a.clase,
                        "denominacion": a.denominacion,
                        "destino": a.destino,
                        "superficie_m2": float(a.superficie_m2),
                    },
                )
                for a in version.areas_reservadas
            ]
        ),
    )
    indicadores = indicadores_de(version, terreno)
    return AlternativaOut(
        id_alternativa=alternativa.id_alternativa,
        id_proyecto=alternativa.id_proyecto,
        codigo=alternativa.codigo,
        estado=alternativa.estado,
        fecha_creacion=alternativa.fecha_creacion,
        descripcion=alternativa.descripcion,
        versiones=proyectos.resumen_versiones(alternativa),
        version=VersionOut(
            id_version=version.id_version,
            numero=version.numero,
            id_version_origen=version.id_version_origen,
            id_conjunto=version.id_conjunto,
            version_parametros=version.conjunto.version,
            estrategia=EstrategiaOut(
                patron_red=version.patron_red,
                orientacion_grados=float(version.orientacion_grados),
                semilla=version.semilla,
            ),
            generada_por=proyectos.resumen_usuario(version.usuario),
            fecha_generacion=version.fecha_generacion,
            duracion_ms=version.duracion_ms,
            version_motor=version.version_motor,
            cumple_restricciones=version.cumple_restricciones,
            indicadores=indicadores,
            capas=capas,
            fijacion=_fijacion(version, alternativa.proyecto.srid_calculo),
            diferencias_con_origen=_diferencias_con_origen(version, terreno),
            tipo=version.tipo,
            verificaciones=verificaciones.verificaciones_de(version, indicadores),
            responde_a=responde_a(alternativa, version),
        ),
    )


def responde_a(alternativa: Alternativa, version: VersionAlternativa) -> list[str]:
    """Las observaciones cuya respuesta con un recálculo creó esta versión (CU12, 3.a; «Responde a O-1»,
    p. 50; D74), por su designación."""
    nombres = designaciones(alternativa)
    return [
        nombres[o.id_observacion]
        for o in de_la_alternativa(alternativa)
        if any(r.id_version_resultante == version.id_version for r in o.respuestas)
    ]


def _fijacion(version: VersionAlternativa, srid: int) -> FijacionOut | None:
    """Lo que se conservó en un recálculo (p. 50), derivado de las filas: las manzanas y celdas
    fijadas, la superficie del sector, y dónde se une la red fijada con la nueva (D60).

    Los anclajes son los de la vista previa: salen de `MotorGeneracion.fijar` sobre la versión de
    origen, la copia única de la regla (D56). Una conexión es un nodo con un tramo fijado y uno
    nuevo: si está en un anclaje, el anclaje se unió; si no, es un empalme (un nodo nuevo sobre el
    costado de una calle fijada)."""
    if version.tipo != TipoVersion.RECALCULADA:
        return None
    origen = next(v for v in version.alternativa.versiones if v.id_version == version.id_version_origen)
    fijos = {n for t in version.tramos if t.fijado for n in (t.id_nodo_origen, t.id_nodo_destino)}
    nuevos = {n for t in version.tramos if not t.fijado for n in (t.id_nodo_origen, t.id_nodo_destino)}
    conexiones = sorted(fijos & nuevos)
    celdas = [c for c in version.celdas if c.fijada]
    manzanas = [m.designacion for m in version.manzanas if m.fijada]
    anclajes = fijacion.armar_fijados(mt.MotorGeneracion(), origen, manzanas).anclajes
    geom_de = {n.id_nodo: n.geom for n in version.nodos}
    puntos = coordenadas.a_metros_todas([to_shape(geom_de[n]) for n in conexiones], srid) if conexiones else []
    unidos = sum(1 for anclaje in anclajes if any(anclaje.distance(p) <= TOLERANCIA for p in puntos))
    en_anclaje = sum(1 for p in puntos if any(anclaje.distance(p) <= TOLERANCIA for anclaje in anclajes))
    return FijacionOut(
        id_version_origen=origen.id_version,
        numero_origen=origen.numero,
        manzanas=manzanas,
        cantidad_celdas=len(celdas),
        cantidad_lotes=sum(1 for c in celdas if c.tipo == str(mt.TipoCelda.LOTE)),
        superficie_m2=float(centesimos(coordenadas.a_metros(to_shape(version.geom_fijada), srid).area)),
        cantidad_anclajes=len(anclajes),
        cantidad_anclajes_unidos=unidos,
        cantidad_empalmes=len(conexiones) - en_anclaje,
        sector=geojson(version.geom_fijada),
    )


def _diferencias_con_origen(version: VersionAlternativa, terreno: Terreno):
    """La tabla «Diferencias entre versiones» de la p. 50, con las reglas de la comparación (D54). Una
    copia (volver a una versión anterior, D60) es igual a su origen: no tiene tabla."""
    if version.tipo != TipoVersion.RECALCULADA:
        return None
    from app.services.comparacion import diferencias_entre

    origen = next(v for v in version.alternativa.versiones if v.id_version == version.id_version_origen)
    return diferencias_entre(origen, version, terreno)


# El primer motor que calcula los porcentajes sobre la superficie disponible (D61).
MOTOR_SOBRE_DISPONIBLE = (0, 10, 0)


def superficie_reservada(version: VersionAlternativa) -> Decimal:
    """La de las áreas reservadas con las que se generó la versión (su copia, D59): 0 sin áreas."""
    return sum((a.superficie_m2 for a in version.areas_reservadas), Decimal(0))


def base_de_porcentajes(version: VersionAlternativa, terreno: Terreno) -> tuple[str, Decimal]:
    """Sobre qué superficie calculó el motor los porcentajes de la versión, y cuánto mide (D61).

    Desde el motor 0.10.0, la disponible: el terreno menos las áreas reservadas de la versión. Antes,
    el terreno entero. Las versiones guardadas no se recalculan (RNF04), así que una del motor 0.9.0
    con áreas conserva sus porcentajes sobre el terreno, y lo que se deriva acá sigue la misma base.
    Sin áreas, las dos bases son la misma."""
    motor = tuple(int(parte) for parte in version.version_motor.split("."))
    if motor >= MOTOR_SOBRE_DISPONIBLE:
        return "disponible", terreno.superficie_m2 - superficie_reservada(version)
    return "terreno", terreno.superficie_m2


def indicadores_de(version: VersionAlternativa, terreno: Terreno) -> IndicadoresOut:
    """Los indicadores de una versión, leídos de la base (CU08). Es la copia única: los usan el GET
    de la alternativa y la comparación (CU13, D54)."""
    base, superficie_base = base_de_porcentajes(version, terreno)
    reservada = superficie_reservada(version)
    return IndicadoresOut(
        cantidad_celdas=version.cantidad_celdas,
        superficie_aprovechable_m2=float(version.superficie_aprovechable_m2),
        # Como los calcula el motor: sobre la misma base que los demás porcentajes de la versión (D61);
        # no conforme es un lote con incumplimientos (un remanente no es un lote, D41).
        porcentaje_aprovechamiento=float(
            centesimos(float(version.superficie_aprovechable_m2) / float(superficie_base) * 100)
        ),
        cantidad_fracciones_no_conformes=sum(
            1 for c in version.celdas if c.tipo == str(mt.TipoCelda.LOTE) and not c.cumple
        ),
        # Todos los incumplimientos de la versión: lotes, cesión, art. 12, art. 48… (D54).
        cantidad_incumplimientos=len(version.incumplimientos),
        porcentaje_circulacion=float(version.porcentaje_circulacion),
        porcentaje_espacio_verde=float(version.porcentaje_espacio_verde),
        longitud_red_m=float(version.longitud_red_m),
        distancia_media_acceso_m=numero(version.distancia_media_acceso_m),
        superficie_espacio_verde_m2=numero(version.superficie_espacio_verde_m2),
        superficie_espacio_libre_m2=numero(version.superficie_espacio_libre_m2),
        porcentaje_cesion=numero(version.porcentaje_cesion),
        cantidad_lotes_grandes=version.cantidad_lotes_grandes,
        porcentaje_avenidas=numero(version.porcentaje_avenidas),
        distancia_media_verde_m=numero(version.distancia_media_verde_m),
        distancia_maxima_verde_m=numero(version.distancia_maxima_verde_m),
        superficie_verde_computable_m2=numero(version.superficie_verde_computable_m2),
        # Como la p. 51: la superficie aprovechable sobre las celdas útiles.
        superficie_media_celda_m2=float(
            centesimos(float(version.superficie_aprovechable_m2) / version.cantidad_celdas)
        )
        if version.cantidad_celdas
        else None,
        # De la copia de las áreas con las que se generó (D59): 0 sin áreas, también en las versiones
        # anteriores a la 0009, que se generaron sin ellas.
        superficie_reservada_m2=float(reservada),
        superficie_disponible_m2=float(terreno.superficie_m2 - reservada),
        base_porcentajes=base,
    )


def codigo_alternativa(numero: int) -> str:
    """1 → A, 26 → Z, 27 → AA… («Alternativa B», p. 49). Cabe en varchar(5) hasta 12 356 630."""
    codigo = ""
    while numero > 0:
        numero, resto = divmod(numero - 1, 26)
        codigo = chr(ord("A") + resto) + codigo
    return codigo


def _exigir_las_mismas_jerarquias(vigente: ConjuntoParametros, origen: ConjuntoParametros) -> None:
    """Las calles fijadas tienen el ancho y la ochava de las jerarquías de la versión de origen: si
    las vigentes cambiaron, recalcular con ellas mezclaría dos perfiles (D56)."""

    def perfil(conjunto) -> dict:
        return {
            j.orden: (float(j.ancho_calzada_m), float(j.ancho_vereda_m), float(j.radio_ochava_m))
            for j in conjunto.jerarquias
        }

    if perfil(vigente) != perfil(origen):
        raise ErrorApi(
            422,
            f"Las jerarquías de calle de los parámetros vigentes (v{vigente.version}) no son las de la versión "
            f"de origen (v{origen.version}): las calles fijadas quedarían con otro ancho.",
            "Recalculá con una versión de parámetros que tenga las mismas jerarquías, o generá una alternativa "
            "nueva.",
            [("jerarquias", "Cambiaron el ancho de calzada, el de vereda o la ochava de alguna jerarquía.")],
        )


def _eje_de_origen(eje_4326, de_origen: list[TramoCirculacion]):
    """El eje guardado de origen de un tramo fijado entero (el mismo, a menos de 1 cm), o el nuevo
    si el tramo se partió en un empalme."""
    candidatos = [t for t in de_origen if hausdorff_distance(to_shape(t.eje), eje_4326) <= 1e-7]
    return candidatos[0].eje if candidatos else guardable(eje_4326)


def _multipoligono(geometria) -> MultiPolygon:
    """La superficie de un tramo como MultiPolygon (columna del tramo, D28). Vacía si el tramo
    cae entero dentro de un cruce."""
    if isinstance(geometria, MultiPolygon):
        return geometria
    if isinstance(geometria, Polygon):
        return MultiPolygon([geometria]) if not geometria.is_empty else MultiPolygon()
    # Una colección (polígonos con restos lineales de un overlay): solo sus polígonos.
    return MultiPolygon(poligonos(geometria))


def _copia_de_areas(fuentes, reservadas) -> list[AreaReservadaVersion]:
    """La copia de las áreas reservadas con las que se generó una versión (D59): las del proyecto al
    generar, o las de la versión de origen al recalcular, en el orden de la solicitud (R1, R2…). El
    polígono es el mismo WKB que recibió el motor, y la superficie, la que midió en metros."""
    return [
        AreaReservadaVersion(
            designacion=f"R{k}",
            geom=fuente.geom,
            clase=fuente.clase,
            denominacion=fuente.denominacion,
            destino=fuente.destino,
            superficie_m2=centesimos(area.area),
        )
        for k, (fuente, area) in enumerate(zip(fuentes, reservadas, strict=True), 1)
    ]


# Columnas de una versión que no se copian al volver a ella (D60): la identidad, la alternativa, el
# origen, quién y cuándo, el número y el sector fijado de un recálculo.
NO_SE_COPIAN = {
    "id_version",
    "id_alternativa",
    "id_version_origen",
    "id_usuario",
    "numero",
    "tipo",
    "geom_fijada",
    "fecha_generacion",
}


def _copia_de_version(elegida: VersionAlternativa, usuario: Usuario, numero: int) -> VersionAlternativa:
    """Las filas de una versión nueva que copia la elegida (D60): las mismas geometrías (el mismo
    WKB) y los mismos valores, sin las marcas de fijación de un recálculo. La red se copia con sus
    nodos, y cada celda y cada incumplimiento, con su manzana y su celda nuevas."""
    nueva = VersionAlternativa(
        usuario=usuario,
        numero=numero,
        tipo=TipoVersion.COPIA,
        id_version_origen=elegida.id_version,
        geom_fijada=None,
    )
    for columna in VersionAlternativa.__table__.columns:
        if columna.key not in NO_SE_COPIAN:
            setattr(nueva, columna.key, getattr(elegida, columna.key))
    nodos = {n.id_nodo: NodoRed(geom=n.geom, id_punto_acceso=n.id_punto_acceso) for n in elegida.nodos}
    manzanas = {
        m.id_manzana: Manzana(designacion=m.designacion, geom=m.geom, superficie_m2=m.superficie_m2, fijada=False)
        for m in elegida.manzanas
    }
    celdas = {
        c.id_celda: Celda(
            manzana=manzanas.get(c.id_manzana),
            designacion=c.designacion,
            tipo=c.tipo,
            geom=c.geom,
            superficie_m2=c.superficie_m2,
            frente_m=c.frente_m,
            fondo_m=c.fondo_m,
            cumple=c.cumple,
            motivo_incumplimiento=c.motivo_incumplimiento,
            fijada=False,
        )
        for c in elegida.celdas
    }
    nueva.nodos = list(nodos.values())
    nueva.tramos = [
        TramoCirculacion(
            id_jerarquia=t.id_jerarquia,
            origen=nodos[t.id_nodo_origen],
            destino=nodos[t.id_nodo_destino],
            eje=t.eje,
            geom=t.geom,
            longitud_m=t.longitud_m,
            fijado=False,
        )
        for t in elegida.tramos
    ]
    nueva.manzanas = list(manzanas.values())
    nueva.celdas = list(celdas.values())
    nueva.incumplimientos = [
        Incumplimiento(celda=celdas.get(i.id_celda), tipo=i.tipo, elemento=i.elemento, detalle=i.detalle, geom=i.geom)
        for i in elegida.incumplimientos
    ]
    nueva.areas_reservadas = [
        AreaReservadaVersion(
            designacion=a.designacion,
            geom=a.geom,
            clase=a.clase,
            denominacion=a.denominacion,
            destino=a.destino,
            superficie_m2=a.superficie_m2,
        )
        for a in elegida.areas_reservadas
    ]
    return nueva


def _motivo(detalles: list[str] | None) -> str | None:
    if not detalles:
        return None
    motivo = "; ".join(detalles)
    return motivo if len(motivo) <= LARGO_MOTIVO else motivo[: LARGO_MOTIVO - 1] + "…"
