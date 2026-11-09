"""Las pruebas de la API corren contra una base de test propia, nunca contra la de dev.

    docker compose exec -e DB_NAME=trazados_test api pytest

Identidades (D63, D67): hay un usuario de prueba por rol con cuenta, cada uno con su cliente HTTP ya
logueado. `cliente` es el director técnico, que puede todo: así las pruebas del flujo no cambian.
`anonimo` es un cliente sin sesión (como el Cliente de la p. 54, que no tiene cuenta).
"""

import itertools
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.core import contrasenas, reloj as reloj_api
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.permisos import Rol
from app.main import app
from app.models import Usuario
from tests.datos_referencia import cuerpo_cliente, cuerpo_generacion, cuerpo_proyecto
from tests.identidades import CONTRASENA, USUARIOS, iniciar_sesion

_codigos = itertools.count(1)

# Guard (como en GO7): la sesión de pruebas BORRA y recrea la base. Nos negamos a correr
# contra una base cuyo nombre no termine en _test, para no destruir datos reales.
if not settings.db_name.endswith("_test"):
    raise RuntimeError(
        f"Las pruebas tienen que correr contra una base de test, no '{settings.db_name}'. "
        "Ejecutá: docker compose exec -e DB_NAME=trazados_test api pytest"
    )

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

_clientes: dict[Rol, TestClient] = {}
_hash: list[str] = []


def asegurar_usuario(email: str, nombre: str, apellido: str, rol: str) -> Usuario:
    """Crea el usuario de prueba, o lo deja como nuevo: activo, con su rol y con `CONTRASENA`."""
    if not _hash:
        _hash.append(contrasenas.hashear(CONTRASENA))
    with SessionLocal() as db:
        usuario = db.scalar(select(Usuario).where(Usuario.email == email))
        if usuario is None:
            usuario = Usuario(email=email, nombre=nombre, apellido=apellido)
            db.add(usuario)
        usuario.rol = rol
        usuario.activo = True
        usuario.hash_contrasena = _hash[0]
        usuario.debe_cambiar_contrasena = False
        usuario.vence_contrasena_temporal = None
        db.commit()
        return usuario


def preparar_identidades() -> None:
    """Los tres usuarios de prueba y sus clientes logueados. La llaman el arranque de la sesión de
    pruebas y las pruebas de migraciones, que bajan la base y se llevan los usuarios o las sesiones."""
    limpiar_acceso()
    for rol, (email, nombre, apellido) in USUARIOS.items():
        asegurar_usuario(email, nombre, apellido, rol)
        cliente = _clientes.setdefault(rol, TestClient(app))
        cliente.cookies.clear()
        respuesta = iniciar_sesion(cliente, email)
        assert respuesta.status_code == 200, respuesta.text
    limpiar_acceso()


def limpiar_acceso() -> None:
    """Vacía el control de acceso: todas las pruebas comparten la dirección del TestClient."""
    with SessionLocal() as db:
        db.execute(text("DELETE FROM acceso_direccion"))
        db.commit()


@pytest.fixture(scope="session")
def restaurar_identidades():
    """`preparar_identidades`, para las pruebas que bajan la base. Va por un fixture y no por un import:
    pytest carga este archivo como `conftest`, y un `from tests.conftest import …` cargaría otra copia,
    con otros clientes."""
    return preparar_identidades


@pytest.fixture(scope="session")
def alembic_cfg() -> Config:
    return Config(str(ALEMBIC_INI))


