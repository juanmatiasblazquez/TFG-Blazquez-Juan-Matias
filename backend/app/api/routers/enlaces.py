"""Seleccionar alternativas, compartirlas y revocarlas (CU14, RF16; p. 45; D70): solo HTTP."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencias import requiere
from app.core.db import get_db
from app.core.permisos import Funcion
from app.models import Usuario
from app.schemas.enlace import EnlaceCreadoOut, EnlaceIn, EnlaceOut, RevocacionIn, SeleccionIn, SeleccionOut
from app.schemas.errores import ErrorOut
from app.services import enlaces

router = APIRouter(tags=["enlaces"])

# «Seleccionar alternativas, compartirlas y revocarlas» (p. 54): el director técnico y el proyectista
# (la tabla manda sobre el CU14, que nombra solo al director; D29).
COMPARTIR = requiere(Funcion.COMPARTIR_ALTERNATIVAS)


@router.patch(
    "/proyectos/{id_proyecto}/seleccion",
    summary="Seleccionar las alternativas para el cliente",
    response_model=SeleccionOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def seleccionar(
    id_proyecto: int, datos: SeleccionIn, db: Session = Depends(get_db), usuario: Usuario = Depends(COMPARTIR)
) -> SeleccionOut:
    """CU14, paso 1 (p. 45, pasos 2 a 8): la selección pasa a ser la pedida. 409 si alguna tiene una
    observación bloqueante sin responder (2.a), y no cambia nada."""
    return enlaces.seleccionar(db, id_proyecto, datos)


@router.post(
    "/proyectos/{id_proyecto}/enlaces",
    summary="Compartir las alternativas seleccionadas",
    status_code=201,
    response_model=EnlaceCreadoOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def compartir(
    id_proyecto: int,
    datos: EnlaceIn,
    response: Response,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(COMPARTIR),
) -> EnlaceCreadoOut:
    """CU14, pasos 3 a 5: el enlace con las versiones vigentes de las seleccionadas y su token, que se
    muestra esta única vez. La dirección del cliente la arma el portal con su origen (D71)."""
    enlace, token = enlaces.compartir(db, id_proyecto, datos, usuario)
    response.headers["Cache-Control"] = "no-store"
    db.expire_all()
    return EnlaceCreadoOut(enlace=enlaces.presentar(enlaces.obtener(db, enlace.id_enlace)), token=token)


@router.get(
    "/proyectos/{id_proyecto}/enlaces",
    summary="Listar los enlaces del proyecto",
    response_model=list[EnlaceOut],
    responses={404: {"model": ErrorOut}},
)
def listar_enlaces(
    id_proyecto: int, db: Session = Depends(get_db), usuario: Usuario = Depends(COMPARTIR)
) -> list[EnlaceOut]:
    """Los enlaces con su estado (vigente, vencido o revocado), su vencimiento, las versiones que comparten
    y sus accesos. Nunca el token."""
    return enlaces.listar(db, id_proyecto)


@router.patch(
    "/enlaces/{id_enlace}",
    summary="Revocar un enlace",
    response_model=EnlaceOut,
    responses={404: {"model": ErrorOut}},
)
def revocar(
    id_enlace: int, datos: RevocacionIn, db: Session = Depends(get_db), usuario: Usuario = Depends(COMPARTIR)
) -> EnlaceOut:
    """`revocar()` (p. 46): desde ahora el cliente ve «no disponible» (CU15, 2.a). No tiene vuelta atrás."""
    enlaces.revocar(db, id_enlace)
    db.expire_all()
    return enlaces.presentar(enlaces.obtener(db, id_enlace))
