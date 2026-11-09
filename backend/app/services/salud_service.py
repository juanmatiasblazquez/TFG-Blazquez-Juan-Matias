from sqlalchemy import text
from sqlalchemy.orm import Session


def version_postgis(db: Session) -> str | None:
    """Versión de la extensión postgis habilitada en la base, o None si no está.

    Lee pg_extension en lugar de llamar a postgis_full_version(): esa función no existe
    cuando la extensión no se creó, y lo que interesa es justamente distinguir ese caso
    (la migración 0001 no corrió). Si la base no responde, propaga el error de SQLAlchemy.
    """
    return db.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
    ).scalar_one_or_none()