@pytest.fixture(scope="session", autouse=True)
def base_de_test(alembic_cfg):
    """Recrea la base de test vacía y la lleva a head con las migraciones reales.

    La crea el conftest (y no un script initdb, que solo corre con el volumen vacío): así
    cada corrida prueba también que las migraciones levantan una base desde cero.
    """
    mantenimiento = create_engine(
        settings.database_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with mantenimiento.connect() as conexion:
        conexion.execute(text(f'DROP DATABASE IF EXISTS "{settings.db_name}" WITH (FORCE)'))
        conexion.execute(text(f'CREATE DATABASE "{settings.db_name}"'))
    mantenimiento.dispose()
    command.upgrade(alembic_cfg, "head")
    preparar_identidades()
    yield


@pytest.fixture(autouse=True)
def acceso_limpio():
    """Cada prueba arranca sin intentos fallidos ni solicitudes contadas (D65)."""
    limpiar_acceso()
    yield


class Reloj:
    """El reloj de la API, para adelantarlo sin dormir (`app.core.reloj`)."""

    def adelantar(self, **tiempo) -> None:
        reloj_api.adelantar(timedelta(**tiempo))


@pytest.fixture
def reloj():
    yield Reloj()
    reloj_api.reiniciar()


@pytest.fixture(scope="session")
def cliente(base_de_test) -> TestClient:
    """El cliente HTTP del director técnico. El cliente del proyecto (CU03) es `id_cliente`."""
    return _clientes[Rol.DIRECTOR_TECNICO]


@pytest.fixture(scope="session")
def cliente_proyectista(base_de_test) -> TestClient:
    return _clientes[Rol.PROYECTISTA]


@pytest.fixture(scope="session")
def cliente_consultor(base_de_test) -> TestClient:
    return _clientes[Rol.CONSULTOR_INTERNO]


@pytest.fixture
def anonimo() -> TestClient:
    """Un cliente sin sesión, nuevo en cada prueba."""
    return TestClient(app)


@pytest.fixture
def db():
    """Sesión para leer de la base lo que guardó la API (y para intentar pisarlo)."""
    with SessionLocal() as sesion:
        yield sesion


@pytest.fixture
def nuevo_codigo():
    """Códigos de proyecto únicos dentro de la corrida (la base se recrea en cada una)."""
    return lambda: f"T-{next(_codigos):04d}"


_correos = itertools.count(1)


@pytest.fixture
def nuevo_correo():
    """Correos únicos dentro de la corrida, para los usuarios que crea una prueba."""
    return lambda prefijo="usuario": f"{prefijo}{next(_correos)}@pruebas.local"


@pytest.fixture
def crear_cliente(cliente):
    """Da de alta un cliente por la API (el de referencia, salvo cambios) y devuelve su JSON."""

    def crear(**cambios) -> dict:
        respuesta = cliente.post("/api/clientes", json=cuerpo_cliente() | cambios)
        assert respuesta.status_code == 201, respuesta.text
        return respuesta.json()

    return crear


@pytest.fixture
def id_cliente(crear_cliente) -> int:
    """Un cliente nuevo para los proyectos de la prueba: CU03 lo exige."""
    return crear_cliente()["id_cliente"]


@pytest.fixture
def crear_proyecto(cliente, nuevo_codigo, id_cliente):
    """Crea un proyecto por la API (el de referencia, salvo cambios) y devuelve su JSON."""

    def crear(**cambios) -> dict:
        respuesta = cliente.post("/api/proyectos", json=cuerpo_proyecto(nuevo_codigo(), id_cliente, **cambios))
        assert respuesta.status_code == 201, respuesta.text
        return respuesta.json()

    return crear


@pytest.fixture
def generar(cliente):
    """Genera una alternativa por la API (estrategia de referencia, salvo cambios)."""

    def generar_(id_proyecto: int, **cambios) -> dict:
        respuesta = cliente.post(f"/api/proyectos/{id_proyecto}/alternativas", json=cuerpo_generacion(**cambios))
        assert respuesta.status_code == 201, respuesta.text
        return respuesta.json()

    return generar_


@pytest.fixture
def crear_usuario(cliente, nuevo_correo):
    """Da de alta un usuario por la API (CU02) y devuelve el cuerpo del 201: el usuario y su temporal."""

    def crear(rol: str = "proyectista", **cambios) -> dict:
        cuerpo = {"nombre": "Nuevo", "apellido": "Usuario", "email": nuevo_correo(rol), "rol": rol} | cambios
        respuesta = cliente.post("/api/usuarios", json=cuerpo)
        assert respuesta.status_code == 201, respuesta.text
        return respuesta.json()

    return crear


@pytest.fixture
def con_contrasena(anonimo, crear_usuario):
    """Un usuario nuevo que ya reemplazó su temporal por `CONTRASENA`, con un cliente HTTP en el que
    quedó su sesión abierta. Devuelve (email, cliente, id_usuario)."""

    def crear(rol: str = "proyectista") -> tuple[str, TestClient, int]:
        creado = crear_usuario(rol)
        email = creado["usuario"]["email"]
        cliente = TestClient(app)
        assert iniciar_sesion(cliente, email, creado["contrasena_temporal"]).status_code == 200
        cambio = cliente.put(
            "/api/sesion/contrasena",
            json={"contrasena_actual": creado["contrasena_temporal"], "contrasena_nueva": CONTRASENA},
        )
        assert cambio.status_code == 200, cambio.text
        limpiar_acceso()
        return email, cliente, creado["usuario"]["id_usuario"]

    return crear
