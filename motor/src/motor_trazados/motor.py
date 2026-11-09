"""Motor de generación: arma una alternativa de punta a punta (secuencia de la p. 43; D24).

    solicitud → validar → dominio → red con su calle de borde y sus avenidas (conexa con los
              accesos) → corredores y ochavas → manzanas (las que no alcanzan el lado menor
              del art. 48 no se subdividen) → piezas → lotes grandes subdivididos → cierre de la
              partición → lotes y remanentes → espacios verdes (cesión) → verificación
              → indicadores → resultado

Todo en metros, en el sistema de cálculo del proyecto. Internamente se calcula en un marco
local (trasladado y rotado según la orientación de la estrategia), donde la partición se
construye y se cierra con la grilla de 1 mm (D25, D39). El resultado vuelve al sistema de
cálculo con una transformación rígida, sin redondear, y no se vuelve a ajustar a ninguna
grilla: así las piezas vecinas siguen compartiendo sus bordes exactos.

Acepta cualquier polígono válido (D40). Lo que no se puede lotear queda como remanente,
espacio verde o libre (D41); solo se rechaza el terreno donde no entra ni un lote. El asignador
convierte parcelas en verde hasta cubrir la cesión (D44): a diferencia de la secuencia de la
p. 43, corre después de subdividir, porque la base de la cesión son los lotes.

Ord. 8060, art. 48 (D50): una calle de borde recorre el contorno, así toda manzana tiene calle de
los dos lados y dos fondos. La manzana que igual no alcanza el lado menor (una punta contra una
esquina aguda, un recorte) sale entera como una pieza remanente: verde o libre.

Áreas reservadas (CU06, paso 4; D59): el dominio es el terreno menos las áreas, con una calle de
borde alrededor de cada una. Las áreas son piezas fijas del cierre (`geometria.cerrar_con_fijas`,
la mecánica del recálculo): conservan su forma y quedan en el resultado aparte de las celdas. El
marco local sale del terreno, no del dominio, así las áreas no cambian el marco de la alternativa.
"""

import itertools
import math
from dataclasses import replace

import shapely

from shapely import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon

from .contrato import (
    CalleBorde,
    CeldaGenerada,
    ElementosFijados,
    Estrategia,
    ManzanaFijada,
    ParametrosLoteo,
    PatronRed,
    ResultadoGeneracion,
    SolicitudGeneracion,
    TipoCelda,
    TipoProyecto,
    TramoFijado,
)
from .asignador import AsignadorEspaciosVerdes
from .corredores import MaterializadorCorredores
from .errores import (
    ErrorConectividad,
    NoImplementado,
    Problema,
    SinDominioRestante,
    SolicitudInvalida,
    TerrenoSinLotes,
)
from .generador_red import SUGERENCIA, GeneradorRed, RedFija, lados_entrantes, limite_con_calle
from .geometria import (
    AREA_RUIDO,
    RESOLUCION,
    TOLERANCIA,
    IndiceEjes,
    MarcoLocal,
    ajustar,
    cerrar_particion,
    cerrar_con_fijas,
    clave_poligono,
    diferencia,
    interseccion,
    medir,
    poligonos,
    restaurar,
    sin_astillas,
    superficie,
    union,
    union_cobertura,
)
from .indicadores import CalculadorIndicadores
from .red import RedCirculacion
from .remanentes import ClasificadorRemanentes
from .semillas import SEMILLA_SUGERIDA
from .subdivisores import Subdivisor, SubdivisorLoteo
from .verificador import VerificadorRestricciones, alcanza_lado_menor, es_lote, es_lote_grande

SUGERENCIA_SIN_LOTES = (
    "Probá otra orientación de la grilla o revisá los parámetros del loteo; un terreno muy chico "
    "o muy angosto no admite lotes con esos mínimos."
)
SUGERENCIA_SIN_CONEXION = (
    "Probá otra orientación o fijá otras manzanas: lo que se recalcula tiene que llegar a una calle "
    "fijada o a un acceso."
)
# Lo mínimo que una manzana tiene que compartir con un corredor para que su calle se fije con ella:
# un lado, no la esquina de un cruce que la toca en un punto (D56).
LADO_COMPARTIDO = RESOLUCION


