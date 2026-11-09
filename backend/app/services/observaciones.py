"""Registrar y responder observaciones (CU11, CU12, RF17; pantalla de la p. 50; D69).

- **Registrar (CU11):** sobre la versión vigente de una alternativa, con tipo, criticidad, detalle y,
  opcionalmente, el sector afectado. Queda `abierta` y la alternativa pasa a `observada`. Un sector que
  excede el terreno da 422 con la parte que sale (3.a), para dibujarlo de nuevo.
- **Responder (CU12):** con un comentario (3.b: justificación o aclaración) o con un recálculo (3.a, que
  ejecuta el CU09). El recálculo y la respuesta se guardan en la misma transacción: la respuesta queda
  vinculada a la versión que resultó, y si el motor no puede, no queda ni la versión ni la respuesta. La
  observación pasa a `respondida`.
- **Cerrar y reabrir** (`cerrar()`, `reabrir()`, p. 46): la conformidad del emisor (Anexo 1.5), solo
  sobre una respondida. Cerrada es final; reabierta vuelve a bloquear.

**El estado de la alternativa** cambia acá con cada observación (D69): registrar o reabrir la pasa a
`observada` (y la saca de la selección); responder la última abierta la vuelve a `generada`. Cada
operación bloquea primero la fila de la alternativa: dos cambios simultáneos no se pisan.
"""

from dataclasses import dataclass

from motor_trazados import coordenadas
from motor_trazados.exportar import geojson_geografico
from motor_trazados.geometria import TOLERANCIA, TOLERANCIA_AREA
from shapely import Polygon
from shapely.geometry.base import BaseGeometry
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import reloj
from app.core.errores import ErrorApi
from app.core.permisos import DESCRIPCIONES, NOMBRES_ROL, Funcion, permite
from app.models import Alternativa, Observacion, Proyecto, RespuestaObservacion, Usuario, VersionAlternativa
from app.models.alternativa import EstadoAlternativa
from app.models.observacion import AccionRespuesta, EstadoObservacion, abiertas, de_la_alternativa, designaciones
from app.schemas.comunes import PoligonoGeoJSON
from app.schemas.observacion import (
    EstadoObservacionIn,
    ObservacionIn,
    ObservacionOut,
    RespuestaIn,
    RespuestaOut,
    SectorIn,
    SectorMedidoOut,
)
from app.schemas.recalculo import RecalculoIn
from app.services import fijacion
from app.services.conversiones import geojson, guardable, leida
from app.services.generacion import ServicioGeneracion, obtener_alternativa
from app.services.proyectos import resumen_usuario

NOMBRES_ESTADO = {
    EstadoObservacion.ABIERTA: "abierta",
    EstadoObservacion.RESPONDIDA: "respondida",
    EstadoObservacion.CERRADA: "cerrada",
}


# --- Consultar ------------------------------------------------------------------------------------


def obtener(db: Session, id_observacion: int) -> Observacion:
    observacion = db.get(Observacion, id_observacion)
    if observacion is None:
        raise ErrorApi(404, f"No existe la observación {id_observacion}.")
    return observacion


def listar(db: Session, id_alternativa: int) -> list[ObservacionOut]:
    """Las observaciones de todas las versiones de la alternativa, en el orden en que se registraron
    (CU12, paso 1: «el listado de la alternativa»)."""
    alternativa = obtener_alternativa(db, id_alternativa)
    nombres = designaciones(alternativa)
    return [_presentar(o, nombres[o.id_observacion]) for o in de_la_alternativa(alternativa)]


def presentar(observacion: Observacion) -> ObservacionOut:
    return _presentar(observacion, designaciones(observacion.version.alternativa)[observacion.id_observacion])


