"""Identidad, permiso y dirección del pedido (RF01, RF03, RNF02; D63, D64, D67).

- `sesion_actual`: la sesión vigente de la cookie, o 401. Es lo único que piden la sesión propia y el
  cambio de contraseña, que se pueden usar con una contraseña temporal pendiente.
- `usuario_actual`: la ÚNICA dependencia de identidad de los endpoints del dominio. Es el usuario de
  una sesión vigente, activo y sin contraseña temporal pendiente (403 si la tiene).
- `requiere(funcion)`: además, que el rol tenga esa función de la tabla de la p. 54 (403 si no). Cada
  endpoint del dominio declara la suya; una meta-prueba lo exige (`tests/test_tabla_roles.py`).
- `direccion_cliente`: la dirección del navegador, como la informa Nginx (D64).
- `enlace_actual`: el enlace compartido del cliente, que no tiene cuenta (CU15; D70, D71). Es la única
  identidad de los endpoints de `/compartido`, que no declaran una función de la tabla: el token solo da
  acceso a lo que comparte su enlace.
"""

import ipaddress
from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errores import ErrorApi
from app.core.permisos import DESCRIPCIONES, NOMBRES_ROL, Funcion, permite
from app.models import EnlaceCompartido, Sesion, Usuario
from app.services import enlaces, sesiones

# La cookie de la sesión (D63): HttpOnly, SameSite=Strict, Path=/api y, en producción, Secure.
COOKIE_SESION = "trazados_sesion"


def sesion_actual(request: Request, db: Session = Depends(get_db)) -> Sesion:
    return sesiones.vigente(db, request.cookies.get(COOKIE_SESION))


def usuario_actual(sesion: Sesion = Depends(sesion_actual)) -> Usuario:
    """El usuario del pedido (D63, que reemplaza al usuario de desarrollo de D31). El estado y el rol se
    leen de la base en cada operación, no del token: desactivar o cambiar el rol corta enseguida."""
    if sesion.usuario.debe_cambiar_contrasena:
        raise ErrorApi(
            403,
            "Antes de seguir tenés que cambiar la contraseña temporal.",
            "Elegí una contraseña nueva: hasta entonces, es lo único que permite la sesión.",
        )
    return sesion.usuario


def requiere(funcion: Funcion) -> Callable[..., Usuario]:
    """La dependencia de un endpoint que ejerce `funcion` (una fila de la tabla de la p. 54)."""

    def con_permiso(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if not permite(usuario.rol, funcion):
            raise ErrorApi(
                403,
                f"El rol {NOMBRES_ROL.get(usuario.rol, usuario.rol)} no permite {DESCRIPCIONES[funcion]}.",
                "Si lo necesitás, pedile a un director técnico que te cambie el rol.",
            )
        return usuario

    # La marca que lee la meta-prueba: qué función declara el endpoint.
    con_permiso.funcion = funcion  # type: ignore[attr-defined]
    return con_permiso


def direccion_cliente(request: Request) -> str:
    """La dirección del navegador (D64): el ÚLTIMO valor de `X-Forwarded-For`, que es el que escribió
    Nginx con `$remote_addr`.

    Nginx es el único salto y pisa el encabezado que haya mandado el cliente (`frontend/nginx/api.inc`).
    Aunque alguien lo vuelva a configurar para agregar en lugar de pisar, el último valor sigue siendo
    el que puso Nginx: lo que el cliente escriba queda antes y no se usa. La API solo es alcanzable a
    través de Nginx (invariante 4), así que el encabezado no llega de otro lado. Sin encabezado (las
    pruebas, un pedido interno) es la del par de la conexión."""
    valores = ",".join(request.headers.getlist("x-forwarded-for")).split(",")
    ultima = valores[-1].strip()
    if ultima:
        try:
            return str(ipaddress.ip_address(ultima))
        except ValueError:
            pass
    return request.client.host if request.client else "desconocida"


def enlace_actual(request: Request, db: Session = Depends(get_db)) -> EnlaceCompartido:
    """El enlace del cliente (CU15, paso 2): el token viaja en `Authorization: Bearer`, nunca en la
    dirección (D71). La página del cliente lo lee del fragmento (`#/compartido/<token>`), que el navegador
    no manda al servidor: así no queda en los registros de Nginx ni de Uvicorn, ni en un `Referer`. 401
    sin token; 404 si no existe; 410 si venció o fue revocado (p. 45, paso 20)."""
    esquema, _, token = request.headers.get("authorization", "").partition(" ")
    token = token.strip()
    if esquema.lower() != "bearer" or not token:
        raise ErrorApi(401, "Falta el enlace compartido.", "Abrí el enlace que te mandó el estudio.")
    return enlaces.vigente(db, token)
