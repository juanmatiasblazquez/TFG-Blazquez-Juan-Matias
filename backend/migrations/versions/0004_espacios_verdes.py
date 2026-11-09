"""espacios verdes y libres: umbrales del verde e indicadores de los remanentes (motor 0.4.0)

Desde el motor 0.4.0, las zonas donde no entra un lote válido quedan como remanentes, espacio
verde o espacio libre (D41). Se guardan como filas de `celda` con su `tipo` («espacio_verde»,
«espacio_libre»), así que la tabla no cambia. Lo que cambia:

- `parametros_loteo` suma los dos umbrales del verde, configurables por proyecto:
  `superficie_minima_verde_m2` y `ancho_minimo_verde_m`. Los conjuntos que ya existen se
  completan con los valores de referencia del motor 0.4.0 (1.000 m² y 20 m): las versiones
  generadas antes no los usaron, y cada una guarda su `version_motor`.
- `version_alternativa` suma los indicadores de los remanentes: superficie verde, superficie
  libre y porcentaje de cesión alcanzado (el verde sobre la superficie de los lotes, que puede
  pasar el 100 %). Quedan nulos en las versiones anteriores. Agregar una columna nula no
  modifica las filas, así que no choca con los triggers de inmutabilidad (D28).

Ninguna de estas columnas está en el ER: anotado en D29 para que el autor lo sume al documento.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Valores de referencia del motor 0.4.0 (valores_referencia.py), para los conjuntos existentes.
SUPERFICIE_MINIMA_VERDE = "1000"
ANCHO_MINIMO_VERDE = "20"


def upgrade() -> None:
    op.add_column(
        "parametros_loteo",
        sa.Column("superficie_minima_verde_m2", sa.Numeric(8, 2), nullable=False, server_default=SUPERFICIE_MINIMA_VERDE),
    )
    op.add_column(
        "parametros_loteo",
        sa.Column("ancho_minimo_verde_m", sa.Numeric(6, 2), nullable=False, server_default=ANCHO_MINIMO_VERDE),
    )
    # El valor por defecto solo completa las filas existentes: de acá en adelante, la API manda
    # siempre los dos valores.
    op.alter_column("parametros_loteo", "superficie_minima_verde_m2", server_default=None)
    op.alter_column("parametros_loteo", "ancho_minimo_verde_m", server_default=None)

    op.add_column("version_alternativa", sa.Column("superficie_espacio_verde_m2", sa.Numeric(12, 2), nullable=True))
    op.add_column("version_alternativa", sa.Column("superficie_espacio_libre_m2", sa.Numeric(12, 2), nullable=True))
    op.add_column("version_alternativa", sa.Column("porcentaje_cesion", sa.Numeric(7, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("version_alternativa", "porcentaje_cesion")
    op.drop_column("version_alternativa", "superficie_espacio_libre_m2")
    op.drop_column("version_alternativa", "superficie_espacio_verde_m2")
    op.drop_column("parametros_loteo", "ancho_minimo_verde_m")
    op.drop_column("parametros_loteo", "superficie_minima_verde_m2")