class MotorGeneracion:
    def __init__(self, asignar_espacios_verdes: bool = True):
        """`asignar_espacios_verdes=False` deja la alternativa como sale de la clasificación,
        sin completar la cesión: sirve para las pruebas y para medir cuántos lotes cuesta el
        verde (D44). La API genera siempre con el asignador."""
        self._generador_red = GeneradorRed()
        self._materializador = MaterializadorCorredores()
        self._clasificador = ClasificadorRemanentes()
        self._asignador = AsignadorEspaciosVerdes() if asignar_espacios_verdes else None
        self._verificador = VerificadorRestricciones()
        self._calculador = CalculadorIndicadores()
        # Un subdivisor por tipo de proyecto: el mismo motor, distintas celdas (p. 21).
        self._subdivisores: dict[TipoProyecto, Subdivisor] = {TipoProyecto.LOTEO: SubdivisorLoteo()}

    def generar(self, solicitud: SolicitudGeneracion) -> ResultadoGeneracion:
        """Genera una alternativa (CU06).

        Errores: `NoImplementado` (playas), `SolicitudInvalida` (datos incoherentes, polígono
        inválido, accesos fuera del borde, áreas reservadas que salen del terreno o se superponen),
        `ErrorConectividad` (la red no llega a todos los accesos) y `TerrenoSinLotes` (no entra ni
        un lote). Las fracciones donde no entra un lote no son errores: quedan como remanentes
        (D41), y los lotes que no cumplen un máximo vuelven marcados (CU06, 6.a).
        """
        subdivisor = self._seleccionar_subdivisor(solicitud.tipo)
        problemas = solicitud.validar()
        if problemas:
            raise SolicitudInvalida(problemas)
        terreno = solicitud.terreno

        # El marco sale del terreno, no del dominio: así las áreas no lo cambian (D59).
        marco = MarcoLocal.para(terreno, solicitud.estrategia.orientacion)
        terreno_local = ajustar(marco.a_local(terreno))
        reservadas = self._reservadas_en(marco, terreno_local, solicitud.reservadas)
        dominio_local = self._preparar_dominio(terreno_local, reservadas)
        accesos_locales = [marco.a_local(acceso) for acceso in solicitud.accesos]
        # Con áreas, la red conoce el terreno y las áreas: les pone su calle de borde (D59).
        contorno = {"terreno": terreno_local, "reservadas": reservadas} if reservadas else {}
        try:
            generada = self._generador_red.generar_con_avenidas(
                dominio_local, accesos_locales, solicitud.estrategia, solicitud.parametros, solicitud.jerarquias,
                **contorno,
            )
        except ErrorConectividad as error:
            geometria = marco.a_global(error.geometria) if error.geometria is not None else None
            raise ErrorConectividad(error.causa, error.sugerencia, geometria) from error
        red, motivo_avenidas = generada.red, generada.motivo
        self._exigir_red_conexa(red, accesos_locales, marco)

        limite = limite_con_calle(terreno_local, reservadas) if reservadas else None
        corredores = self._materializador.materializar(
            red,
            solicitud.jerarquias,
            dominio_local,
            limite=limite,
            reservadas=reservadas,
            entrantes=_entrantes(terreno_local, solicitud.parametros),
        )
        circulacion = union(corredores)
        manzanas = poligonos(diferencia(dominio_local, circulacion))
        piezas: list[CeldaGenerada] = []
        for indice, manzana in enumerate(manzanas, 1):
            if not alcanza_lado_menor(manzana, solicitud.parametros):
                # Ord. 8060, art. 48 (D50): una manzana que no alcanza el lado menor no lleva lotes.
                # Sale entera como una pieza remanente; el clasificador decide si es verde o libre.
                piezas.append(_sin_lotes(manzana, indice))
                continue
            frentes = subdivisor.identificar_frentes(manzana, circulacion)
            piezas += subdivisor.subdividir(manzana, frentes, solicitud.parametros, indice)
        piezas = self._subdividir_grandes(subdivisor, piezas, circulacion, red, solicitud.parametros)
        corredores, piezas, manzanas, reservadas = self._cerrar(terreno_local, corredores, piezas, len(manzanas), reservadas)

        # Vuelta al sistema de cálculo, rígida: los bordes compartidos siguen siendo idénticos.
        red_global = red.transformada(marco.a_global)
        # `corredores[i]` va con `red.tramos()[i]`; en la red transformada el orden de los tramos
        # cambia (las claves de los nodos son otras), así que se emparejan por sus nodos.
        corredor_de = {}
        for tramo, corredor in zip(red.tramos(), corredores, strict=True):
            eje = marco.a_global(tramo.eje)
            nodos = tuple(sorted((red_global.nodo(eje.coords[0]), red_global.nodo(eje.coords[-1]))))
            corredor_de[nodos] = marco.a_global(corredor)
        corredores_globales = tuple(corredor_de[(t.origen, t.destino)] for t in red_global.tramos())
        circulacion_global = union_cobertura(corredores_globales)
        ejes = IndiceEjes([tramo.eje for tramo in red_global.tramos()])
        # Lotes y remanentes se deciden con la geometría final, medida como la mide el
        # verificador (D26, D41).
        celdas = self._clasificador.clasificar(
            [replace(p, geometria=marco.a_global(p.geometria)) for p in piezas],
            circulacion_global,
            ejes,
            solicitud.parametros,
        )
        resultado = ResultadoGeneracion(
            red=red_global,
            corredores=corredores_globales,
            manzanas=tuple(marco.a_global(m) for m in manzanas),
            celdas=tuple(celdas),
            reservadas=tuple(marco.a_global(area) for area in reservadas),
        )
        if not resultado.lotes:
            p = solicitud.parametros
            raise TerrenoSinLotes(
                "En el terreno no entra ningún lote que cumpla los mínimos (frente "
                f"{p.frente_minimo:g} m, fondo {p.fondo_minimo:g} m y superficie {p.superficie_minima:g} m²).",
                SUGERENCIA_SIN_LOTES,
            )
        motivo_cesion = None
        if self._asignador is not None:
            asignacion = self._asignador.asignar(
                resultado.celdas, resultado.manzanas, circulacion_global, red_global, ejes, solicitud.parametros
            )
            resultado = replace(resultado, celdas=asignacion.celdas)
            motivo_cesion = asignacion.motivo
        incumplimientos = self._verificador.verificar(
            resultado, solicitud.parametros, solicitud.accesos, motivo_cesion, motivo_avenidas
        )
        resultado = replace(resultado, incumplimientos=tuple(incumplimientos))
        indicadores = self._calculador.calcular(resultado, terreno.area, solicitud.accesos, solicitud.parametros)
        return replace(resultado, indicadores=indicadores)

    def recalcular(self, solicitud: SolicitudGeneracion, fijados: ElementosFijados) -> ResultadoGeneracion:
        """Recálculo parcial (CU09, secuencia de la p. 44; D56): conserva lo fijado y genera la red y
        la subdivisión solo en el dominio restante, conectadas a lo fijado.

        1. Lo fijado vuelve exacto a la grilla de 1 mm en el marco de la alternativa (el de su v1),
           donde se cerró: el dominio restante es el terreno menos el sector, en ese marco.
        2. La grilla nueva se traza en el marco de la estrategia (sus calles paralelas a los ejes), en
           el dominio restante, con la calle de borde solo sobre el límite del terreno, y se integra
           con la red fijada (`GeneradorRed`, con `fija`).
        3. Corredores nuevos, manzanas nuevas (las que no alcanzan el lado menor no se subdividen) y
           su subdivisión, con la circulación completa: un lote nuevo frentea sobre una calle fijada.
        4. El cierre, en el marco de la alternativa, junto con lo fijado y sin moverlo
           (`geometria.cerrar_con_fijas`).
        5. Clasificación de lo nuevo, asignación del verde solo en las manzanas nuevas, y
           verificación e indicadores del trazado completo.

        Las áreas reservadas son las de la versión de origen (`solicitud.reservadas`, que arma la API
        con su copia): se descuentan del dominio restante, su calle se vuelve a trazar donde no se
        fijó, y entran al cierre como piezas fijas, como al generar (D59).

        Errores: los de `generar`, más `SinDominioRestante` si lo fijado abarca todo el terreno (3.a)
        y `ErrorConectividad` si la red nueva no se conecta con la fijada (5.a).
        """
        subdivisor = self._seleccionar_subdivisor(solicitud.tipo)
        problemas = solicitud.validar()
        if problemas:
            raise SolicitudInvalida(problemas)
        terreno = solicitud.terreno
        p = solicitud.parametros

        # 1. Lo fijado, exacto en el marco de la alternativa.
        alternativa, terreno_alt, corredores_fijos, manzanas_fijas, sector_alt, restante_alt, reservadas_alt = (
            self._en_su_marco(terreno, fijados, solicitud.reservadas)
        )
        marco = MarcoLocal.para(terreno, solicitud.estrategia.orientacion)
        mismo = marco == alternativa
        sector_global = alternativa.a_global(sector_alt)

        # 2. La red nueva, en el marco de la estrategia, integrada con la fijada.
        def a_construccion(geometria):
            return geometria if mismo else marco.a_local(alternativa.a_global(geometria))

        def a_alternativa(geometria):
            return geometria if mismo else alternativa.a_local(marco.a_global(geometria))

        if mismo:
            dominio_local, restante_local, reservadas_local = terreno_alt, restante_alt, reservadas_alt
        else:
            dominio_local = ajustar(marco.a_local(terreno))
            reservadas_local = self._reservadas_en(marco, dominio_local, solicitud.reservadas)
            restante_local = superficie(diferencia(dominio_local, marco.a_local(sector_global)))
            if reservadas_local:
                restante_local = superficie(diferencia(restante_local, union(reservadas_local)))
        # Para trazar, sin astillas ni ranuras: con otra orientación, el sector y el terreno ajustados a
        # otra grilla dejan tiras de menos de un milímetro entre los dos, que no son dominio. Una
        # apertura de medio centímetro (con inglete, así las esquinas quedan) las borra. El cierre, en
        # el marco de la alternativa, usa el dominio restante exacto y se las da a sus vecinas.
        restante_local = sin_astillas(restante_local)
        contexto = superficie(union([a_construccion(c) for c in corredores_fijos if not c.is_empty]))
        accesos_locales = [marco.a_local(acceso) for acceso in solicitud.accesos]
        fija = RedFija(
            tramos=tuple((marco.a_local(t.eje), t.jerarquia) for t in fijados.tramos),
            anclajes=tuple(marco.a_local(a) for a in fijados.anclajes),
            terreno=dominio_local,
            sector=a_construccion(sector_alt),
            # Las filas de la v1 en el marco de la grilla nueva: los lados con calle de borde son los de
            # la versión de origen (D86).
            filas_origen=math.radians(fijados.orientacion_marco - solicitud.estrategia.orientacion),
        )
        try:
            generada = self._generador_red.generar_con_avenidas(
                restante_local, accesos_locales, solicitud.estrategia, p, solicitud.jerarquias, fija,
                reservadas=reservadas_local,
            )
        except ErrorConectividad as error:
            geometria = marco.a_global(error.geometria) if error.geometria is not None else sector_global
            raise ErrorConectividad(error.causa, error.sugerencia, geometria) from error
        red, motivo_avenidas = generada.red, generada.motivo
        self._exigir_red_integrada(red, accesos_locales, marco, sector_global)

        # 3. Corredores y manzanas nuevos, y su subdivisión con la circulación completa.
        corredores = self._materializador.materializar(
            red,
            solicitud.jerarquias,
            restante_local,
            contexto,
            limite_con_calle(dominio_local, reservadas_local),
            reservadas_local,
            _entrantes(dominio_local, p),
        )
        tramos = red.tramos()
        nuevos = [i for i, tramo in enumerate(tramos) if not tramo.fijado]
        circulacion_nueva = superficie(union([corredores[i] for i in nuevos]))
        circulacion_total = superficie(union([circulacion_nueva, contexto]))
        # 5.a también si una parte del dominio restante no toca ninguna calle, fijada ni nueva: la red
        # nueva no llegó a ella (no tiene accesos ni anclajes), y lo que se genere ahí no tendría frente.
        sin_calle = [parte for parte in poligonos(restante_local) if parte.distance(circulacion_total) > TOLERANCIA]
        if sin_calle:
            area = math.fsum(parte.area for parte in sin_calle)
            raise ErrorConectividad(
                f"El sector recalculado no se puede conectar con el fijado: {len(sin_calle)} parte(s) del terreno "
                f"({area:.0f} m²) no tocan ninguna calle, fijada ni nueva.",
                SUGERENCIA_SIN_CONEXION,
                marco.a_global(MultiPolygon(sin_calle)),
            )
        manzanas_nuevas = poligonos(diferencia(restante_local, circulacion_nueva))
        piezas: list[CeldaGenerada] = []
        for indice, manzana in enumerate(manzanas_nuevas, 1):
            if not alcanza_lado_menor(manzana, p):
                piezas.append(_sin_lotes(manzana, indice))
                continue
            frentes = subdivisor.identificar_frentes(manzana, circulacion_total)
            piezas += subdivisor.subdividir(manzana, frentes, p, indice)
        piezas = self._subdividir_grandes(subdivisor, piezas, circulacion_total, red, p)

        # 4. El cierre en el marco de la alternativa, con lo fijado (`geometria.cerrar_con_fijas`):
        # un solo arreglo plano sobre el terreno, sin mover lo fijado.
        # Las manzanas fijadas quedan afuera del arreglo: están rodeadas de calles fijadas, y sus
        # celdas no se tocan (vuelven tal cual a la grilla de la alternativa).
        celdas_fijas_alt = [restaurar(alternativa.a_local(c.geometria)) for c in fijados.celdas]
        piezas = [replace(pieza, geometria=a_alternativa(pieza.geometria)) for pieza in piezas]
        nuevas = [a_alternativa(corredores[i]) for i in nuevos] + [pieza.geometria for pieza in piezas]
        # El dominio del arreglo es el de las calles fijadas más el restante: hacia las manzanas, su
        # borde es exactamente el de los corredores (con sus vértices). Las áreas reservadas entran
        # como piezas fijas, igual que al generar (D59).
        arreglo = superficie(
            union_cobertura([*reservadas_alt, *(c for c in corredores_fijos if not c.is_empty), restante_alt])
        )
        fijas, nuevas = cerrar_con_fijas(arreglo, [*reservadas_alt, *corredores_fijos], nuevas)
        reservadas_cerradas, corredores_fijos = fijas[: len(reservadas_alt)], fijas[len(reservadas_alt) :]
        cerrados = nuevas[: len(nuevos)]
        partidas, cerrados = _repartir_astillas(piezas, nuevas[len(nuevos) :], list(cerrados))
        con_piezas = sorted({pieza.indice_manzana for pieza in partidas})
        renumeradas = {indice: k for k, indice in enumerate(con_piezas, 1)}
        piezas = [replace(pieza, indice_manzana=renumeradas[pieza.indice_manzana]) for pieza in partidas]
        manzanas_nuevas = [
            union_cobertura([pieza.geometria for pieza in piezas if pieza.indice_manzana == k])
            for k in range(1, len(con_piezas) + 1)
        ]

        # 5. Al sistema de cálculo: la red integrada y un corredor por tramo.
        red_global, corredores_globales = self._integrar_resultado(
            red, marco, alternativa, fijados, fija, corredores_fijos, dict(zip(nuevos, cerrados, strict=True))
        )
        circulacion_global = union_cobertura(corredores_globales)
        ejes = IndiceEjes([tramo.eje for tramo in red_global.tramos()])

        # Las manzanas: las fijadas conservan su designación y las nuevas toman los números libres,
        # en el orden estable de siempre. El resultado las ordena por número.
        ocupados = {_numero_de(m.designacion) for m in fijados.manzanas}
        libres = (n for n in itertools.count(1) if n not in ocupados)
        entradas = [
            (_numero_de(m.designacion), m.designacion, alternativa.a_global(g), ("fija", k))
            for k, (m, g) in enumerate(zip(fijados.manzanas, manzanas_fijas, strict=True))
        ]
        for k, manzana in enumerate(manzanas_nuevas, 1):
            numero = next(libres)
            entradas.append((numero, f"M{numero}", alternativa.a_global(manzana), ("nueva", k)))
        entradas.sort(key=lambda entrada: entrada[0])
        posicion = {origen: k for k, (_, _, _, origen) in enumerate(entradas, 1)}
        designaciones = tuple(nombre for _, nombre, _, _ in entradas)
        manzanas = tuple(geometria for _, _, geometria, _ in entradas)
        de_fija = {m.designacion: posicion[("fija", k)] for k, m in enumerate(fijados.manzanas)}
        celdas_fijas = [
            replace(
                celda, geometria=alternativa.a_global(geometria), indice_manzana=de_fija[celda.designacion.split("-")[0]]
            )
            for celda, geometria in zip(fijados.celdas, celdas_fijas_alt, strict=True)
        ]
        celdas_nuevas = self._clasificador.clasificar(
            [
                replace(
                    pieza,
                    geometria=alternativa.a_global(pieza.geometria),
                    indice_manzana=posicion[("nueva", pieza.indice_manzana)],
                )
                for pieza in piezas
            ],
            circulacion_global,
            ejes,
            p,
            designaciones,
        )
        resultado = ResultadoGeneracion(
            red=red_global,
            corredores=corredores_globales,
            manzanas=manzanas,
            celdas=(*celdas_fijas, *celdas_nuevas),
            designaciones=designaciones,
            reservadas=tuple(alternativa.a_global(area) for area in reservadas_cerradas),
        )
        if not resultado.lotes:
            raise TerrenoSinLotes(
                f"En el trazado no queda ningún lote que cumpla los mínimos (frente {p.frente_minimo:g} m, "
                f"fondo {p.fondo_minimo:g} m y superficie {p.superficie_minima:g} m²).",
                SUGERENCIA_SIN_LOTES,
            )
        motivo_cesion = None
        if self._asignador is not None:
            convertibles = frozenset(posicion[("nueva", k)] for k in range(1, len(manzanas_nuevas) + 1))
            asignacion = self._asignador.asignar(
                resultado.celdas, resultado.manzanas, circulacion_global, red_global, ejes, p, convertibles, designaciones
            )
            resultado = replace(resultado, celdas=asignacion.celdas)
            motivo_cesion = asignacion.motivo
        incumplimientos = self._verificador.verificar(resultado, p, solicitud.accesos, motivo_cesion, motivo_avenidas)
        resultado = replace(resultado, incumplimientos=tuple(incumplimientos))
        indicadores = self._calculador.calcular(resultado, terreno.area, solicitud.accesos, p)
        return replace(resultado, indicadores=indicadores)

    def exigir_dominio_restante(self, terreno: Polygon, fijados: ElementosFijados, reservadas=()) -> None:
        """Curso 3.a del CU09: `SinDominioRestante` si lo fijado (y las áreas reservadas) abarcan todo
        el terreno. Es la misma cuenta del recálculo; la API la usa para la vista previa del sector."""
        self._en_su_marco(terreno, fijados, reservadas)

    def _en_su_marco(self, terreno: Polygon, fijados: ElementosFijados, reservadas=()):
        """Lo fijado en el marco de la alternativa, exacto en la grilla de 1 mm donde se cerró (D56):
        el marco, el terreno, los corredores y las manzanas fijados, el sector, el dominio restante y
        las áreas reservadas, que el dominio restante descuenta (D59). `SinDominioRestante` si no
        queda nada (3.a)."""
        alternativa = MarcoLocal.para(terreno, fijados.orientacion_marco)
        terreno_alt = ajustar(alternativa.a_local(terreno))
        corredores = [restaurar(alternativa.a_local(t.corredor)) for t in fijados.tramos]
        manzanas = [restaurar(alternativa.a_local(m.geometria)) for m in fijados.manzanas]
        sector = superficie(union_cobertura([*manzanas, *(c for c in corredores if not c.is_empty)]))
        restante = superficie(diferencia(terreno_alt, sector))
        areas = self._reservadas_en(alternativa, terreno_alt, reservadas)
        if areas:
            restante = superficie(diferencia(restante, union(areas)))
        if not poligonos(restante):
            raise SinDominioRestante(
                "Lo fijado abarca todo el terreno: no queda área para recalcular.",
                "Soltá alguna manzana: el recálculo genera solo lo que no está fijado.",
            )
        return alternativa, terreno_alt, corredores, manzanas, sector, restante, areas

    def fijar(self, origen: ResultadoGeneracion, manzanas, orientacion_marco: float) -> ElementosFijados:
        """Lo que se conserva de una versión al fijar estas manzanas (CU09, el `armarFijados` de la
        p. 47; D56). Es la copia única de la regla de qué se fija:

        - cada manzana elegida, entera, con sus celdas;
        - los tramos cuyo corredor comparte un lado con ella, así ningún lote pierde su frente, y los
          tramos cuyo eje queda dentro de esa superficie (los que no tienen corredor propio);
        - el sector: la unión de esas manzanas y esos corredores;
        - los anclajes: los nodos de la red fijada donde un tramo no fijado seguía.

        `origen` es la versión de origen, en el sistema de cálculo; `manzanas`, las designaciones.
        Da `SolicitudInvalida` si no hay ninguna o si alguna no existe.
        """
        designaciones = [origen.designacion_manzana(k) for k in range(1, len(origen.manzanas) + 1)]
        pedidas = list(dict.fromkeys(manzanas))
        if not pedidas:
            raise SolicitudInvalida([Problema("manzanas", "Elegí al menos una manzana para fijar.")])
        faltan = [d for d in pedidas if d not in designaciones]
        if faltan:
            raise SolicitudInvalida([Problema("manzanas", f"La versión no tiene la manzana «{d}».") for d in faltan])
        indices = sorted(designaciones.index(d) + 1 for d in pedidas)
        tramos = origen.red.tramos()
        elegidos: set[int] = set()
        for k in indices:
            borde = origen.manzanas[k - 1].boundary
            for i, corredor in enumerate(origen.corredores):
                # Un lado compartido, por corto que sea, no un vértice: el cruce que solo toca la
                # esquina no cuenta. La partición es una cobertura exacta (D39): un lado compartido
                # tiene los mismos vértices en las dos piezas, también después de pasar por la base.
                if not corredor.is_empty and borde.intersection(corredor.boundary).length > LADO_COMPARTIDO:
                    elegidos.add(i)
        calles = union_cobertura([origen.corredores[i] for i in sorted(elegidos)])
        if not calles.is_empty:
            cubierta = calles.buffer(TOLERANCIA)
            elegidos |= {i for i, tramo in enumerate(tramos) if cubierta.covers(tramo.eje)}
        fijos = sorted(elegidos)
        extremos: dict = {}
        for i in fijos:
            for nodo, punto in (
                (tramos[i].origen, tramos[i].eje.coords[0]),
                (tramos[i].destino, tramos[i].eje.coords[-1]),
            ):
                extremos.setdefault(nodo, punto)
        anclajes = [
            Point(extremos[nodo])
            for nodo in sorted(extremos)
            if any(i not in elegidos for i, t in enumerate(tramos) if nodo in (t.origen, t.destino))
        ]
        piezas = [origen.manzanas[k - 1] for k in indices] + [
            origen.corredores[i] for i in fijos if not origen.corredores[i].is_empty
        ]
        en_manzana = set(indices)
        return ElementosFijados(
            sector=_multipoligono(union_cobertura(piezas)),
            celdas=tuple(c for c in origen.celdas if c.indice_manzana in en_manzana),
            tramos=tuple(TramoFijado(tramos[i].eje, tramos[i].jerarquia, origen.corredores[i]) for i in fijos),
            anclajes=tuple(anclajes),
            manzanas=tuple(ManzanaFijada(designaciones[k - 1], origen.manzanas[k - 1]) for k in indices),
            orientacion_marco=float(orientacion_marco),
        )

    def _exigir_red_integrada(self, red, accesos, marco: MarcoLocal, sector) -> None:
        """Curso 5.a del CU09 (p. 44): si la red nueva no se conecta con la fijada, o algún acceso
        quedó sin calle, no hay recálculo (D56)."""
        sin_calle = [f"A{k}" for k, acceso in enumerate(accesos, 1) if not red.servido(acceso)]
        aisladas = red.componentes_aisladas()
        if not sin_calle and not aisladas:
            return
        ejes = [tramo.eje for nodos in aisladas for tramo in red.tramos_de(nodos)]
        if aisladas:
            causa = (
                "El sector recalculado no se puede conectar con el fijado: la red quedó partida en "
                f"{len(aisladas) + 1} partes que no se conectan entre sí."
            )
        else:
            causa = f"Los accesos {', '.join(sin_calle)} no abren a ninguna calle de la red integrada."
        geometria = marco.a_global(MultiLineString(ejes)) if ejes else sector
        raise ErrorConectividad(causa, SUGERENCIA_SIN_CONEXION, geometria)

    def _integrar_resultado(self, red, marco, alternativa, fijados, fija, corredores_fijos, corredores_nuevos):
        """La red integrada en el sistema de cálculo, y el corredor de cada tramo en su orden.

        Un tramo fijado entero conserva su corredor; su eje sale de las claves de sus nodos, como el de
        todos los tramos: con la misma orientación es exactamente el de origen, y con otra difiere en
        menos de 1 mm (la API guarda el de origen). Uno que se partió en un empalme da dos tramos
        fijados sobre el mismo eje: la
        superficie entera queda en el que contiene el punto medio del eje original y el otro no tiene
        superficie propia, como un tramo dentro de un cruce (D28, D56)."""
        originales = {}
        for k, (eje_local, _) in enumerate(fija.tramos):
            clave = tuple(sorted((red.nodo(eje_local.coords[0]), red.nodo(eje_local.coords[-1]))))
            originales[clave] = k
        red_global = RedCirculacion()
        corredor_de = {}
        dueno: dict[int, int] = {}
        for i, tramo in enumerate(red.tramos()):
            # Todos los ejes salen de las claves de sus nodos, como al generar: así los tramos que se
            # tocan comparten el nodo también en el sistema de cálculo. Con la misma orientación, un
            # tramo fijado entero vuelve exacto a su eje de origen.
            eje = marco.a_global(LineString([tramo.origen, tramo.destino]))
            if tramo.fijado and (tramo.origen, tramo.destino) in originales:
                k = originales[(tramo.origen, tramo.destino)]
                corredor = alternativa.a_global(corredores_fijos[k])
            elif tramo.fijado:
                medio = [
                    k
                    for k, (eje_local, _) in enumerate(fija.tramos)
                    if k not in dueno
                    and eje_local.distance(tramo.eje.interpolate(0.5, normalized=True)) <= TOLERANCIA
                    and tramo.eje.distance(eje_local.interpolate(0.5, normalized=True)) <= TOLERANCIA
                ]
                if medio:
                    dueno[medio[0]] = i
                    corredor = alternativa.a_global(corredores_fijos[medio[0]])
                else:
                    corredor = Polygon()
            else:
                corredor = alternativa.a_global(corredores_nuevos[i])
            agregado = red_global.agregar_tramo(eje.coords[0], eje.coords[-1], eje, tramo.jerarquia, tramo.fijado)
            if agregado is not None:
                corredor_de[(agregado.origen, agregado.destino)] = corredor
        return red_global, tuple(corredor_de[(t.origen, t.destino)] for t in red_global.tramos())

    def sugerir_estrategia(self, terreno: Polygon) -> Estrategia:
        """La estrategia que la pantalla propone antes de generar (p. 43, paso 1; D42): grilla
        orientada según `GeneradorRed.orientacion_sugerida` y la semilla de la p. 49."""
        return Estrategia(PatronRed.GRILLA, GeneradorRed.orientacion_sugerida(terreno), SEMILLA_SUGERIDA)

    def _seleccionar_subdivisor(self, tipo: TipoProyecto) -> Subdivisor:
        subdivisor = self._subdivisores.get(tipo)
        if subdivisor is None:
            if tipo == TipoProyecto.ESTACIONAMIENTO:
                raise NoImplementado(
                    "La generación de playas de estacionamiento todavía no está implementada."
                )
            raise NoImplementado(f"La generación para proyectos de tipo «{tipo}» no está implementada.")
        return subdivisor

    def _preparar_dominio(self, terreno, reservadas):
        """Dominio de trabajo: el terreno menos las áreas reservadas (CU06, paso 4; D59), en el marco
        local. Es el `prepararDominio(terreno, reservadas)` de la p. 47.

        Cualquier polígono válido sirve (D40). Con áreas, el dominio puede tener agujeros (un área en
        el medio) o estar en piezas, y pierde las astillas: un área a centímetros del borde o de otra
        no deja una tira de dominio entre las dos (`geometria.sin_astillas`). Esas tiras no se
        pierden: el cierre se las da a una pieza vecina.
        """
        if not reservadas:
            return terreno
        return sin_astillas(superficie(diferencia(terreno, union(reservadas))))

    @staticmethod
    def _reservadas_en(marco: MarcoLocal, terreno, reservadas) -> list:
        """Las áreas reservadas en el marco local: en la grilla de 1 mm, como el terreno, y recortadas a
        él (la validación admite que lo excedan en menos de 1 cm)."""
        return [superficie(interseccion(ajustar(marco.a_local(area)), terreno)) for area in reservadas]

    def _subdividir_grandes(self, subdivisor: Subdivisor, piezas, circulacion, red, p) -> list[CeldaGenerada]:
        """Parte cada lote grande en lotes que cumplan todo, si se puede (D47, camino 1).

        Corre antes de cerrar la partición, en el marco local donde se construye: un corte
        después del cierre metería vértices que las piezas vecinas no tienen. Se mide como el
        verificador (`medir` sobre los corredores y los ejes locales), y vale la primera forma de
        `Subdivisor.redividir` cuyas partes son todas lotes sin pasar la superficie máxima. Si no
        hay ninguna, el lote queda entero: el asignador lo convierte primero en verde (D46), o
        queda como lote grande.
        """
        ejes = IndiceEjes([tramo.eje for tramo in red.tramos()])

        def es_lote_chico(geometria) -> bool:
            return not es_lote_grande(geometria, p) and es_lote(geometria, medir(geometria, circulacion, ejes), p)

        resultado = []
        for pieza in piezas:
            g = pieza.geometria
            formas = []
            if pieza.tipo is TipoCelda.LOTE and es_lote_grande(g, p) and es_lote(g, medir(g, circulacion, ejes), p):
                formas = subdivisor.redividir(g, circulacion, p)
            partes = next((forma for forma in formas if all(es_lote_chico(parte) for parte in forma)), None)
            resultado += [replace(pieza, geometria=parte) for parte in partes] if partes else [pieza]
        return resultado

    def _cerrar(self, terreno, corredores, piezas: list[CeldaGenerada], cantidad_manzanas: int, reservadas=()):
        """Cierra la partición (D39) y rearma cada manzana como la unión de sus piezas.

        Si el cierre dejara una pieza en dos partes, no se pierde ninguna: cada parte sigue
        como pieza de su manzana y el clasificador decide qué es.

        Una manzana astilla puede quedarse sin caras: el cierre se las da a sus vecinas, que ya
        cubren esa superficie. Esa manzana desaparece y las demás se renumeran, así toda manzana
        tiene celdas (lo encontró el barrido de 96 terrenos de la sesión 6: el triángulo de 24°
        con la grilla a 75°).

        Con áreas reservadas (D59), el cierre es el del recálculo (`cerrar_con_fijas`) sobre el
        terreno entero, con las áreas como piezas fijas: conservan su forma y solo suman puntos sobre
        sus lados. Las partes de menos de `AREA_RUIDO` que deja se suman a una vecina
        (`_repartir_astillas`). Devuelve también las áreas cerradas.
        """
        if reservadas:
            fijas, nuevas = cerrar_con_fijas(terreno, list(reservadas), [*corredores, *(p.geometria for p in piezas)])
            piezas_cerradas, corredores_cerrados = _repartir_astillas(
                piezas, nuevas[len(corredores) :], list(nuevas[: len(corredores)])
            )
        else:
            fijas = []
            cerradas = cerrar_particion(terreno, [*corredores, *(p.geometria for p in piezas)])
            corredores_cerrados = cerradas[: len(corredores)]
            piezas_cerradas = []
            for pieza, geometria in zip(piezas, cerradas[len(corredores) :], strict=True):
                piezas_cerradas += [replace(pieza, geometria=parte) for parte in poligonos(geometria)]
        manzanas, nuevo_indice = [], {}
        for indice in range(1, cantidad_manzanas + 1):
            partes = [p.geometria for p in piezas_cerradas if p.indice_manzana == indice]
            if partes:
                nuevo_indice[indice] = len(manzanas) + 1
                manzanas.append(union_cobertura(partes))
        piezas_cerradas = [replace(p, indice_manzana=nuevo_indice[p.indice_manzana]) for p in piezas_cerradas]
        return corredores_cerrados, piezas_cerradas, manzanas, fijas

    def _exigir_red_conexa(self, red, accesos, marco: MarcoLocal) -> None:
        """Alternativa de la secuencia (p. 43): sin red conexa con los accesos no hay alternativa."""
        sin_calle = [f"A{k}" for k, acceso in enumerate(accesos, 1) if not red.servido(acceso)]
        if sin_calle:
            raise ErrorConectividad(
                f"Los accesos {', '.join(sin_calle)} no abren a ninguna calle de la red.",
                SUGERENCIA,
                marco.a_global(MultiPoint([accesos[int(a[1:]) - 1] for a in sin_calle])),
            )
        aisladas = red.componentes_aisladas()
        if aisladas:
            ejes = [tramo.eje for nodos in aisladas for tramo in red.tramos_de(nodos)]
            raise ErrorConectividad(
                f"La red quedó partida en {len(aisladas) + 1} partes que no se conectan entre sí.",
                SUGERENCIA,
                marco.a_global(MultiLineString(ejes)),
            )


