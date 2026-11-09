"""la descripción de una alternativa para el cliente (API 0.13.0)

El prototipo de la vista del cliente (p. 51, figura 21) muestra, arriba de los indicadores, una
descripción del trazado escrita por el estudio («Trazado en grilla con calles principales…»). El ER no
tiene dónde guardarla (D29, D76):

- **`alternativa.descripcion`** (`text`, NULL): la escribe quien comparte (CU14) y se puede cambiar.
  `alternativa` no es inmutable: su estado ya cambia con el ciclo de revisión (D69).
- **`enlace_version.descripcion`** (`text`, NULL): la copia de la descripción en el momento de compartir.
  Lo que ve el cliente no cambia después de compartir (p. 45; D70): ni la versión ni su descripción. Un
  `ADD COLUMN` no dispara el trigger de inmutabilidad de la 0002, que rechaza UPDATE, DELETE y TRUNCATE
  y sigue igual; las filas que ya existen quedan sin descripción.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("alternativa", sa.Column("descripcion", sa.Text(), nullable=True))
    op.add_column("enlace_version", sa.Column("descripcion", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("enlace_version", "descripcion")
    op.drop_column("alternativa", "descripcion")
