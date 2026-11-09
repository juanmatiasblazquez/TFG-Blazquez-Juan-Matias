"""Usuarios del estudio, sus sesiones y el control de acceso por dirección (ER `usuario`, p. 47;
Seguridad, p. 53; D63, D65, D66). `sesion` y `acceso_direccion` no están en el ER (D29)."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.tipos import Fecha

# Fechas que decide la API con su reloj (`app.core.reloj`): sin valor por defecto de la base.
FechaDeReloj = DateTime(timezone=True)


class Usuario(Base):
    """Usuario del estudio (ER `usuario`). Nunca se borra: se desactiva, para conservar la autoría de
    proyectos y versiones (CU02). `rol` es uno de `app.core.permisos.Rol`.

    `debe_cambiar_contrasena` y `vence_contrasena_temporal` no están en el ER (D29): la contraseña
    temporal vale 24 h y hay que reemplazarla en el primer ingreso (p. 53)."""

    __tablename__ = "usuario"
    __table_args__ = (CheckConstraint("rol IN ('director_tecnico', 'proyectista', 'consultor_interno')", name="rol"),)

    id_usuario: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(60))
    apellido: Mapped[str] = mapped_column(String(60))
    # En minúsculas y sin espacios (`schemas.usuario.normalizar_email`): único sin importar cómo se
    # escriba.
    email: Mapped[str] = mapped_column(String(120), unique=True)
    # Argon2id (`app.core.contrasenas`, D66). Nunca la contraseña.
    hash_contrasena: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20))
    activo: Mapped[bool]
    fecha_alta: Mapped[Fecha]
    debe_cambiar_contrasena: Mapped[bool] = mapped_column(server_default=false())
    vence_contrasena_temporal: Mapped[datetime | None] = mapped_column(FechaDeReloj)


class Sesion(Base):
    """Una sesión iniciada (D63): un token aleatorio que vive en una cookie `HttpOnly` y del que acá
    se guarda solo el SHA-256. Vence a las 12 h de iniciada (p. 53), y se cierra antes al cerrar
    sesión, al desactivar al usuario o al reemplazar su contraseña."""

    __tablename__ = "sesion"

    id_sesion: Mapped[int] = mapped_column(primary_key=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"), index=True)
    hash_token: Mapped[str] = mapped_column(String(64), unique=True)
    inicio: Mapped[datetime] = mapped_column(FechaDeReloj)
    vence: Mapped[datetime] = mapped_column(FechaDeReloj)
    cerrada_en: Mapped[datetime | None] = mapped_column(FechaDeReloj)

    usuario: Mapped[Usuario] = relationship()


class AccesoDireccion(Base):
    """El control de acceso de una dirección al inicio de sesión (D65): los intentos fallidos
    consecutivos y el bloqueo de 30 min tras el décimo (CU01, 4.b; p. 53), y las solicitudes del
    minuto en curso (el límite por minuto). Una fila por dirección."""

    __tablename__ = "acceso_direccion"

    # IPv4 o IPv6 en texto: hasta 45 caracteres.
    direccion: Mapped[str] = mapped_column(String(45), primary_key=True)
    intentos_fallidos: Mapped[int]
    bloqueada_hasta: Mapped[datetime | None] = mapped_column(FechaDeReloj)
    ventana_inicio: Mapped[datetime] = mapped_column(FechaDeReloj)
    solicitudes_en_ventana: Mapped[int]
