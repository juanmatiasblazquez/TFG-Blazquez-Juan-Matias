"""Pedidos de otro sitio (CSRF; D63).

La sesión viaja en una cookie, y el navegador la manda sola: una página de otro sitio podría hacer
que el navegador del usuario envíe un formulario a la API con su sesión. Dos defensas:

- la cookie es `SameSite=Strict`, así el navegador no la manda en pedidos que vienen de otro sitio;
- y la API rechaza con 403 un pedido que modifica (POST, PUT, PATCH, DELETE) si el navegador avisa que
  viene de otro origen. Hace falta además de `SameSite`, porque para el navegador «el mismo sitio»
  ignora el puerto: otro servicio en `localhost:8000` es el mismo sitio que el portal en
  `localhost:8080`.

El aviso es `Sec-Fetch-Site` (lo mandan todos los navegadores actuales); si falta, se compara `Origin`
con el `Host`. Un pedido sin ninguno de los dos no viene de un navegador (curl, los scripts, las
pruebas), y no lleva una cookie ajena: pasa.
"""

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.schemas.errores import ErrorOut

METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS"})
MISMO_ORIGEN = frozenset({"same-origin", "none"})


def de_otro_origen(request: Request) -> bool:
    if request.method in METODOS_SEGUROS:
        return False
    sitio = request.headers.get("sec-fetch-site")
    if sitio is not None:
        return sitio not in MISMO_ORIGEN
    origen = request.headers.get("origin")
    if origen is None:
        return False
    return urlsplit(origen).netloc != request.headers.get("host")


def registrar_control_de_origen(app: FastAPI) -> None:
    # Un middleware de Starlette es `async` por contrato; no hace nada que bloquee (D08 habla de los
    # endpoints).
    @app.middleware("http")
    async def _control_de_origen(request: Request, siguiente):
        if de_otro_origen(request):
            cuerpo = ErrorOut(
                causa="El pedido viene de otro sitio.",
                sugerencia="Usá el portal desde su propia dirección.",
                problemas=[],
                geometria=None,
            )
            return JSONResponse(status_code=403, content=cuerpo.model_dump(mode="json"))
        return await siguiente(request)
