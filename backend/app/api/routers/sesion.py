from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencias import COOKIE_SESION, direccion_cliente, sesion_actual
from app.core.db import get_db
from app.models import Sesion
from app.schemas.errores import ErrorOut
from app.schemas.sesion import CambioContrasenaIn, InicioSesionIn, SesionOut
from app.services import sesiones
from app.services.sesiones import DURACION_SESION

router = APIRouter(tags=["sesion"])


def _poner_cookie(request: Request, response: Response, token: str) -> None:
    """La cookie de la sesión (D63): el navegador la manda sola a /api y ningún script la puede leer."""
    response.set_cookie(
        COOKIE_SESION,
        token,
        max_age=int(DURACION_SESION.total_seconds()),
        path="/api",
        httponly=True,
        samesite="strict",
        secure=request.app.state.settings.cookie_segura,
    )


@router.post(
    "/sesion",
    summary="Iniciar sesión",
    response_model=SesionOut,
    responses={401: {"model": ErrorOut}, 422: {"model": ErrorOut}, 429: {"model": ErrorOut}},
)
def iniciar_sesion(
    datos: InicioSesionIn, request: Request, response: Response, db: Session = Depends(get_db)
) -> SesionOut:
    """CU01: con correo y contraseña, una sesión de 12 h en una cookie `HttpOnly` (D63).

    - 401 con el mismo mensaje si el correo no existe, la contraseña no es correcta o el usuario está
      desactivado (4.a), y en el mismo tiempo.
    - 429 si la dirección quedó bloqueada por 10 intentos fallidos consecutivos (4.b, 30 min) o pasó
      el límite por minuto, con `Retry-After` (D65).
    - Con una contraseña temporal, la sesión solo permite cambiarla (`debe_cambiar_contrasena`)."""
    sesion, token = sesiones.iniciar(db, datos.email, datos.contrasena.get_secret_value(), direccion_cliente(request))
    _poner_cookie(request, response, token)
    return sesiones.presentar(sesion)


@router.get(
    "/sesion",
    summary="Consultar la sesión actual",
    response_model=SesionOut,
    responses={401: {"model": ErrorOut}},
)
def leer_sesion(sesion: Sesion = Depends(sesion_actual)) -> SesionOut:
    """Quién inició sesión, con qué rol y qué funciones tiene (p. 54), y cuánto le queda. 401 si no
    hay sesión o venció."""
    return sesiones.presentar(sesion)


@router.delete("/sesion", summary="Cerrar sesión", status_code=204)
def cerrar_sesion(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    """Cierra la sesión de la cookie y la borra del navegador. Sin sesión vigente también responde 204:
    cerrar sesión siempre se puede."""
    sesiones.cerrar(db, request.cookies.get(COOKIE_SESION))
    response.delete_cookie(
        COOKIE_SESION,
        path="/api",
        httponly=True,
        samesite="strict",
        secure=request.app.state.settings.cookie_segura,
    )


@router.put(
    "/sesion/contrasena",
    summary="Cambiar la contraseña",
    response_model=SesionOut,
    responses={401: {"model": ErrorOut}, 422: {"model": ErrorOut}, 429: {"model": ErrorOut}},
)
def cambiar_contrasena(
    datos: CambioContrasenaIn,
    request: Request,
    sesion: Sesion = Depends(sesion_actual),
    db: Session = Depends(get_db),
) -> SesionOut:
    """La contraseña nueva del usuario de la sesión (p. 53). Es lo único que permite una sesión con
    una contraseña temporal pendiente. Pide la actual; la nueva tiene que cumplir la política (422 con
    el campo si no). Cierra las demás sesiones del usuario."""
    sesiones.cambiar_contrasena(
        db,
        sesion,
        datos.contrasena_actual.get_secret_value(),
        datos.contrasena_nueva.get_secret_value(),
        direccion_cliente(request),
    )
    return sesiones.presentar(sesion)
