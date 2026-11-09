"""Espera a que PostgreSQL acepte conexiones. Lo llama entrypoint.sh antes de migrar."""

import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from app.core.config import settings

INTENTOS = 30
PAUSA_SEGUNDOS = 2


def main() -> int:
    engine = create_engine(settings.database_url, poolclass=NullPool, connect_args={"connect_timeout": 3})
    destino = f"{settings.db_host}:{settings.db_port}/{settings.db_name}"
    for intento in range(1, INTENTOS + 1):
        try:
            with engine.connect() as conexion:
                conexion.execute(text("SELECT 1"))
            print(f"PostgreSQL disponible en {destino}.")
            return 0
        except OperationalError:
            print(f"Esperando a PostgreSQL en {destino} ({intento}/{INTENTOS})...")
            time.sleep(PAUSA_SEGUNDOS)
    print(f"PostgreSQL no respondió en {destino}.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
