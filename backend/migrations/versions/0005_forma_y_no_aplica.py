"""criterio de forma del lote y NULL como «no aplica» (motor 0.5.0)

Dos cambios en `parametros_loteo`:

- **Los parámetros del criterio de forma (D43):** `ancho_minimo_lote_m` (el ancho útil de un
  lote) y `factor_union_maximo` (el tope de la unión de una fracción con su lote vecino). Ningún
  conjunto que ya existe los tenía: quedan en NULL.
- **NULL quiere decir «no aplica» (D45).** La 0004 completó los umbrales del verde de los
  conjuntos que ya existían con 1.000 m² y 20 m. Las versiones generadas con esos conjuntos antes
  del motor 0.4.0 no los usaron, así que el conjunto decía algo que no pasó. Pasan a NULL en los
  conjuntos que **ninguna versión generada con el motor 0.4.0 o posterior** usó: ningún motor
  que aplica los umbrales generó con ellos.
  - Un conjunto que usaron versiones de los dos motores los conserva, porque la del 0.4.0 sí los
    aplicó. Cada versión guarda su `version_motor`.
  - Las columnas pasan a admitir NULL. La API sigue mandando siempre los cuatro valores en un
    conjunto nuevo, y generar con un conjunto que tiene alguno en NULL da 422 (D45).

**El trigger de inmutabilidad (D28) no se toca.** Esta migración no modifica ninguna fila de una
tabla con trigger: `parametros_loteo` no lo tiene, y los indicadores de los remanentes de
`version_alternativa` ya eran NULL en las versiones anteriores desde la 0004 (se agregaron como
columnas nulas, sin valor por defecto, y agregar una columna no actualiza filas).

Ninguna de estas columnas está en el ER: anotado en D29.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Los valores con los que la 0004 completó los conjuntos, para volver atrás.
SUPERFICIE_MINIMA_VERDE = "1000"
ANCHO_MINIMO_VERDE = "20"


def upgrade() -> None:
    op.add_column("parametros_loteo", sa.Column("ancho_minimo_lote_m", sa.Numeric(6, 2), nullable=True))
    op.add_column("parametros_loteo", sa.Column("factor_union_maximo", sa.Numeric(4, 2), nullable=True))
    op.alter_column("parametros_loteo", "superficie_minima_verde_m2", nullable=True)
    op.alter_column("parametros_loteo", "ancho_minimo_verde_m", nullable=True)
    # La versión del motor se compara por sus números: '0.10.0' es posterior a '0.4.0'.
    op.execute(
        """
        UPDATE parametros_loteo AS p
           SET superficie_minima_verde_m2 = NULL, ancho_minimo_verde_m = NULL
         WHERE NOT EXISTS (
               SELECT 1
                 FROM version_alternativa AS v
                WHERE v.id_conjunto = p.id_conjunto
                  AND string_to_array(v.version_motor, '.')::int[] >= ARRAY[0, 4, 0]
         )
        """
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE parametros_loteo SET superficie_minima_verde_m2 = {SUPERFICIE_MINIMA_VERDE} "
        "WHERE superficie_minima_verde_m2 IS NULL"
    )
    op.execute(f"UPDATE parametros_loteo SET ancho_minimo_verde_m = {ANCHO_MINIMO_VERDE} WHERE ancho_minimo_verde_m IS NULL")
    op.alter_column("parametros_loteo", "ancho_minimo_verde_m", nullable=False)
    op.alter_column("parametros_loteo", "superficie_minima_verde_m2", nullable=False)
    op.drop_column("parametros_loteo", "factor_union_maximo")
    op.drop_column("parametros_loteo", "ancho_minimo_lote_m")
