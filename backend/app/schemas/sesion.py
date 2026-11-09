"""Inicio de sesión, la sesión actual y el cambio de contraseña (CU01, RF01; D63, D66).

Las contraseñas llegan como `SecretStr`: su `repr` no muestra el valor, así no aparecen en un log ni
en un error por descuido.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

# Lo más largo que se acepta en el inicio de sesión. La política admite 128 (`app.core.contrasenas`);
# acá solo se evita hashear un texto enorme.
LARGO_MAXIMO = 1024


def _no_enorme(valor: SecretStr) -> SecretStr:
    if len(valor.get_secret_value()) > LARGO_MAXIMO:
        raise ValueError(f"Admite hasta {LARGO_MAXIMO} caracteres.")
    return valor


class InicioSesionIn(BaseModel):
    """Correo y contraseña (CU01, paso 3)."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254, examples=["director@estudio.com.ar"])
    contrasena: SecretStr

    _contrasena = field_validator("contrasena")(_no_enorme)


class CambioContrasenaIn(BaseModel):
    """La contraseña actual (la temporal, en el primer ingreso) y la nueva, que tiene que cumplir la
    política de la p. 53."""

    model_config = ConfigDict(extra="forbid")

    contrasena_actual: SecretStr
    contrasena_nueva: SecretStr

    _contrasenas = field_validator("contrasena_actual", "contrasena_nueva")(_no_enorme)


class UsuarioSesionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_usuario: int
    nombre: str
    apellido: str
    email: str
    rol: str


class SesionOut(BaseModel):
    """La sesión actual (D63). El portal oculta lo que el rol no puede hacer con `permisos` (las
    funciones de la tabla de la p. 54 que tiene el rol), sin copiar la tabla (D37); quien decide es la
    API en cada operación."""

    usuario: UsuarioSesionOut
    permisos: list[str]
    # Con una contraseña temporal, la sesión solo permite cambiarla (p. 53).
    debe_cambiar_contrasena: bool
    vence: datetime
    # Lo que le queda a la sesión según el reloj de la API: el portal avisa antes de que venza sin
    # depender de la hora del navegador.
    segundos_restantes: int
    # La política de contraseñas de la p. 53, en una frase: el portal la muestra al cambiarla.
    politica_contrasena: str
    # El nombre del estudio (`NOMBRE_ESTUDIO`), para la barra del portal (p. 48 a 51; D74). Null si no
    # se configuró.
    estudio: str | None = None
