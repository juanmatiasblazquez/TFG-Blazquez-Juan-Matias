import motor_trazados
from fastapi import APIRouter, Depends, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.salud import SaludOut
from app.services import salud_service

router = APIRouter(tags=["salud"])


@router.get(
    "/health",
    summary="Estado de la API, la base y PostGIS",
    response_model=SaludOut,
    responses={503: {"model": SaludOut}},
)
def health(response: Response, db: Session = Depends(get_db)) -> SaludOut:
    """Liveness + readiness: el proceso responde, la base está accesible y PostGIS habilitado.

    Devuelve 503 (con el mismo cuerpo) si la base no responde o si la extensión no está:
    así el healthcheck del contenedor, el indicador del frontend y un monitoreo externo
    distinguen "proceso vivo" de "servicio útil".
    """
    try:
        postgis = salud_service.version_postgis(db)
        base = "ok"
    except SQLAlchemyError:
        postgis, base = None, "caida"
    sano = base == "ok" and postgis is not None
    if not sano:
        response.status_code = 503
    return SaludOut(
        estado="ok" if sano else "degradado",
        base=base,
        postgis=postgis,
        motor=motor_trazados.__version__,
    )