def _presentar(observacion: Observacion, designacion: str) -> ObservacionOut:
    return ObservacionOut(
        id_observacion=observacion.id_observacion,
        designacion=designacion,
        id_version=observacion.id_version,
        numero_version=observacion.version.numero,
        tipo=observacion.tipo,
        criticidad=observacion.criticidad,
        descripcion=observacion.descripcion,
        sector=geojson(observacion.sector),
        estado=observacion.estado,
        emisor=resumen_usuario(observacion.emisor),
        fecha_emision=observacion.fecha_emision,
        fecha_cierre=observacion.fecha_cierre,
        respuestas=[
            RespuestaOut(
                id_respuesta=r.id_respuesta,
                accion=r.accion,
                descripcion=r.descripcion,
                usuario=resumen_usuario(r.usuario),
                fecha=r.fecha,
                id_version_resultante=r.id_version_resultante,
                numero_version_resultante=None if r.version_resultante is None else r.version_resultante.numero,
            )
            for r in observacion.respuestas
        ],
    )


# --- Registrar (CU11) -------------------------------------------------------------------------------


def registrar(db: Session, id_version: int, datos: ObservacionIn, usuario: Usuario) -> Observacion:
    """CU11, paso 5: la observación `abierta` sobre la versión vigente, y la alternativa `observada`."""
    version = fijacion.obtener_version(db, id_version)
    alternativa = version.alternativa
    _bloquear(db, alternativa)
    vigente = _vigente(db, alternativa)
    if vigente.id_version != version.id_version:
        raise ErrorApi(
            409,
            f"La versión {version.numero} no es la vigente de la alternativa {alternativa.codigo}.",
            f"Las observaciones se registran sobre la versión vigente, la {vigente.numero}.",
        )
    sector = None if datos.sector is None else validar_sector(alternativa.proyecto, datos.sector)
    observacion = Observacion(
        version=version,
        emisor=usuario,
        tipo=datos.tipo,
        criticidad=datos.criticidad,
        descripcion=datos.descripcion,
        sector=None if sector is None else guardable(sector),
        estado=EstadoObservacion.ABIERTA,
    )
    db.add(observacion)
    alternativa.estado = EstadoAlternativa.OBSERVADA
    db.commit()
    return observacion


@dataclass(frozen=True)
class _SectorMedido:
    poligono: Polygon  # en 4326, con la precisión completa
    superficie: float | None  # en m²; None si el polígono no es válido
    problema: str | None  # el mensaje del campo `sector`; None si sirve
    afuera: BaseGeometry | None  # en metros, la parte que sale del terreno


def _medir_sector(proyecto: Proyecto, sector: PoligonoGeoJSON) -> _SectorMedido:
    """El sector, medido en metros con la tolerancia del motor (1 cm), como las áreas reservadas: puede
    tocar el borde del terreno, no salir de él. La misma medida para registrar y para la vista previa."""
    srid = proyecto.srid_calculo
    poligono = sector.a_shapely()
    metros = coordenadas.a_metros(poligono, srid)
    if not metros.is_valid:
        return _SectorMedido(poligono, None, "El polígono no es válido (¿se cruza a sí mismo?).", None)
    if metros.area <= TOLERANCIA_AREA:
        return _SectorMedido(poligono, metros.area, "El polígono no tiene superficie.", None)
    terreno = coordenadas.a_metros(leida(proyecto.terreno.geom), srid)
    if not terreno.buffer(TOLERANCIA).covers(metros):
        afuera = metros.difference(terreno)
        return _SectorMedido(poligono, metros.area, f"Sale del terreno: {_m2(afuera.area)} afuera.", afuera)
    return _SectorMedido(poligono, metros.area, None, None)


def validar_sector(proyecto: Proyecto, sector: PoligonoGeoJSON) -> Polygon:
    """El sector afectado, en 4326 y con la precisión completa, si es un polígono válido dentro del
    terreno. Si sale, 422 con la parte de afuera, para que el portal la muestre (CU11, 3.a: «para que
    dibuje nuevamente»)."""
    medido = _medir_sector(proyecto, sector)
    if medido.afuera is not None:
        raise ErrorApi(
            422,
            "El sector dibujado excede el límite del terreno.",
            "Dibujalo de nuevo dentro del polígono del terreno: la parte que sale está marcada en el mapa.",
            [("sector", medido.problema)],
            geometria=geojson_geografico(coordenadas.a_geograficas(medido.afuera, proyecto.srid_calculo)),
        )
    if medido.problema is not None:
        raise _sector_invalido(medido.problema)
    return medido.poligono


