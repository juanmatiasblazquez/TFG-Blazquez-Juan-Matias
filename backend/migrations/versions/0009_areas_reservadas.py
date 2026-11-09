"""áreas reservadas del terreno y su copia en cada versión (motor 0.9.0)

- **`area_reservada`** es la entidad del ER (p. 47): cuelga del terreno (CU04, paso 5) con su
  polígono, su clase, su denominación y su destino. No es parte de una versión: el proyecto puede
  cambiar sus áreas (`PUT /api/proyectos/{id}/areas-reservadas`), y por eso no lleva trigger.
  - `clase` es texto libre y opcional: el documento tipa la clase como `ClaseArea` pero no
    enumera sus valores (D59, D29).
  - `denominacion` es obligatoria: es «a qué corresponde» el área (CU04, paso 5).
- **`area_reservada_version`** no está en el ER: es la copia de las áreas con las que se generó
  cada versión, con su designación (R1, R2…). Si después cambian las áreas del proyecto, una versión
  anterior sigue diciendo con qué áreas se generó y se puede reproducir (RNF05), y su recálculo usa
  esas mismas áreas (D59). Guarda el polígono que se le pasó al motor, con la precisión completa.
  Cuelga de la versión, así que es **inmutable** como el resto (RNF04, D28): lleva el mismo trigger
  de la 0002 en esta misma migración.

Lo que se aparta del ER, anotado en D28 y D29: la tabla de la copia y la designación.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def geometria(tipo: str) -> Geometry:
    return Geometry(geometry_type=tipo, srid=4326, spatial_index=False)


def upgrade() -> None:
    op.create_table(
        "area_reservada",
        sa.Column("id_area_reservada", sa.Integer(), nullable=False),
        sa.Column("id_terreno", sa.Integer(), nullable=False),
        sa.Column("geom", geometria("POLYGON"), nullable=False),
        sa.Column("clase", sa.String(20), nullable=True),
        sa.Column("denominacion", sa.String(120), nullable=False),
        sa.Column("destino", sa.String(200), nullable=True),
        sa.PrimaryKeyConstraint("id_area_reservada", name="pk_area_reservada"),
        sa.ForeignKeyConstraint(["id_terreno"], ["terreno.id_terreno"], name="fk_area_reservada_id_terreno"),
    )
    op.create_index("ix_area_reservada_id_terreno", "area_reservada", ["id_terreno"])
    op.create_table(
        "area_reservada_version",
        sa.Column("id_area_version", sa.Integer(), nullable=False),
        sa.Column("id_version", sa.Integer(), nullable=False),
        sa.Column("designacion", sa.String(10), nullable=False),
        sa.Column("geom", geometria("POLYGON"), nullable=False),
        sa.Column("clase", sa.String(20), nullable=True),
        sa.Column("denominacion", sa.String(120), nullable=False),
        sa.Column("destino", sa.String(200), nullable=True),
        sa.Column("superficie_m2", sa.Numeric(12, 2), nullable=False),
        sa.PrimaryKeyConstraint("id_area_version", name="pk_area_reservada_version"),
        sa.ForeignKeyConstraint(
            ["id_version"], ["version_alternativa.id_version"], name="fk_area_reservada_version_id_version"
        ),
        sa.UniqueConstraint("id_version", "designacion", name="uq_area_reservada_version_id_version_designacion"),
    )
    # RNF04: la copia es parte de la versión, y una versión no se modifica nunca (D28).
    op.execute(
        "CREATE TRIGGER area_reservada_version_inmutable BEFORE UPDATE OR DELETE ON area_reservada_version "
        "FOR EACH ROW EXECUTE FUNCTION version_inmutable()"
    )
    op.execute(
        "CREATE TRIGGER area_reservada_version_inmutable_truncate BEFORE TRUNCATE ON area_reservada_version "
        "FOR EACH STATEMENT EXECUTE FUNCTION version_inmutable()"
    )


def downgrade() -> None:
    # Borrar la tabla se lleva sus triggers (DROP TABLE no los dispara).
    op.drop_table("area_reservada_version")
    op.drop_index("ix_area_reservada_id_terreno", table_name="area_reservada")
    op.drop_table("area_reservada")
