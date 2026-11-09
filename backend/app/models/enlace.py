"""Enlaces compartidos con el cliente (ER `enlace_compartido` y `enlace_version`, p. 47; CU14, CU15,
RF16; Seguridad, p. 54; migración 0012, D70).

- `token` es el nombre del ER, pero guarda el SHA-256 del token, nunca el token (p. 54: «en la base de
  datos se almacena ese código de manera hasheada»). Sus 64 caracteres hexadecimales son el varchar(64)
  del ER. El token se muestra una sola vez, al crear el enlace.
- El estado (vigente, vencido o revocado) no es una columna: se deriva de `revocado` y de
  `fecha_vencimiento` (`services.enlaces.estado_de`).
- `id_usuario` (quién lo generó) no está en el ER (D29).
- `enlace_version` ata el enlace a versiones concretas: lo que se genere después no cambia lo que ve el
  cliente (p. 45). Es inmutable, con el trigger de la 0002.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, false, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.alternativa import VersionAlternativa
from app.models.proyecto import Proyecto
from app.models.tipos import Fecha
from app.models.usuario import FechaDeReloj, Usuario


class EnlaceCompartido(Base):
    __tablename__ = "enlace_compartido"

    id_enlace: Mapped[int] = mapped_column(primary_key=True)
    id_proyecto: Mapped[int] = mapped_column(ForeignKey("proyecto.id_proyecto"), index=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"))
    # El SHA-256 del token (`sesiones.hash_token`), no el token.
    token: Mapped[str] = mapped_column(String(64), unique=True)
    fecha_creacion: Mapped[Fecha]
    fecha_vencimiento: Mapped[datetime] = mapped_column(FechaDeReloj)
    revocado: Mapped[bool] = mapped_column(server_default=false())
    ultimo_acceso: Mapped[datetime | None] = mapped_column(FechaDeReloj)
    cantidad_accesos: Mapped[int] = mapped_column(server_default=text("0"))

    proyecto: Mapped[Proyecto] = relationship()
    usuario: Mapped[Usuario] = relationship()
    versiones: Mapped[list["EnlaceVersion"]] = relationship(order_by="EnlaceVersion.id_version")


class EnlaceVersion(Base):
    __tablename__ = "enlace_version"

    id_enlace: Mapped[int] = mapped_column(ForeignKey("enlace_compartido.id_enlace"), primary_key=True)
    id_version: Mapped[int] = mapped_column(ForeignKey("version_alternativa.id_version"), primary_key=True)
    # La descripción de la alternativa al compartir (0013, D76): el cliente ve esta, no la que se escriba
    # después.
    descripcion: Mapped[str | None] = mapped_column(Text)

    version: Mapped[VersionAlternativa] = relationship()
