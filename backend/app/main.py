from fastapi import FastAPI

from app.api.routers import (
    accesos,
    alternativas,
    clientes,
    comparacion,
    compartido,
    enlaces,
    observaciones,
    parametros,
    proyectos,
    salud,
    sesion,
    terrenos,
    usuarios,
    versiones,
)
from app.core.config import Settings, settings
from app.core.errores import registrar_manejadores
from app.core.origen import registrar_control_de_origen

# Todo lo de la API vive bajo /api: Nginx deriva ese prefijo a este contenedor y el resto
# al frontend (frontend/nginx/api.inc). Por eso la documentación interactiva también va
# bajo /api, y solo fuera de producción.
API_PREFIX = "/api"


def crear_app(config: Settings) -> FastAPI:
    """Arma la aplicación para una configuración. Es una fábrica para poder probar la de
    producción (sin documentación y con la cookie `Secure`) sin cambiar el entorno."""
    documentar = not config.es_produccion
    app = FastAPI(
        title="Trazados de loteo — API",
        version="0.16.0",
        docs_url=f"{API_PREFIX}/docs" if documentar else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if documentar else None,
        # Por defecto FastAPI lo pone en /docs/oauth2-redirect, fuera de lo que Nginx deriva a
        # la API: el «Authorize» de Swagger fallaría cuando exista el inicio de sesión.
        swagger_ui_oauth2_redirect_url=f"{API_PREFIX}/docs/oauth2-redirect" if documentar else None,
    )
    app.state.settings = config
    registrar_manejadores(app)
    registrar_control_de_origen(app)
    modulos = (
        salud,
        sesion,
        usuarios,
        accesos,
        clientes,
        proyectos,
        terrenos,
        parametros,
        alternativas,
        versiones,
        comparacion,
        observaciones,
        enlaces,
        compartido,
    )
    for modulo in modulos:
        app.include_router(modulo.router, prefix=API_PREFIX)
    return app


app = crear_app(settings)
