"""Gestión de usuarios (CU02, RF02; D66, D68). Solo el director técnico (p. 54)."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Los roles con cuenta (`app.core.permisos.Rol`). El Cliente no tiene cuenta (CU15).
RolIn = Literal["director_tecnico", "proyectista", "consultor_interno"]


def normalizar_email(email: str) -> str:
    """Sin espacios y en minúsculas: «Ana@Estudio.com » y «ana@estudio.com» son el mismo correo. Es la
    copia única: la usan el alta, la modificación, el inicio de sesión y el comando de administración."""
    return email.strip().lower()


def validar_email(email: str) -> str:
    email = normalizar_email(email)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("No es una dirección de correo válida.")
    return email


class UsuarioIn(BaseModel):
    """Alta de un usuario (CU02, pasos 4 y 5). La contraseña la genera el sistema: es temporal, vale
    24 h y se muestra una sola vez (paso 6)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombre: str = Field(min_length=1, max_length=60)
    apellido: str = Field(min_length=1, max_length=60)
    email: str = Field(min_length=1, max_length=120, examples=["proyectista@estudio.com.ar"])
    rol: RolIn

    _email = field_validator("email")(validar_email)


class UsuarioCambiosIn(BaseModel):
    """Modificación de un usuario (CU02, 3.a y 3.b): sus datos, su rol o la baja. Lo que no llega no
    cambia. `activo: false` lo da de baja (nunca se borra). Reactivarlo es otra operación,
    `POST /usuarios/{id}/reactivacion`, porque genera una contraseña temporal nueva (D72)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombre: str | None = Field(None, min_length=1, max_length=60)
    apellido: str | None = Field(None, min_length=1, max_length=60)
    email: str | None = Field(None, min_length=1, max_length=120)
    rol: RolIn | None = None
    activo: Literal[False] | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, email: str | None) -> str | None:
        return None if email is None else validar_email(email)


class UsuarioOut(BaseModel):
    """Un usuario como lo ve el director técnico (CU02, paso 2: rol y estado). Nunca la contraseña ni
    su hash."""

    model_config = ConfigDict(from_attributes=True)

    id_usuario: int
    nombre: str
    apellido: str
    email: str
    rol: str
    activo: bool
    fecha_alta: datetime
    # Con una contraseña temporal pendiente de cambio, y hasta cuándo vale (p. 53).
    debe_cambiar_contrasena: bool
    vence_contrasena_temporal: datetime | None


class ContrasenaTemporalOut(BaseModel):
    """La contraseña temporal, que se muestra UNA sola vez para que el director técnico la entregue
    (CU02, paso 6; p. 53). En la base queda solo su hash."""

    contrasena_temporal: str
    vence: datetime


class UsuarioCreadoOut(BaseModel):
    """El alta y la reactivación (D72): el usuario y su contraseña temporal, que se muestra esta única
    vez."""

    usuario: UsuarioOut
    contrasena_temporal: str
    vence: datetime


class DireccionBloqueadaOut(BaseModel):
    """Una dirección con el inicio de sesión bloqueado por intentos fallidos (CU01, 4.b; D65, D72)."""

    direccion: str
    intentos_fallidos: int
    bloqueada_hasta: datetime
    # Con el reloj de la API, como el aviso de vencimiento de la sesión.
    segundos_restantes: int
