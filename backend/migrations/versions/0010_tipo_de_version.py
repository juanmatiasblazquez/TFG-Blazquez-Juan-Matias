"""tipo de versión explícito: generada, recalculada o copia (API 0.11.0)

- **`version_alternativa.tipo`** dice cómo nació cada versión (D62):
  - `generada`: la versión 1 de una alternativa (CU06);
  - `recalculada`: la n + 1 de un recálculo con sector fijado (CU09, D56);
  - `copia`: la n + 1 que vuelve a una versión anterior (D60).

  Hasta la 0009 se deducía de las otras columnas (con origen y sin sector era una copia). Un campo
  explícito no depende de que esa regla siga valiendo cuando aparezcan otras formas de crear una
  versión, por ejemplo la respuesta a una observación (CU12, 3.a).
- **El completado de las versiones que ya existen** se deduce exacto de lo guardado, con la misma
  regla que se usaba: sin origen es `generada`, con origen y sector fijado es `recalculada`, con
  origen y sin sector es `copia`.
- **El trigger de inmutabilidad (D28) rechaza ese UPDATE.** La migración lo deshabilita solo para
  completar esta columna, dentro de su transacción, y lo vuelve a habilitar antes de exigir el NOT
  NULL. No cambia ningún valor guardado: agrega uno que ya estaba implícito. Es la única excepción,
  registrada en D28 y D62, y `test_migraciones` controla que el trigger quede habilitado.

La columna no está en el ER: anotado en D29.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TRIGGER = "version_alternativa_inmutable"


def upgrade() -> None:
    op.add_column("version_alternativa", sa.Column("tipo", sa.String(12), nullable=True))
    op.execute(f"ALTER TABLE version_alternativa DISABLE TRIGGER {TRIGGER}")
    op.execute(
        "UPDATE version_alternativa SET tipo = CASE "
        "WHEN id_version_origen IS NULL THEN 'generada' "
        "WHEN geom_fijada IS NOT NULL THEN 'recalculada' "
        "ELSE 'copia' END"
    )
    op.execute(f"ALTER TABLE version_alternativa ENABLE TRIGGER {TRIGGER}")
    op.alter_column("version_alternativa", "tipo", nullable=False)
    op.create_check_constraint(
        op.f("ck_version_alternativa_tipo"),
        "version_alternativa",
        "tipo IN ('generada', 'recalculada', 'copia')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_version_alternativa_tipo"), "version_alternativa", type_="check")
    op.drop_column("version_alternativa", "tipo")
