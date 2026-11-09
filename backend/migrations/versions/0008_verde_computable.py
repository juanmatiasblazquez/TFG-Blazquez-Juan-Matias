"""verde computable para la cesión (motor 0.8.0)

- **`version_alternativa`** suma `superficie_verde_computable_m2`: el espacio verde que cuenta para
  la cesión. Desde el motor 0.8.0 las puntas que no alcanzan el lado menor del art. 48 de la Ord.
  8060 siguen siendo verde, pero no computan (D55, que reemplaza a D52). `superficie_espacio_verde_m2`
  sigue siendo todo el verde, y `porcentaje_cesion` pasa a ser el computable sobre los lotes. Nula
  en las versiones anteriores: en ellas todo el verde computaba, pero no se guardó por separado.

**El recálculo (CU09, D56) no necesita columnas nuevas.** `id_version_origen`, `geom_fijada` y las
marcas `fijada` / `fijado` de las manzanas, las celdas y los tramos están en el ER y en la 0002.

**El trigger de inmutabilidad (D28) no se toca.** Agregar una columna nula a `version_alternativa`
no actualiza filas.

La columna no está en el ER: anotado en D29.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("version_alternativa", sa.Column("superficie_verde_computable_m2", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("version_alternativa", "superficie_verde_computable_m2")
