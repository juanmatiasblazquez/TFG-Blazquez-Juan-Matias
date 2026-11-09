"""Observaciones (CU11, CU12, RF17; D69): solo HTTP. Las reglas están en `services.observaciones`."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencias import requiere
from app.core.db import get_db
from app.core.permisos import Funcion
from app.models import Usuario
from app.schemas.errores import ErrorOut
from app.schemas.observacion import (
    EstadoObservacionIn,
    ObservacionIn,
    ObservacionOut,
    RespuestaIn,
    SectorIn,
    SectorMedidoOut,
)
from app.services import observaciones

router = APIRouter(tags=["observaciones"])

# Las filas de la p. 54.
CONSULTAR = requiere(Funcion.CONSULTAR_ALTERNATIVAS)
REGISTRAR = requiere(Funcion.REGISTRAR_OBSERVACIONES)
RESPONDER = requiere(Funcion.RESPONDER_OBSERVACIONES)


@router.get(
    "/alternativas/{id_alternativa}/observaciones",
    summary="Listar las observaciones de una alternativa",
    response_model=list[ObservacionOut],
    responses={404: {"model": ErrorOut}},
)
def listar_observaciones(
    id_alternativa: int, db: Session = Depends(get_db), usuario: Usuario = Depends(CONSULTAR)
) -> list[ObservacionOut]:
    """Las observaciones de todas las versiones de la alternativa, con su estado, su sector y sus
    respuestas (CU12, paso 1; p. 50)."""
    return observaciones.listar(db, id_alternativa)


@router.post(
    "/versiones/{id_version}/observaciones",
    summary="Registrar una observación",
    status_code=201,
    response_model=ObservacionOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def registrar_observacion(
    id_version: int, datos: ObservacionIn, db: Session = Depends(get_db), usuario: Usuario = Depends(REGISTRAR)
) -> ObservacionOut:
    """CU11: la observación queda abierta y la alternativa, observada. 422 con la parte que sale si el
    sector excede el terreno (3.a); 409 si la versión no es la vigente."""
    id_observacion = observaciones.registrar(db, id_version, datos, usuario).id_observacion
    db.expire_all()
    return observaciones.presentar(observaciones.obtener(db, id_observacion))


@router.post(
    "/versiones/{id_version}/observaciones/sector",
    summary="Medir el sector de una observación sin registrarla",
    response_model=SectorMedidoOut,
    responses={404: {"model": ErrorOut}},
)
def medir_sector(
    id_version: int, datos: SectorIn, db: Session = Depends(get_db), usuario: Usuario = Depends(REGISTRAR)
) -> SectorMedidoOut:
    """La superficie del sector que se está dibujando y, si sale del terreno, cuánto y dónde, medido como
    al registrar (CU11, 3.a; figura 19; D79). No registra nada."""
    return observaciones.vista_previa_sector(db, id_version, datos)


@router.post(
    "/observaciones/{id_observacion}/respuestas",
    summary="Responder una observación",
    status_code=201,
    response_model=ObservacionOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def responder_observacion(
    id_observacion: int, datos: RespuestaIn, db: Session = Depends(get_db), usuario: Usuario = Depends(RESPONDER)
) -> ObservacionOut:
    """CU12: con un comentario (3.b) o con un recálculo (3.a), que crea la versión n + 1 y queda vinculado
    a la respuesta, en la misma transacción. La observación pasa a respondida. Es `def`: el recálculo
    ocupa la CPU (D08)."""
    observaciones.responder(db, id_observacion, datos, usuario)
    db.expire_all()
    return observaciones.presentar(observaciones.obtener(db, id_observacion))


@router.patch(
    "/observaciones/{id_observacion}",
    summary="Cerrar o reabrir una observación",
    response_model=ObservacionOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}},
)
def cambiar_estado_observacion(
    id_observacion: int,
    datos: EstadoObservacionIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(REGISTRAR),
) -> ObservacionOut:
    """`cerrar()` y `reabrir()` (p. 46), sobre una observación respondida: los decide quien registra las
    observaciones, el director técnico (D69)."""
    observaciones.cambiar_estado(db, id_observacion, datos)
    db.expire_all()
    return observaciones.presentar(observaciones.obtener(db, id_observacion))
