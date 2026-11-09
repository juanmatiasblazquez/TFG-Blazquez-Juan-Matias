from collections.abc import Generator

from geoalchemy2 import alembic_helpers
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# connect_timeout: si la base no responde, /api/health tiene que contestar 503 enseguida
# en vez de quedar colgado hasta el timeout del proxy.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Nombres de restricciones e índices deterministas: las migraciones (escritas a mano) usan los
# mismos, y la prueba de que los modelos coinciden con ellas los compara (D28).
CONVENCION_NOMBRES = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION_NOMBRES)


# Tablas que crea la extensión postgis y no son del dominio: ni el autogenerate ni la prueba
# que compara modelos y migraciones tienen que verlas.
TABLAS_DE_POSTGIS = {"spatial_ref_sys"}


def incluir_objeto(objeto, nombre, tipo, reflejado, comparado_con) -> bool:
    """Filtro de Alembic: qué objetos de la base son del esquema propio (copia única: lo usan
    migrations/env.py y tests/test_migraciones.py)."""
    if tipo == "table" and reflejado and nombre in TABLAS_DE_POSTGIS:
        return False
    # Las tablas internas de las extensiones espaciales, según GeoAlchemy2.
    return alembic_helpers.include_object(objeto, nombre, tipo, reflejado, comparado_con)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
