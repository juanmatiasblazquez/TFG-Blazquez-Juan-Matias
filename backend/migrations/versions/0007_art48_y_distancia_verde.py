"""lados de la manzana del art. 48 de la Ord. 8060 y distancia al verde (motor 0.7.0)

- **`parametros_loteo`** suma `lado_minimo_manzana_m` (42 m), `lado_maximo_manzana_m` (250 m) y
  `lado_maximo_sin_pasaje_m` (200 m), de la Ord. 8060, art. 48 (D50). Quedan en NULL en todos los
  conjuntos que ya existen, porque ningún motor anterior los aplicó: es la regla de D45, y generar
  con un conjunto así da 422.
- **`version_alternativa`** suma `distancia_media_verde_m` y `distancia_maxima_verde_m`: la
  distancia media y la máxima de los lotes al espacio verde más cercano, por la red (D51). Nulas
  en las versiones anteriores.
- **`criterio_espacio_verde` no se toca.** Cada conjunto conserva el criterio que de hecho usó:
  «menos_lotes» los del motor 0.6.0, «cercania» los del 0.5.x, y NULL los anteriores al asignador
  (0006). El valor por defecto pasa a ser «cercania» (D51), pero no es un valor de la columna: es
  el de referencia del motor, que el portal propone para un conjunto nuevo
  (`GET /api/parametros/referencia`).

**El trigger de inmutabilidad (D28) no se toca.** Ninguna fila de una tabla con trigger se
modifica: `parametros_loteo` no lo tiene, y agregar columnas nulas a `version_alternativa` no
actualiza filas.

Ninguna de estas columnas está en el ER: anotado en D29.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LADOS = ("lado_minimo_manzana_m", "lado_maximo_manzana_m", "lado_maximo_sin_pasaje_m")
DISTANCIAS = ("distancia_media_verde_m", "distancia_maxima_verde_m")


def upgrade() -> None:
    for columna in LADOS:
        op.add_column("parametros_loteo", sa.Column(columna, sa.Numeric(7, 2), nullable=True))
    for columna in DISTANCIAS:
        op.add_column("version_alternativa", sa.Column(columna, sa.Numeric(8, 2), nullable=True))


def downgrade() -> None:
    for columna in reversed(DISTANCIAS):
        op.drop_column("version_alternativa", columna)
    for columna in reversed(LADOS):
        op.drop_column("parametros_loteo", columna)
