# Imagen para correr las pruebas del motor AISLADO de la API (RNF07): no tiene FastAPI,
# SQLAlchemy, psycopg ni el código de backend/. Si el motor importara algo de eso, sus
# pruebas fallarían acá aunque el análisis estático se lo perdiera.
#
#   docker compose run --rm motor
#
# Es una imagen de herramientas (perfil «herramientas» del compose de desarrollo): en
# producción el motor viaja instalado dentro del contenedor api.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /motor

COPY . .
RUN pip install --no-cache-dir --root-user-action=ignore -e ".[test]"

CMD ["pytest"]
