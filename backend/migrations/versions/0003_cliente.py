"""cliente del proyecto (CU03)

CU03 hace obligatorio el cliente: «si un cliente no está cargado, primero hay que darlo de alta».
Crea la tabla `cliente` del ER y la columna `proyecto.id_cliente`, NOT NULL (D35).

Los proyectos que ya existen no tienen cliente. Antes de exigir la columna se les asigna uno
que lo dice: «Sin cliente (proyectos anteriores a la migración 0003)». Solo se crea si hay
proyectos, así que en una base nueva no aparece. Asignarles un cliente real es una tarea de
datos, no de esquema.

Lo que se aparta del ER, registrado en D29: `cliente.cuit` es único y opcional (el ER no dice
ni una cosa ni la otra).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTE_DE_LA_MIGRACION = "Sin cliente (proyectos anteriores a la migración 0003)"


def upgrade() -> None:
    op.create_table(
        "cliente",
        sa.Column("id_cliente", sa.Integer(), nullable=False),
        sa.Column("razon_social", sa.String(120), nullable=False),
        sa.Column("cuit", sa.String(13), nullable=True),
        sa.Column("email", sa.String(120), nullable=True),
        sa.Column("telefono", sa.String(30), nullable=True),
        sa.PrimaryKeyConstraint("id_cliente", name="pk_cliente"),
        sa.UniqueConstraint("cuit", name="uq_cliente_cuit"),
    )

    op.add_column("proyecto", sa.Column("id_cliente", sa.Integer(), nullable=True))
    conexion = op.get_bind()
    if conexion.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM proyecto)")):
        id_cliente = conexion.scalar(
            sa.text("INSERT INTO cliente (razon_social) VALUES (:razon_social) RETURNING id_cliente"),
            {"razon_social": CLIENTE_DE_LA_MIGRACION},
        )
        conexion.execute(sa.text("UPDATE proyecto SET id_cliente = :id_cliente"), {"id_cliente": id_cliente})
    op.alter_column("proyecto", "id_cliente", nullable=False)
    op.create_foreign_key("fk_proyecto_id_cliente", "proyecto", "cliente", ["id_cliente"], ["id_cliente"])
    op.create_index("ix_proyecto_id_cliente", "proyecto", ["id_cliente"])


def downgrade() -> None:
    op.drop_index("ix_proyecto_id_cliente", table_name="proyecto")
    op.drop_constraint("fk_proyecto_id_cliente", "proyecto", type_="foreignkey")
    op.drop_column("proyecto", "id_cliente")
    op.drop_table("cliente")
