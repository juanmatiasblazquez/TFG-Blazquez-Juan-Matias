# Contenedor «api»: FastAPI + el paquete del motor (diagrama de despliegue, p. 52).
# Se construye con dos contextos (ver los compose): este directorio y «motor» (./motor).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

# El motor es un paquete aparte (RNF07) y se instala como tal: la API depende de él, nunca
# al revés. Instalación editable: en desarrollo el bind mount de ./motor sobre /motor hace
# que los cambios del motor se vean sin reconstruir la imagen.
COPY --from=motor . /motor
RUN pip install --no-cache-dir --root-user-action=ignore -e /motor

COPY . .

EXPOSE 8000

# Invocado con bash para no depender del bit de ejecución: el bind mount de ./backend sobre
# /code lo tapa, y un clon hecho en Windows no lo preserva (mismo criterio que GO7).
ENTRYPOINT ["bash", "/code/entrypoint.sh"]
