import motor_trazados
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app, crear_app
from tests.datos_referencia import cuerpo_proyecto

cliente = TestClient(app)


def test_health_confirma_base_postgis_y_motor():
    respuesta = cliente.get("/api/health")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "ok"
    assert cuerpo["base"] == "ok"
    # PostgreSQL 17 + PostGIS 3.5 es lo que fija el diagrama de despliegue (p. 52).
    assert cuerpo["postgis"].startswith("3.5")
    assert cuerpo["motor"] == motor_trazados.__version__


def test_la_documentacion_vive_bajo_api():
    """Todo bajo /api, que es lo que Nginx deriva a la API: así se usa desde el navegador."""
    assert cliente.get("/api/docs").status_code == 200
    assert cliente.get("/api/openapi.json").status_code == 200
    assert cliente.get("/api/docs/oauth2-redirect").status_code == 200
    assert cliente.get("/docs").status_code == 404
    assert cliente.get("/docs/oauth2-redirect").status_code == 404


def test_la_documentacion_lista_los_endpoints_del_flujo():
    rutas = cliente.get("/api/openapi.json").json()["paths"]
    assert {
        "/api/clientes",
        "/api/clientes/{id_cliente}",
        "/api/proyectos",
        "/api/proyectos/{id_proyecto}",
        "/api/proyectos/{id_proyecto}/parametros",
        "/api/parametros/referencia",
        "/api/proyectos/{id_proyecto}/alternativas",
        "/api/alternativas/{id_alternativa}",
    } <= rutas.keys()
    # El 422 documentado es el formato propio (causa, sugerencia, problemas), no el de FastAPI.
    error = rutas["/api/proyectos"]["post"]["responses"]["422"]["content"]["application/json"]["schema"]
    assert error["$ref"].endswith("/ErrorOut")


def test_en_produccion_no_hay_documentacion_y_sin_sesion_todo_queda_cerrado():
    produccion = TestClient(crear_app(Settings(app_env="prod", db_password="una-clave-propia-y-larga")))
    assert produccion.get("/api/docs").status_code == 404
    assert produccion.get("/api/openapi.json").status_code == 404
    assert produccion.get("/api/health").status_code == 200
    # Sin sesión, la dependencia única responde 401 (D63). No hay usuarios por defecto (D68).
    respuesta = produccion.post("/api/proyectos", json=cuerpo_proyecto("PROD-1", id_cliente=1))
    assert respuesta.status_code == 401
    assert respuesta.json()["causa"] == "Iniciá sesión para continuar."
    assert produccion.get("/api/proyectos/1").status_code == 401
    assert produccion.get("/api/usuarios").status_code == 401
