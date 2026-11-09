"""Ninguna contraseña ni ningún token de enlace en texto plano, ni en la base ni en los logs (RNF02;
Seguridad, p. 53 y 54; D66, D70, D71).

Recorre todo lo que toca una contraseña (el alta con su temporal, el inicio de sesión, el cambio, el
reemplazo por olvido, un inicio fallido y un 422 de la política) con los logs capturados en DEBUG, que
incluyen el SQL de SQLAlchemy con sus parámetros. Después busca cada contraseña en todas las filas de
todas las tablas y en todo lo registrado.
"""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.identidades import iniciar_sesion

PROPIA = "Marca#Secreta9z"
OTRA_PROPIA = "Marca#Segunda7q"
RECHAZADA = "marca-rechazada-sin-mayuscula"


@pytest.fixture
def todo_el_log(caplog):
    """Todos los loggers en DEBUG, también el SQL de SQLAlchemy con sus parámetros. La configuración de
    Alembic (`alembic.ini`) deja `sqlalchemy.engine` en WARN y deshabilita los loggers que ya existían:
    acá se habilitan, y al final se restauran."""
    loggers = [l for l in logging.root.manager.loggerDict.values() if isinstance(l, logging.Logger)]
    deshabilitados = [l for l in loggers if l.disabled]
    for logger in deshabilitados:
        logger.disabled = False
    for nombre in ("", "sqlalchemy.engine", "app", "fastapi", "httpx"):
        caplog.set_level(logging.DEBUG, logger=nombre)
    yield caplog
    for logger in deshabilitados:
        logger.disabled = True


def test_ninguna_contrasena_queda_en_texto_plano_ni_en_la_base_ni_en_los_logs(cliente, crear_usuario, db, todo_el_log, capfd):
    caplog = todo_el_log
    creado = crear_usuario("proyectista")
    email, id_usuario, temporal = creado["usuario"]["email"], creado["usuario"]["id_usuario"], creado["contrasena_temporal"]
    usuario = TestClient(cliente.app)
    assert iniciar_sesion(usuario, email, temporal).status_code == 200
    rechazo = usuario.put("/api/sesion/contrasena", json={"contrasena_actual": temporal, "contrasena_nueva": RECHAZADA})
    assert rechazo.status_code == 422
    assert usuario.put("/api/sesion/contrasena", json={"contrasena_actual": temporal, "contrasena_nueva": PROPIA}).status_code == 200
    assert iniciar_sesion(TestClient(cliente.app), email, RECHAZADA).status_code == 401
    segunda = cliente.post(f"/api/usuarios/{id_usuario}/contrasena-temporal").json()["contrasena_temporal"]
    assert iniciar_sesion(usuario, email, segunda).status_code == 200
    assert usuario.put("/api/sesion/contrasena", json={"contrasena_actual": segunda, "contrasena_nueva": OTRA_PROPIA}).status_code == 200
    # Un 422 de la validación de Pydantic con la contraseña adentro: el error trae el valor (`input`),
    # pero la API no lo devuelve ni lo registra.
    invalido = usuario.post("/api/sesion", json={"email": email, "contrasena": OTRA_PROPIA, "sobra": 1})
    assert invalido.status_code == 422
    secretos = [temporal, segunda, PROPIA, OTRA_PROPIA, RECHAZADA]
    for respuesta in (rechazo, invalido):
        assert not any(s in respuesta.text for s in secretos)

    # En la base: cada fila de cada tabla del esquema, como texto.
    tablas = db.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).all()
    assert {"usuario", "sesion", "acceso_direccion"} <= set(tablas)
    for tabla in tablas:
        filas = db.scalars(text(f'SELECT t::text FROM "{tabla}" t')).all()
        for secreto in secretos:
            assert not any(secreto in fila for fila in filas), (tabla, secreto)
    guardado = db.scalar(text("SELECT hash_contrasena FROM usuario WHERE id_usuario = :u"), {"u": id_usuario})
    assert guardado.startswith("$argon2id$")
    # Los tokens de sesión tampoco: solo su SHA-256.
    token = usuario.cookies["trazados_sesion"]
    assert not any(token in f for f in db.scalars(text("SELECT t::text FROM sesion t")).all())

    # En los logs (con el SQL y sus parámetros) y en la salida estándar. Que el SQL esté capturado (y con
    # el hash que se guardó) muestra que la búsqueda mira donde tiene que mirar.
    assert any(r.name.startswith("sqlalchemy.engine") for r in caplog.records)
    assert "$argon2id$" in caplog.text
    salida = capfd.readouterr()
    for secreto in secretos:
        assert secreto not in caplog.text
        assert secreto not in salida.out and secreto not in salida.err



def test_ningun_token_de_enlace_queda_en_texto_plano_ni_en_la_base_ni_en_los_logs(
    cliente, crear_proyecto, generar, db, todo_el_log, capfd
):
    """El recorrido de un enlace (compartir, abrir, ver una alternativa, revocar y volver a abrir) con los
    logs en DEBUG, el SQL incluido: el token no aparece en ninguna fila de ninguna tabla (la base guarda su
    SHA-256, p. 54) ni en nada de lo registrado. Los registros de acceso de Nginx y de Uvicorn los controla
    la skill verify, a través del Nginx real (D71)."""
    import hashlib
    from datetime import timedelta

    from app.core import reloj

    caplog = todo_el_log
    proyecto = crear_proyecto()
    generar(proyecto["id_proyecto"])
    assert cliente.patch(f"/api/proyectos/{proyecto['id_proyecto']}/seleccion", json={"alternativas": ["A"]}).status_code == 200
    fecha = (reloj.hoy() + timedelta(days=5)).isoformat()
    creado = cliente.post(f"/api/proyectos/{proyecto['id_proyecto']}/enlaces", json={"fecha_vencimiento": fecha})
    assert creado.status_code == 201, creado.text
    token, id_enlace = creado.json()["token"], creado.json()["enlace"]["id_enlace"]
    navegador = TestClient(cliente.app)
    navegador.headers["Authorization"] = f"Bearer {token}"
    assert navegador.get("/api/compartido").status_code == 200
    assert navegador.get("/api/compartido/alternativas/A").status_code == 200
    assert cliente.patch(f"/api/enlaces/{id_enlace}", json={"revocado": True}).status_code == 200
    revocado = navegador.get("/api/compartido")
    assert revocado.status_code == 410
    assert token not in revocado.text

    tablas = db.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).all()
    assert "enlace_compartido" in tablas
    for tabla in tablas:
        filas = db.scalars(text(f'SELECT t::text FROM "{tabla}" t')).all()
        assert not any(token in fila for fila in filas), tabla
    guardado = db.scalar(text("SELECT token FROM enlace_compartido WHERE id_enlace = :e"), {"e": id_enlace})
    assert guardado == hashlib.sha256(token.encode()).hexdigest()

    # Lo que se busca está en el log: el SQL que buscó el enlace, con el hash como parámetro.
    assert guardado in caplog.text
    assert token not in caplog.text
    salida = capfd.readouterr()
    assert token not in salida.out and token not in salida.err
