"""Sesiones: iniciar, validar, cerrar y cambiar la contraseña (CU01, RF01, RNF02; D63, D66).

- **El token** es aleatorio (`secrets.token_urlsafe(32)`, 256 bits) y viaja en una cookie `HttpOnly`;
  en la base queda solo su SHA-256. Es el mismo patrón que la p. 54 pide para los enlaces compartidos.
- **Vence a las 12 h de iniciada** (p. 53), sin renovarse con el uso, y se cierra antes al cerrar
  sesión, al desactivar al usuario o al reemplazar su contraseña.
- **En cada operación** (`vigente`) se verifica que la sesión exista, no haya vencido ni se haya
  cerrado, y que el usuario siga activo; el rol se lee de la base. Por eso desactivar o cambiar el
  rol corta en el pedido siguiente.
- **Mensaje genérico (CU01, 4.a; p. 53):** un correo inexistente, una contraseña incorrecta y un
  usuario desactivado responden lo mismo, y tardan lo mismo (`contrasenas.verificar` hace el trabajo
  completo también sin usuario). Solo quien da la contraseña correcta de una temporal vencida recibe
  un mensaje propio: ya conoce la contraseña, así que no se le revela nada.
"""

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import contrasenas, reloj
from app.core.config import settings
from app.core.errores import ErrorApi
from app.core.permisos import funciones_de
from app.models import Sesion, Usuario
from app.schemas.sesion import SesionOut, UsuarioSesionOut
from app.schemas.usuario import normalizar_email
from app.services import acceso

DURACION_SESION = timedelta(hours=12)  # p. 53
VIGENCIA_TEMPORAL = timedelta(hours=24)  # p. 53

NO_COINCIDEN = "El correo o la contraseña no son correctos."
SUGERENCIA_INGRESO = "Revisalos y volvé a intentar. Si no recordás la contraseña, pedile una temporal al director técnico."
TEMPORAL_VENCIDA = "La contraseña temporal venció."
SUGERENCIA_TEMPORAL = "Pedile otra al director técnico: cada contraseña temporal vale 24 horas."
SIN_SESION = "Iniciá sesión para continuar."
SESION_NO_VALIDA = "Tu sesión venció o ya no es válida."
SUGERENCIA_SESION = "Volvé a iniciar sesión."


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def temporal_vencida(usuario: Usuario) -> bool:
    return (
        usuario.debe_cambiar_contrasena
        and usuario.vence_contrasena_temporal is not None
        and usuario.vence_contrasena_temporal <= reloj.ahora()
    )


def iniciar(db: Session, email: str, contrasena: str, direccion: str) -> tuple[Sesion, str]:
    """CU01: la sesión nueva y su token (que va a la cookie y no se guarda). 401 genérico si no
    corresponde; 429 si la dirección está bloqueada o pasó el límite (D65)."""
    acceso.controlar(db, direccion)
    usuario = db.scalar(select(Usuario).where(Usuario.email == normalizar_email(email)))
    # Siempre se verifica, también sin usuario: el tiempo no revela si el correo existe.
    correcta = contrasenas.verificar(usuario.hash_contrasena if usuario else None, contrasena)
    if usuario is None or not correcta or not usuario.activo:
        acceso.registrar_fallo(db, direccion)
        raise ErrorApi(401, NO_COINCIDEN, SUGERENCIA_INGRESO)
    if temporal_vencida(usuario):
        acceso.registrar_fallo(db, direccion)
        raise ErrorApi(401, TEMPORAL_VENCIDA, SUGERENCIA_TEMPORAL)
    acceso.registrar_exito(db, direccion)
    if contrasenas.necesita_rehash(usuario.hash_contrasena):
        usuario.hash_contrasena = contrasenas.hashear(contrasena)
    token = secrets.token_urlsafe(32)
    inicio = reloj.ahora()
    sesion = Sesion(usuario=usuario, hash_token=hash_token(token), inicio=inicio, vence=inicio + DURACION_SESION)
    db.add(sesion)
    db.commit()
    return sesion, token


