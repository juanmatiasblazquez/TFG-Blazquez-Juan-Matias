"""Lo que la vista del cliente suma en la sesión 14 (p. 51; D75, D76).

- La descripción de la alternativa para el cliente: la escriben quienes comparten, se copia en el enlace al
  compartir, y cambiarla después no cambia lo que ya ve el cliente.
- Quién compartió: la inicial del nombre, el apellido y el rol (validado por el autor, D75).
- El nombre del estudio (`NOMBRE_ESTUDIO`), en la sesión y en la vista del cliente (D74).
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core import reloj as reloj_api
from app.core.config import settings
from app.main import app

TEXTO = "Trazado en grilla con las avenidas sobre los dos accesos y el verde hacia el centro."


@pytest.fixture
def proyecto(crear_proyecto, generar) -> dict:
    datos = crear_proyecto()
    datos["A"] = generar(datos["id_proyecto"])
    return datos


def describir(cliente, alternativa: dict, descripcion):
    return cliente.patch(f"/api/alternativas/{alternativa['id_alternativa']}", json={"descripcion": descripcion})


def compartir(cliente, proyecto: dict) -> str:
    assert cliente.patch(f"/api/proyectos/{proyecto['id_proyecto']}/seleccion", json={"alternativas": ["A"]}).status_code == 200
    vence = (reloj_api.hoy() + timedelta(days=7)).isoformat()
    respuesta = cliente.post(f"/api/proyectos/{proyecto['id_proyecto']}/enlaces", json={"fecha_vencimiento": vence})
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["token"]


def del_cliente(token: str) -> TestClient:
    navegador = TestClient(app)
    navegador.headers["Authorization"] = f"Bearer {token}"
    return navegador


def test_la_descripcion_se_escribe_y_se_borra(cliente, proyecto):
    respuesta = describir(cliente, proyecto["A"], f"  {TEXTO}  ")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["descripcion"] == TEXTO
    leida = cliente.get(f"/api/proyectos/{proyecto['id_proyecto']}").json()
    assert leida["alternativas"][0]["descripcion"] == TEXTO
    # Vacía, se borra.
    assert describir(cliente, proyecto["A"], "   ").json()["descripcion"] is None


def test_la_describen_quienes_comparten(cliente_proyectista, cliente_consultor, proyecto):
    assert describir(cliente_proyectista, proyecto["A"], TEXTO).status_code == 200
    assert describir(cliente_consultor, proyecto["A"], TEXTO).status_code == 403


def test_tiene_un_largo_maximo(cliente, proyecto):
    respuesta = describir(cliente, proyecto["A"], "x" * 2001)
    assert respuesta.status_code == 422
    assert [p["campo"] for p in respuesta.json()["problemas"]] == ["descripcion"]


def test_el_cliente_ve_la_descripcion_que_habia_al_compartir(cliente, proyecto):
    describir(cliente, proyecto["A"], TEXTO)
    navegador = del_cliente(compartir(cliente, proyecto))
    assert navegador.get("/api/compartido/alternativas/A").json()["descripcion"] == TEXTO
    # Cambiarla después no cambia lo que ya ve el cliente (D70): el enlace guardó su copia.
    describir(cliente, proyecto["A"], "Otra descripción")
    assert navegador.get("/api/compartido/alternativas/A").json()["descripcion"] == TEXTO
    # Un enlace nuevo lleva la nueva.
    otro = del_cliente(compartir(cliente, proyecto))
    assert otro.get("/api/compartido/alternativas/A").json()["descripcion"] == "Otra descripción"


def test_sin_descripcion_el_cliente_ve_null(cliente, proyecto):
    navegador = del_cliente(compartir(cliente, proyecto))
    assert navegador.get("/api/compartido/alternativas/A").json()["descripcion"] is None


def test_el_cliente_ve_quien_compartio_con_la_inicial_y_el_rol(cliente_proyectista, proyecto):
    """«Compartido por L. Ferreyra, director técnico.» (p. 51): sin el nombre completo ni el correo."""
    vista = del_cliente(compartir(cliente_proyectista, proyecto)).get("/api/compartido").json()
    assert vista["compartido_por"] == {"nombre": "P. Proyectista", "rol": "proyectista"}


def test_el_nombre_del_estudio(cliente, proyecto, monkeypatch):
    # Sin configurar: null, y el portal dice «Sistema de trazados».
    assert cliente.get("/api/sesion").json()["estudio"] is None
    token = compartir(cliente, proyecto)
    assert del_cliente(token).get("/api/compartido").json()["estudio"] is None
    monkeypatch.setattr(settings, "nombre_estudio", "  Estudio de prueba  ")
    assert cliente.get("/api/sesion").json()["estudio"] == "Estudio de prueba"
    assert del_cliente(token).get("/api/compartido").json()["estudio"] == "Estudio de prueba"
