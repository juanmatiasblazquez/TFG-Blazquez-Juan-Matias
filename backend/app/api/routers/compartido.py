"""Lo que ve el cliente por un enlace, sin cuenta (CU15, RF16; p. 45, pasos 16 a 25; D70, D71).

Son los únicos endpoints, además de los públicos, sin una función de la tabla de la p. 54: su identidad es
el enlace (`enlace_actual`), que solo da acceso a lo que comparte. Son de solo lectura, y el token viaja en
el encabezado `Authorization`, nunca en la dirección.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencias import enlace_actual
from app.core.db import get_db
from app.models import EnlaceCompartido
from app.schemas.compartido import AlternativaCompartidaOut, CompartidoOut
from app.schemas.errores import ErrorOut
from app.services import compartido, enlaces

router = APIRouter(tags=["compartido"])

# Lo compartido no se guarda en ninguna caché, ni del navegador ni de un proxy.
SIN_CACHE = {"Cache-Control": "no-store"}
ERRORES = {401: {"model": ErrorOut}, 404: {"model": ErrorOut}, 410: {"model": ErrorOut}}


@router.get("/compartido", summary="Ver lo compartido", response_model=CompartidoOut, responses=ERRORES)
def ver_compartido(
    response: Response, db: Session = Depends(get_db), enlace: EnlaceCompartido = Depends(enlace_actual)
) -> CompartidoOut:
    """CU15, pasos 2 y 3: valida el token, su vencimiento y su estado, registra el acceso y muestra los
    datos del proyecto y las alternativas compartidas. 410 si venció o fue revocado (2.a)."""
    response.headers.update(SIN_CACHE)
    enlaces.registrar_acceso(db, enlace)
    return compartido.presentar(enlace)


@router.get(
    "/compartido/alternativas/{codigo}",
    summary="Ver una alternativa compartida",
    response_model=AlternativaCompartidaOut,
    responses=ERRORES,
)
def ver_alternativa_compartida(
    codigo: str, response: Response, enlace: EnlaceCompartido = Depends(enlace_actual)
) -> AlternativaCompartidaOut:
    """CU15, pasos 4 y 5: el trazado de la versión compartida, sobre cartografía, y sus indicadores
    principales. 404 si el enlace no comparte esa alternativa."""
    response.headers.update(SIN_CACHE)
    return compartido.presentar_alternativa(compartido.version_compartida(enlace, codigo))