def vigente(db: Session, token: str | None) -> Sesion:
    """La sesión de un token, si sigue vigente; si no, 401. Se llama en cada operación."""
    if not token:
        raise ErrorApi(401, SIN_SESION, None)
    sesion = db.scalar(select(Sesion).where(Sesion.hash_token == hash_token(token)))
    if (
        sesion is None
        or sesion.cerrada_en is not None
        or sesion.vence <= reloj.ahora()
        or not sesion.usuario.activo
        or temporal_vencida(sesion.usuario)
    ):
        raise ErrorApi(401, SESION_NO_VALIDA, SUGERENCIA_SESION)
    return sesion


def cerrar(db: Session, token: str | None) -> None:
    """Cierra la sesión del token, si existe y sigue abierta. Sin token no hace nada."""
    if not token:
        return
    db.execute(
        update(Sesion)
        .where(Sesion.hash_token == hash_token(token), Sesion.cerrada_en.is_(None))
        .values(cerrada_en=reloj.ahora())
    )
    db.commit()


def cerrar_todas(db: Session, id_usuario: int, salvo: int | None = None) -> None:
    """Cierra las sesiones abiertas de un usuario (salvo una): al desactivarlo, al reemplazar su
    contraseña o cuando la cambia él. No confirma: va con el cambio que la motiva."""
    condiciones = [Sesion.id_usuario == id_usuario, Sesion.cerrada_en.is_(None)]
    if salvo is not None:
        condiciones.append(Sesion.id_sesion != salvo)
    db.execute(update(Sesion).where(*condiciones).values(cerrada_en=reloj.ahora()))


def cambiar_contrasena(db: Session, sesion: Sesion, actual: str, nueva: str, direccion: str) -> None:
    """La contraseña nueva del usuario de la sesión (p. 53): pide la actual (la temporal, en el primer
    ingreso) y que la nueva cumpla la política. Cierra las demás sesiones del usuario. Cuenta para el
    bloqueo y el límite como el inicio de sesión, porque también verifica una contraseña (D65)."""
    acceso.controlar(db, direccion)
    usuario = sesion.usuario
    if not contrasenas.verificar(usuario.hash_contrasena, actual):
        acceso.registrar_fallo(db, direccion)
        raise ErrorApi(
            422,
            "La contraseña actual no es correcta.",
            "Escribí la que usaste para iniciar sesión.",
            problemas=[("contrasena_actual", "No es la contraseña actual.")],
        )
    problemas = contrasenas.problemas_de(nueva)
    if not problemas and nueva == actual:
        problemas = ["Tiene que ser distinta de la actual."]
    if problemas:
        raise ErrorApi(
            422,
            "La contraseña nueva no cumple la política.",
            contrasenas.DESCRIPCION_POLITICA,
            problemas=[("contrasena_nueva", " ".join(problemas))],
        )
    acceso.registrar_exito(db, direccion)
    usuario.hash_contrasena = contrasenas.hashear(nueva)
    usuario.debe_cambiar_contrasena = False
    usuario.vence_contrasena_temporal = None
    cerrar_todas(db, usuario.id_usuario, salvo=sesion.id_sesion)
    db.commit()


def presentar(sesion: Sesion) -> SesionOut:
    usuario = sesion.usuario
    return SesionOut(
        usuario=UsuarioSesionOut.model_validate(usuario),
        permisos=[str(f) for f in funciones_de(usuario.rol)],
        debe_cambiar_contrasena=usuario.debe_cambiar_contrasena,
        vence=sesion.vence,
        segundos_restantes=max(0, int((sesion.vence - reloj.ahora()).total_seconds())),
        politica_contrasena=contrasenas.DESCRIPCION_POLITICA,
        estudio=settings.nombre_estudio.strip() or None,
    )
