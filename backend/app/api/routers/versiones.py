from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencias import requiere
from app.core.db import get_db
from app.core.permisos import Funcion
from app.models import Usuario
from app.schemas.alternativa import AlternativaOut
from app.schemas.errores import ErrorOut
from app.schemas.recalculo import RecalculoIn, SectorIn, SectorOut
from app.services import fijacion
from app.services.generacion import ServicioGeneracion, presentar_alternativa

router = APIRouter(tags=["versiones"])

# «Consultar alternativas» (p. 54).
CONSULTAR = requiere(Funcion.CONSULTAR_ALTERNATIVAS)
# «Generar alternativas y recalcular sectores» (p. 54).
GENERAR = requiere(Funcion.GENERAR_ALTERNATIVAS)


@router.get(
    "/versiones/{id_version}",
    summary="Consultar una versión",
    response_model=AlternativaOut,
    responses={404: {"model": ErrorOut}},
)
def leer_version(
    id_version: int, db: Session = Depends(get_db), usuario: Usuario = Depends(CONSULTAR)
) -> AlternativaOut:
    """Una versión cualquiera de una alternativa, con la misma forma que la alternativa (CU10): el
    portal la usa para el selector de versiones y para comparar dos versiones (D57)."""
    version = fijacion.obtener_version(db, id_version)
    return presentar_alternativa(version.alternativa, version)


@router.post(
    "/versiones/{id_version}/sector",
    summary="Ver el sector que se fijaría",
    response_model=SectorOut,
    responses={404: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def ver_sector(
    id_version: int, datos: SectorIn, db: Session = Depends(get_db), usuario: Usuario = Depends(GENERAR)
) -> SectorOut:
    """CU09, paso 3: lo que se conservaría con estas manzanas (y las que quedan enteras dentro del
    contorno), con sus calles, sus anclajes y sus indicadores. No guarda nada: es `POST` porque lleva
    un polígono. 422 si no se eligió ninguna manzana, si alguna no existe o si lo fijado abarca todo
    el terreno (3.a)."""
    return fijacion.vista_previa(db, id_version, datos)


@router.post(
    "/versiones/{id_version}/recalculos",
    summary="Fijar sectores y recalcular",
    status_code=201,
    response_model=AlternativaOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def recalcular(
    id_version: int,
    datos: RecalculoIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(GENERAR),
) -> AlternativaOut:
    """CU09 (secuencia de la p. 44): conserva las manzanas elegidas, con sus celdas y sus calles, y
    recalcula el resto con la estrategia confirmada. 201 con la versión n + 1 de la misma alternativa,
    en GeoJSON, con lo fijado y las diferencias con la versión de origen, que no cambia. 422 con causa
    y sugerencia si no queda nada que recalcular (3.a) o si lo nuevo no se conecta con lo fijado (5.a).
    Es `def` y no `async def`: el motor ocupa la CPU (D08)."""
    id_nueva = ServicioGeneracion(db).recalcular(id_version, datos, usuario).id_version
    response.headers["Location"] = request.url_for("leer_version", id_version=id_nueva).path
    # Lo que se responde se lee de la base, igual que en el GET.
    db.expire_all()
    version = fijacion.obtener_version(db, id_nueva)
    return presentar_alternativa(version.alternativa, version)


@router.post(
    "/versiones/{id_version}/copias",
    summary="Volver a esta versión",
    status_code=201,
    response_model=AlternativaOut,
    responses={404: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def volver_a_version(
    id_version: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(GENERAR),
) -> AlternativaOut:
    """Volver a una versión anterior (p. 50; D60): crea la versión n + 1 de la misma alternativa, que
    copia la elegida (sus capas, sus indicadores, sus parámetros, su estrategia y sus áreas
    reservadas). Nunca modifica ni reactiva una versión: la vigente es la de mayor número. 201 con
    `Location`; 422 si la elegida ya es la vigente."""
    id_nueva = ServicioGeneracion(db).copiar_version(id_version, usuario).id_version
    response.headers["Location"] = request.url_for("leer_version", id_version=id_nueva).path
    db.expire_all()
    version = fijacion.obtener_version(db, id_nueva)
    return presentar_alternativa(version.alternativa, version)