def vista_previa_sector(db: Session, id_version: int, datos: SectorIn) -> SectorMedidoOut:
    """`POST /versiones/{id}/observaciones/sector`: el sector que se está dibujando, medido como al
    registrarlo (figura 19; D79), sin registrar nada: su superficie y, si sale del terreno, cuánto y dónde
    (CU11, 3.a)."""
    proyecto = fijacion.obtener_version(db, id_version).alternativa.proyecto
    medido = _medir_sector(proyecto, datos.sector)
    afuera = medido.afuera
    return SectorMedidoOut(
        superficie_m2=None if medido.superficie is None else round(medido.superficie, 2),
        afuera_m2=0.0 if afuera is None else round(afuera.area, 2),
        afuera=None
        if afuera is None
        else geojson_geografico(coordenadas.a_geograficas(afuera, proyecto.srid_calculo)),
        problema=medido.problema,
    )


def _sector_invalido(mensaje: str) -> ErrorApi:
    return ErrorApi(422, "El sector dibujado no sirve.", "Dibujalo de nuevo sobre el mapa.", [("sector", mensaje)])


# --- Responder (CU12) -------------------------------------------------------------------------------


def responder(db: Session, id_observacion: int, datos: RespuestaIn, usuario: Usuario) -> Observacion:
    """CU12, paso 5: registra la respuesta y marca la observación `respondida`. Con un recálculo (3.a),
    corre el CU09 sobre la versión vigente y vincula la respuesta con la versión n + 1, todo en una
    transacción. Si con eso no queda ninguna abierta, la alternativa vuelve a `generada` (D69)."""
    observacion = obtener(db, id_observacion)
    alternativa = observacion.version.alternativa
    _bloquear(db, alternativa)
    db.refresh(observacion)
    nombre = designaciones(alternativa)[observacion.id_observacion]
    if observacion.estado != EstadoObservacion.ABIERTA:
        raise ErrorApi(
            409,
            f"La observación {nombre} ya está {NOMBRES_ESTADO[EstadoObservacion(observacion.estado)]}.",
            "Solo se responde una observación abierta. Si la respuesta no alcanzó, el director técnico la "
            "puede reabrir.",
        )
    con_recalculo = datos.accion == AccionRespuesta.RECALCULO_PARCIAL
    if con_recalculo and datos.recalculo is None:
        raise ErrorApi(
            422,
            "Una respuesta con recálculo lleva el recálculo.",
            "Elegí las manzanas que se conservan y la estrategia, como al fijar sectores (CU09).",
            [("recalculo", "Falta este dato.")],
        )
    if not con_recalculo and datos.recalculo is not None:
        raise ErrorApi(
            422,
            "Solo una respuesta con recálculo lleva un recálculo.",
            "Una justificación o una aclaración se responde con el comentario (CU12, 3.b).",
            [("recalculo", "Este campo no se admite con esta acción.")],
        )
    resultante = None
    if con_recalculo:
        resultante = _recalcular(db, alternativa, datos, usuario)
    db.add(
        RespuestaObservacion(
            observacion=observacion,
            usuario=usuario,
            accion=datos.accion,
            descripcion=datos.descripcion,
            version_resultante=resultante,
        )
    )
    observacion.estado = EstadoObservacion.RESPONDIDA
    if alternativa.estado == EstadoAlternativa.OBSERVADA and not abiertas(alternativa):
        alternativa.estado = EstadoAlternativa.GENERADA
    db.commit()
    return observacion


