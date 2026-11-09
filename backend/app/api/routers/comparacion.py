from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencias import requiere
from app.core.db import get_db
from app.core.permisos import Funcion
from app.models import Usuario
from app.schemas.comparacion import ComparacionOut
from app.schemas.errores import ErrorOut
from app.services import comparacion

router = APIRouter(tags=["alternativas"])

# «Consultar alternativas» (p. 54).
CONSULTAR = requiere(Funcion.CONSULTAR_ALTERNATIVAS)


@router.get(
    "/proyectos/{id_proyecto}/comparacion",
    summary="Comparar alternativas",
    response_model=ComparacionOut,
    responses={404: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def comparar_alternativas(
    id_proyecto: int,
    alternativas: Annotated[
        list[int] | None,
        Query(description="Ids de dos o tres alternativas del proyecto, en el orden de la tabla.", examples=[[12, 15]]),
    ] = None,
    versiones: Annotated[
        list[int] | None,
        Query(description="O ids de dos o tres versiones del proyecto (por ejemplo, v1 y v2 de una alternativa)."),
    ] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(CONSULTAR),
) -> ComparacionOut:
    """Contrasta dos o tres alternativas de un proyecto (CU13, RF15), o dos o tres versiones (D57).

    Por indicador, el valor de cada una, la diferencia contra la primera y la mejor, solo donde la
    dirección no se discute. Además, los parámetros y la estrategia en los que difieren. Es de solo
    lectura: compara la versión vigente de cada alternativa (o las versiones pedidas) y no guarda nada.
    """
    return comparacion.comparar(db, id_proyecto, alternativas, versiones)
