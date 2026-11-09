from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.core.db import Base, incluir_objeto

# Importar los modelos registra las tablas en Base.metadata.
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Las migraciones se escriben a mano (D07, D28); con esto, un `alembic revision --autogenerate`
# de consulta escribe bien las columnas geometry.
OPCIONES_GEOESPACIALES = {
    "process_revision_directives": alembic_helpers.writer,
    "render_item": alembic_helpers.render_item,
}


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=incluir_objeto,
        **OPCIONES_GEOESPACIALES,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # El engine se arma con el objeto URL (no con sqlalchemy.url del .ini): así una
    # contraseña con "%" no choca con la interpolación de configparser.
    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=incluir_objeto,
            **OPCIONES_GEOESPACIALES,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