def _recalcular(db: Session, alternativa: Alternativa, datos: RespuestaIn, usuario: Usuario) -> VersionAlternativa:
    """El CU09 dentro de la respuesta, sin confirmar: sobre la versión vigente, que el pedido nombra para no
    fijar manzanas de una pantalla desactualizada. Quien responde también tiene que poder recalcular (en
    la p. 54, los dos que responden también generan; se controla igual por si la tabla cambia)."""
    if not permite(usuario.rol, Funcion.GENERAR_ALTERNATIVAS):
        raise ErrorApi(
            403,
            f"El rol {NOMBRES_ROL.get(usuario.rol, usuario.rol)} no permite "
            f"{DESCRIPCIONES[Funcion.GENERAR_ALTERNATIVAS]}.",
            "Respondé con una justificación o una aclaración, o pedile a un proyectista que recalcule.",
        )
    vigente = _vigente(db, alternativa)
    recalculo = datos.recalculo
    if recalculo.id_version != vigente.id_version:
        raise ErrorApi(
            409,
            f"La versión que se quiere recalcular ya no es la vigente de la alternativa {alternativa.codigo}: "
            f"la vigente es la {vigente.numero}.",
            "Volvé a cargar la alternativa y elegí las manzanas sobre la versión vigente.",
        )
    entrada = RecalculoIn(estrategia=recalculo.estrategia, manzanas=recalculo.manzanas)
    return ServicioGeneracion(db).recalcular_sin_confirmar(vigente, entrada, usuario)


# --- Cerrar y reabrir -------------------------------------------------------------------------------


def cambiar_estado(db: Session, id_observacion: int, datos: EstadoObservacionIn) -> Observacion:
    """`cerrar()` y `reabrir()` (p. 46): solo sobre una observación respondida. Cerrar es la conformidad
    del emisor con la respuesta (Anexo 1.5) y no cambia la alternativa. Reabrir la vuelve a `abierta`, y la
    alternativa a `observada`: si es bloqueante, vuelve a impedir compartir."""
    observacion = obtener(db, id_observacion)
    alternativa = observacion.version.alternativa
    _bloquear(db, alternativa)
    db.refresh(observacion)
    nombre = designaciones(alternativa)[observacion.id_observacion]
    if observacion.estado != EstadoObservacion.RESPONDIDA:
        estado = NOMBRES_ESTADO[EstadoObservacion(observacion.estado)]
        raise ErrorApi(
            409,
            f"La observación {nombre} está {estado}: solo se cierra o se reabre una respondida.",
            "Una abierta se responde primero; una cerrada ya no cambia."
            if observacion.estado == EstadoObservacion.ABIERTA
            else "Si hace falta volver sobre el tema, registrá una observación nueva.",
        )
    if datos.estado == EstadoObservacion.CERRADA:
        observacion.estado = EstadoObservacion.CERRADA
        observacion.fecha_cierre = reloj.ahora()
    else:
        observacion.estado = EstadoObservacion.ABIERTA
        alternativa.estado = EstadoAlternativa.OBSERVADA
    db.commit()
    return observacion


# --- Auxiliares -------------------------------------------------------------------------------------


def _bloquear(db: Session, alternativa: Alternativa) -> None:
    """Bloquea la fila de la alternativa hasta el final de la transacción: los cambios de estado de sus
    observaciones, de la selección y los enlaces se hacen de a uno."""
    db.execute(
        select(Alternativa.id_alternativa)
        .where(Alternativa.id_alternativa == alternativa.id_alternativa)
        .with_for_update()
    )


def _vigente(db: Session, alternativa: Alternativa) -> VersionAlternativa:
    """La versión de mayor número, leída de la base (la relación puede estar desactualizada)."""
    return db.scalar(
        select(VersionAlternativa)
        .where(VersionAlternativa.id_alternativa == alternativa.id_alternativa)
        .order_by(VersionAlternativa.numero.desc())
        .limit(1)
    )


def _m2(valor: float) -> str:
    """Una superficie en español: «0,35 m²», «5.459 m²» (RNF01)."""
    if valor < 10:
        return f"{valor:.2f}".replace(".", ",") + " m²"
    return f"{round(valor):,}".replace(",", ".") + " m²"