def _repartir_astillas(piezas, geometrias, corredores):
    """Las piezas nuevas de un recálculo separadas en partes, sin perder ninguna: una parte de menos
    de `AREA_RUIDO` (una astilla del cierre entre dos grillas) se suma a la pieza nueva o al corredor
    nuevo con el que comparte más borde, en lugar de descartarse y dejar una grieta (D56)."""
    partidas, astillas = [], []
    for pieza, geometria in zip(piezas, geometrias, strict=True):
        partes = sorted(
            (p for p in shapely.get_parts(geometria) if isinstance(p, Polygon) and not p.is_empty),
            key=lambda p: (-round(p.area, 9), clave_poligono(p)),
        )
        if not partes:
            continue
        grandes = [p for p in partes if p.area >= AREA_RUIDO] or partes[:1]
        partidas += [replace(pieza, geometria=p) for p in grandes]
        astillas += [p for p in partes if p not in grandes]
    for astilla in sorted(astillas, key=clave_poligono):
        vecinas = [
            (round(astilla.boundary.intersection(c.geometria.boundary).length, 9), 0, k)
            for k, c in enumerate(partidas)
        ] + [
            (round(astilla.boundary.intersection(c.boundary).length, 9), 1, k)
            for k, c in enumerate(corredores)
            if not c.is_empty
        ]
        largo, es_corredor, k = max(vecinas, key=lambda v: (v[0], -v[1], -v[2]), default=(0, 0, -1))
        if largo <= 0:
            continue
        if es_corredor:
            corredores[k] = superficie(union_cobertura([corredores[k], astilla]))
        else:
            unida = union_cobertura([partidas[k].geometria, astilla])
            if isinstance(unida, Polygon):
                partidas[k] = replace(partidas[k], geometria=unida)
    return partidas, corredores


def _numero_de(designacion: str) -> int:
    """«M6» → 6."""
    return int(designacion.lstrip("M"))


def _multipoligono(geometria) -> MultiPolygon:
    if isinstance(geometria, MultiPolygon):
        return geometria
    return MultiPolygon(poligonos(geometria))


def _entrantes(terreno: Polygon, p: ParametrosLoteo) -> list:
    """Los lados de una entrante del terreno, cuya calle se alinea con la grilla si la calle de borde va
    por lado (D86): los corredores la llevan hasta el límite aunque el lado se aparte un poco."""
    return lados_entrantes(terreno) if p.calle_borde == CalleBorde.POR_LADO else []


def _sin_lotes(manzana: Polygon, indice: int) -> CeldaGenerada:
    """La pieza de una manzana que no alcanza el lado menor del art. 48 (D50): la manzana entera,
    que no es un lote candidato. Sale como espacio libre y el clasificador la vuelve verde si cumple
    los criterios del verde (D41). Ese verde no computa para la cesión (D55)."""
    return CeldaGenerada(
        geometria=manzana,
        tipo=TipoCelda.ESPACIO_LIBRE,
        frente=0.0,
        fondo=0.0,
        indice_manzana=indice,
        designacion=f"M{indice}-EL01",
    )
