#!/usr/bin/env bash
set -e

# Espera a que PostgreSQL acepte conexiones. En el primer arranque compose ya espera el
# healthcheck de db (depends_on), pero tras un reinicio del servidor Docker levanta los
# contenedores sin respetar ese orden.
python -m app.core.esperar_base

echo "Aplicando migraciones (alembic upgrade head)..."
alembic upgrade head

# No se siembra ningún usuario (D68). El primer director técnico se crea con
#   docker compose exec api python -m app.admin crear-director --nombre ... --apellido ... --email ...

echo "Iniciando API..."
# Sin --proxy-headers (D64): con --forwarded-allow-ips="*", Uvicorn toma el PRIMER valor de
# X-Forwarded-For, que puede escribir el cliente. La dirección del navegador la lee una sola
# función, app.api.dependencias.direccion_cliente: el último valor, el que escribe Nginx.
if [ "${APP_RELOAD:-0}" = "1" ]; then
  # Solo desarrollo: recarga al cambiar el código de la API o del motor (bind mounts).
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --reload --reload-dir /code/app --reload-dir /motor/src
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
