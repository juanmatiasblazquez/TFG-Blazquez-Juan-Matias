from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Cliente(Base):
    """Quien encarga los proyectos (ER `cliente`, p. 47). CU03 lo hace obligatorio: si no está
    cargado, primero se da de alta.

    El ER no dice qué columnas son obligatorias: lo es la razón social. El CUIT es opcional, pero
    no se repite, porque identifica a la empresa (D35).
    """

    __tablename__ = "cliente"

    id_cliente: Mapped[int] = mapped_column(primary_key=True)
    razon_social: Mapped[str] = mapped_column(String(120))
    # NN-NNNNNNNN-N, con el dígito verificador ya comprobado (schemas/cliente.py).
    cuit: Mapped[str | None] = mapped_column(String(13), unique=True)
    email: Mapped[str | None] = mapped_column(String(120))
    telefono: Mapped[str | None] = mapped_column(String(30))
