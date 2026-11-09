"""Selección de alternativas y enlaces compartidos (CU14, RF16; secuencia de la p. 45; D70)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.comunes import UsuarioResumen
from app.schemas.proyecto import AlternativaResumen


class SeleccionIn(BaseModel):
    """CU14, paso 1: las alternativas que se presentarán al cliente, por su código. Reemplaza la
    selección anterior; una lista vacía la borra."""

    model_config = ConfigDict(extra="forbid")

    alternativas: list[str] = Field(max_length=100, examples=[["A", "B"]])


class EnlaceIn(BaseModel):
    """CU14, paso 3: la fecha de vencimiento, obligatoria y de 30 días como máximo (p. 54). El enlace
    vale hasta el final de ese día, en hora de Córdoba."""

    model_config = ConfigDict(extra="forbid")

    fecha_vencimiento: date


class RevocacionIn(BaseModel):
    """Revocar un enlace (p. 54: «puede ser revocada en cualquier momento»). No tiene vuelta atrás."""

    model_config = ConfigDict(extra="forbid")

    revocado: Literal[True]


class VersionCompartida(BaseModel):
    id_version: int
    codigo_alternativa: str
    numero_version: int


class EnlaceOut(BaseModel):
    """Un enlace, como lo ve el estudio. Nunca el token: se mostró una vez, al crearlo, y la base guarda
    solo su hash."""

    id_enlace: int
    estado: Literal["vigente", "vencido", "revocado"]
    fecha_creacion: datetime
    fecha_vencimiento: datetime
    creado_por: UsuarioResumen
    versiones: list[VersionCompartida]
    ultimo_acceso: datetime | None
    cantidad_accesos: int


class EnlaceCreadoOut(BaseModel):
    """El enlace recién creado y su token, que se muestra esta única vez (CU14, paso 5). El portal arma
    la dirección del cliente con su propio origen: `<origen>/#/compartido/<token>` (D71)."""

    enlace: EnlaceOut
    token: str


class SeleccionOut(BaseModel):
    alternativas: list[AlternativaResumen]
