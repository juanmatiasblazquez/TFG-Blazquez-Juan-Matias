"""habilita la extensión PostGIS

Primera migración y ÚNICA fuente de la extensión. La imagen de la base
(docker/db/Dockerfile) se construye sin el script de postgis/postgis que la creaba sola,
así que si /api/health informa la versión de PostGIS es porque esta migración corrió.

Solo se crea `postgis` (tipos geometry/geography, índices GiST, funciones espaciales). No
se crean postgis_topology ni postgis_tiger_geocoder: el prototipo no los usa.

CREATE EXTENSION postgis requiere privilegios de superusuario: el usuario de la app es el
dueño de la base (docs/decisiones.md, D16).

Revision ID: 0001
Revises:
Create Date: 2026-10-27

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    # Falla si alguna tabla todavía usa tipos de PostGIS: es lo esperable, porque las
    # migraciones que las crean se deshacen antes que esta.
    op.execute("DROP EXTENSION IF EXISTS postgis")
