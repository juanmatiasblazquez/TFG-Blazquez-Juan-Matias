"""por dónde va la calle de borde: todo el contorno o por lado (motor 0.11.0)

`parametros_loteo` suma **`calle_borde`** (D86): «contorno», la calle de borde en todo el límite del
terreno (D50), o «por_lado», solo en los lados casi paralelos a las filas, los de una entrante y los de
un acceso. Es la casilla «Calle de borde en todo el contorno» del portal.

Sigue la regla de D45, como el criterio del verde en la 0006: cada conjunto toma el valor que de hecho
se usó.
- «contorno» en los que usó alguna versión del motor desde la 0.7.0, la de la calle de borde (D50),
  hasta la 0.10.x: así una alternativa guardada se vuelve a generar igual (RNF05).
- NULL en el resto: los anteriores a la calle de borde y los que nunca se usaron. Generar con un
  conjunto así da 422, y configurar los parámetros (CU05) propone el valor de referencia, «por_lado».
- El rango se cierra en 0.11.0 a propósito: si una base se baja y se vuelve a subir, un conjunto que usó
  el motor 0.11.0 no recibe un valor que ese motor no necesariamente usó.

**El trigger de inmutabilidad (D28) no se toca:** `parametros_loteo` no lo tiene.

La columna no está en el ER: anotado en D29.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# La calle de borde del motor 0.7.0 al 0.10.x (D50).
CONTORNO = "contorno"


def upgrade() -> None:
    op.add_column("parametros_loteo", sa.Column("calle_borde", sa.String(10), nullable=True))
    # La versión del motor se compara por sus números: '0.10.2' es posterior a '0.7.0'.
    op.execute(
        f"""
        UPDATE parametros_loteo AS p
           SET calle_borde = '{CONTORNO}'
         WHERE EXISTS (
               SELECT 1
                 FROM version_alternativa AS v
                WHERE v.id_conjunto = p.id_conjunto
                  AND string_to_array(v.version_motor, '.')::int[] >= ARRAY[0, 7, 0]
                  AND string_to_array(v.version_motor, '.')::int[] < ARRAY[0, 11, 0]
         )
        """
    )


def downgrade() -> None:
    op.drop_column("parametros_loteo", "calle_borde")
