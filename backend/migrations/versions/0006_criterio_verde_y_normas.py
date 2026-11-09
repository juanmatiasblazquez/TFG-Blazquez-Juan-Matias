"""criterio del asignador, art. 12 de la Ley 4146 y art. 54 de la Ord. 8060 (motor 0.6.0)

`parametros_loteo` suma seis columnas, todas nulas, con la regla de D45 (NULL es «no aplica»):

- **`criterio_espacio_verde`** (D46): «menos_lotes» o «cercania». Cada conjunto toma el valor
  que de hecho se usó:
  - «cercania» en los que usó alguna versión del motor 0.5.x, el de la sesión 6, porque su
    asignador elegía por cercanía (D44);
  - NULL en el resto: los anteriores al asignador y los que nunca se usaron. Es el mismo
    criterio que en la 0005.
  - El rango se cierra en 0.6.0 a propósito: si una base se baja y se vuelve a subir, un
    conjunto que usó el motor 0.6.0 no recibe un criterio que ese motor no necesariamente usó.
- **Ley 4146, art. 12** (D48): `porcentaje_minimo_avenidas`, `ancho_minimo_avenida_m`,
  `ancho_minimo_calle_m` y `ancho_minimo_calzada_m`.
- **Ord. 8060, art. 54** (D49): `porcentaje_incremento_esquina`.

Estos cinco quedan en NULL en todos los conjuntos que ya existen, porque ningún motor anterior
los aplicó. Generar con un conjunto que tiene alguno en NULL da 422 (D45).

`version_alternativa` suma dos indicadores: `cantidad_lotes_grandes` (D47) y
`porcentaje_avenidas` (D48), nulos en las versiones anteriores.

**El trigger de inmutabilidad (D28) no se toca.** Ninguna fila de una tabla con trigger se
modifica: `parametros_loteo` no lo tiene, y agregar columnas nulas a `version_alternativa` no
actualiza filas.

Ninguna de estas columnas está en el ER: anotado en D29.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# El criterio del asignador del motor 0.5.0 (D44).
CERCANIA = "cercania"
NUMERICAS = (
    "porcentaje_minimo_avenidas",
    "ancho_minimo_avenida_m",
    "ancho_minimo_calle_m",
    "ancho_minimo_calzada_m",
    "porcentaje_incremento_esquina",
)


def upgrade() -> None:
    for columna in NUMERICAS:
        op.add_column("parametros_loteo", sa.Column(columna, sa.Numeric(5, 2), nullable=True))
    op.add_column("parametros_loteo", sa.Column("criterio_espacio_verde", sa.String(15), nullable=True))
    op.add_column("version_alternativa", sa.Column("cantidad_lotes_grandes", sa.Integer(), nullable=True))
    op.add_column("version_alternativa", sa.Column("porcentaje_avenidas", sa.Numeric(5, 2), nullable=True))
    # La versión del motor se compara por sus números: '0.10.0' es posterior a '0.5.0'. Solo el
    # motor 0.5.x tenía el asignador por cercanía.
    op.execute(
        f"""
        UPDATE parametros_loteo AS p
           SET criterio_espacio_verde = '{CERCANIA}'
         WHERE EXISTS (
               SELECT 1
                 FROM version_alternativa AS v
                WHERE v.id_conjunto = p.id_conjunto
                  AND string_to_array(v.version_motor, '.')::int[] >= ARRAY[0, 5, 0]
                  AND string_to_array(v.version_motor, '.')::int[] < ARRAY[0, 6, 0]
         )
        """
    )


def downgrade() -> None:
    op.drop_column("version_alternativa", "porcentaje_avenidas")
    op.drop_column("version_alternativa", "cantidad_lotes_grandes")
    op.drop_column("parametros_loteo", "criterio_espacio_verde")
    for columna in reversed(NUMERICAS):
        op.drop_column("parametros_loteo", columna)
