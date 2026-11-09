"""Las direcciones bloqueadas por intentos fallidos, desde el portal (CU01, 4.b; D65, D72): solo HTTP."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencias import requiere
from app.core.db import get_db
from app.core.permisos import Funcion
from app.models import Usuario
from app.schemas.errores import ErrorOut
from app.schemas.usuario import DireccionBloqueadaOut
from app.services import acceso

router = APIRouter(tags=["usuarios"])

# Desbloquear es parte de gestionar a los usuarios: solo el director técnico (p. 54; D72).
GESTIONAR = requiere(Funcion.GESTIONAR_USUARIOS)


@router.get(
    "/direcciones-bloqueadas",
    summary="Listar las direcciones bloqueadas",
    response_model=list[DireccionBloqueadaOut],
)
def listar_bloqueadas(
    db: Session = Depends(get_db), usuario: Usuario = Depends(GESTIONAR)
) -> list[DireccionBloqueadaOut]:
    """Las direcciones con el inicio de sesión bloqueado y el tiempo que les queda (D72)."""
    return [
        DireccionBloqueadaOut(
            direccion=fila.direccion,
            intentos_fallidos=fila.intentos_fallidos,
            bloqueada_hasta=fila.bloqueada_hasta,
            segundos_restantes=acceso.segundos_restantes(fila),
        )
        for fila in acceso.bloqueadas(db)
    ]


@router.delete(
    "/direcciones-bloqueadas/{direccion}",
    summary="Desbloquear una dirección",
    status_code=204,
    responses={404: {"model": ErrorOut}},
)
def desbloquear(direccion: str, db: Session = Depends(get_db), usuario: Usuario = Depends(GESTIONAR)) -> Response:
    """Levanta el bloqueo antes de los 30 minutos. Con todo el estudio detrás de la misma dirección pública,
    diez fallos de una persona dejan afuera a todos (D72). Las sesiones abiertas nunca se bloquearon, así
    que quien tiene una puede destrabar a los demás."""
    acceso.desbloquear_desde_el_portal(db, direccion)
    return Response(status_code=204)
