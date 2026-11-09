"""Gestión de usuarios (CU02, RF02; Seguridad, p. 53; D66, D68).

- **Alta:** el sistema genera una contraseña temporal aleatoria que vale 24 h, la devuelve una sola
  vez para que el director técnico la entregue y guarda solo su hash. 409 si el correo ya está
  registrado (6.a).
- **Modificación:** datos, rol y baja. Un usuario nunca se borra: `activo = false` lo da de baja y
  conserva la autoría de sus proyectos y versiones.
- **Reactivación:** el CU02 no la prevé, pero sin ella una baja por error no tendría vuelta. La hace el
  director técnico y genera una contraseña temporal nueva, como el alta (D72): quien vuelve no entra con
  la contraseña que tenía al irse.
- **Contraseña olvidada:** el director técnico la reemplaza por una temporal con las mismas reglas.
- **Efecto inmediato:** dar de baja o reemplazar la contraseña cierra las sesiones abiertas del
  usuario, y un cambio de rol vale desde el pedido siguiente porque el rol se lee de la base.
- **Siempre queda un director técnico activo:** dar de baja o cambiarle el rol al último da 409. Si
  no, nadie podría volver a gestionar usuarios desde el portal.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import contrasenas, reloj
from app.core.errores import ErrorApi
from app.core.permisos import Rol
from app.models import Usuario
from app.schemas.usuario import UsuarioCambiosIn, UsuarioIn
from app.services import sesiones
from app.services.sesiones import VIGENCIA_TEMPORAL

CORREO_REGISTRADO = "El correo ya está registrado."


def _correo_registrado() -> ErrorApi:
    return ErrorApi(
        409,
        CORREO_REGISTRADO,
        "Buscalo en la lista de usuarios: se lo puede modificar o, si está desactivado, reactivar.",
        problemas=[("email", "Ya hay un usuario con este correo.")],
    )


def listar(db: Session) -> list[Usuario]:
    """Los activos primero, por apellido y nombre (CU02, paso 2)."""
    return list(db.scalars(select(Usuario).order_by(Usuario.activo.desc(), Usuario.apellido, Usuario.nombre)))


def obtener(db: Session, id_usuario: int) -> Usuario:
    usuario = db.get(Usuario, id_usuario)
    if usuario is None:
        raise ErrorApi(404, f"No existe el usuario {id_usuario}.")
    return usuario


def _nueva_temporal(usuario: Usuario) -> tuple[str, datetime]:
    """Le asigna una temporal nueva al usuario y la devuelve, con su vencimiento. No confirma."""
    temporal = contrasenas.generar_temporal()
    vence = reloj.ahora() + VIGENCIA_TEMPORAL
    usuario.hash_contrasena = contrasenas.hashear(temporal)
    usuario.debe_cambiar_contrasena = True
    usuario.vence_contrasena_temporal = vence
    return temporal, vence


def crear(db: Session, nombre: str, apellido: str, email: str, rol: str) -> tuple[Usuario, str, datetime]:
    """El usuario nuevo, su contraseña temporal y cuándo vence (CU02, paso 6). Es la copia única del
    alta: la usan el endpoint y `python -m app.admin crear-director`."""
    if db.scalar(select(Usuario).where(Usuario.email == email)) is not None:
        raise _correo_registrado()
    usuario = Usuario(nombre=nombre, apellido=apellido, email=email, rol=rol, activo=True)
    temporal, vence = _nueva_temporal(usuario)
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError as error:
        # Dos altas simultáneas con el mismo correo: la restricción única decide.
        db.rollback()
        raise _correo_registrado() from error
    return usuario, temporal, vence


def crear_desde(db: Session, datos: UsuarioIn) -> tuple[Usuario, str, datetime]:
    return crear(db, datos.nombre, datos.apellido, datos.email, datos.rol)


def _directores_activos_ademas_de(db: Session, usuario: Usuario) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Usuario)
        .where(Usuario.rol == Rol.DIRECTOR_TECNICO, Usuario.activo, Usuario.id_usuario != usuario.id_usuario)
    )


def modificar(db: Session, id_usuario: int, cambios: UsuarioCambiosIn) -> Usuario:
    """CU02, 3.a (datos o rol) y 3.b (baja). Lo que no llega no cambia."""
    usuario = obtener(db, id_usuario)
    datos = cambios.model_dump(exclude_unset=True)
    if datos.get("email") is not None and datos["email"] != usuario.email:
        if db.scalar(select(Usuario).where(Usuario.email == datos["email"])) is not None:
            raise _correo_registrado()
    # Un null explícito es «no cambia», igual que no mandar el campo.
    nuevo_rol = datos.get("rol") or usuario.rol
    deja_de_dirigir = (
        usuario.rol == Rol.DIRECTOR_TECNICO
        and usuario.activo
        and (nuevo_rol != Rol.DIRECTOR_TECNICO or datos.get("activo") is False)
    )
    if deja_de_dirigir and _directores_activos_ademas_de(db, usuario) == 0:
        raise ErrorApi(
            409,
            "Tiene que quedar al menos un director técnico activo.",
            "Antes de darlo de baja o cambiarle el rol, nombrá a otro director técnico.",
            problemas=[("rol" if "rol" in datos else "activo", "Es el único director técnico activo.")],
        )
    for campo, valor in datos.items():
        if valor is not None:
            setattr(usuario, campo, valor)
    if datos.get("activo") is False:
        sesiones.cerrar_todas(db, usuario.id_usuario)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _correo_registrado() from error
    return usuario


def reactivar(db: Session, id_usuario: int) -> tuple[Usuario, str, datetime]:
    """Vuelve a dar de alta a un usuario desactivado, con una temporal nueva de 24 h que se muestra una
    sola vez (D72). 409 si ya está activo."""
    usuario = obtener(db, id_usuario)
    if usuario.activo:
        raise ErrorApi(
            409,
            f"{usuario.nombre} {usuario.apellido} ya está activo.",
            "Si olvidó la contraseña, reemplazala por una temporal.",
        )
    usuario.activo = True
    temporal, vence = _nueva_temporal(usuario)
    db.commit()
    return usuario, temporal, vence


def reemplazar_contrasena(db: Session, id_usuario: int) -> tuple[str, datetime]:
    """Contraseña olvidada (p. 53): una temporal nueva, con las mismas reglas que la del alta. Cierra
    las sesiones abiertas del usuario."""
    usuario = obtener(db, id_usuario)
    temporal, vence = _nueva_temporal(usuario)
    sesiones.cerrar_todas(db, usuario.id_usuario)
    db.commit()
    return temporal, vence
