"""La tabla de roles de la p. 54 (Seguridad), convertida en prueba (RF03, RNF02; D67).

Cada celda de la tabla, para cada rol, contra cada endpoint de su fila:

- «Sí»: el pedido se cumple (2xx);
- «No»: 403 para los roles con cuenta, y 401 para el Cliente, que no tiene cuenta (CU15);
- «Solo compartidas»: el Cliente, con el token de un enlace real, ve lo compartido (2xx en `/compartido`)
  y nada más: los endpoints del estudio le dan 401.

El Cliente es un navegador sin sesión que manda `Authorization: Bearer <token>` de un enlace vigente,
como la página del enlace (D71): así cada «No» prueba también que el token no alcanza ninguna operación de
escritura ni ningún dato fuera de lo que muestra el CU15. Ninguna celda queda omitida.

La tabla está transcrita del documento, tal cual, y NO sale de `app.core.permisos`: la prueba compara
lo que responde la API con el documento, no el código consigo mismo. Una meta-prueba exige, además, que
cada endpoint de la API declare una función de la tabla y aparezca acá, en su fila.

    docker compose exec -e DB_NAME=trazados_test api pytest tests/test_tabla_roles.py -s
"""

import itertools
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.dependencias import enlace_actual, sesion_actual
from app.core import reloj
from app.core.db import SessionLocal
from app.main import API_PREFIX, app
from tests.datos_referencia import (
    cuerpo_cliente,
    cuerpo_generacion,
    cuerpo_proyecto,
    cuerpo_recalculo,
    terreno_y_accesos_4326,
)

# --- La tabla de la p. 54, transcrita -------------------------------------------------------------

ROLES = ("Director técnico", "Proyectista", "Consultor interno", "Cliente")
TABLA = (
    ("Gestionar usuarios y roles", ("Si", "No", "No", "No")),
    ("Registrar proyectos, delimitar terrenos y configurar parámetros", ("Si", "No", "No", "No")),
    ("Generar alternativas y recalcular sectores", ("Si", "Si", "No", "No")),
    ("Consultar alternativas", ("Si", "Si", "Si", "Solo compartidas")),
    ("Registrar observaciones", ("Si", "No", "No", "No")),
    ("Responder observaciones", ("Si", "Si", "No", "No")),
    ("Seleccionar alternativas, compartirlas y revocarlas", ("Si", "Si", "No", "No")),
)

# Qué función de `app.core.permisos.Funcion` es cada fila: el único vínculo de la prueba con el código.
FUNCION_DE_FILA = {
    "Gestionar usuarios y roles": "gestionar_usuarios",
    "Registrar proyectos, delimitar terrenos y configurar parámetros": "registrar_proyectos",
    "Generar alternativas y recalcular sectores": "generar_alternativas",
    "Consultar alternativas": "consultar_alternativas",
    "Registrar observaciones": "registrar_observaciones",
    "Responder observaciones": "responder_observaciones",
    "Seleccionar alternativas, compartirlas y revocarlas": "compartir_alternativas",
}
# Los endpoints que no ejercen una función de la tabla.
PUBLICOS = {("GET", "/api/health"), ("POST", "/api/sesion"), ("DELETE", "/api/sesion")}
# Solo piden una sesión: se pueden usar con una contraseña temporal pendiente (p. 53).
SOLO_SESION = {("GET", "/api/sesion"), ("PUT", "/api/sesion/contrasena")}
# Solo piden el token de un enlace (CU15): lo que el Cliente ve, «Solo compartidas».
SOLO_ENLACE = {("GET", "/api/compartido"), ("GET", "/api/compartido/alternativas/{codigo}")}


# --- Los endpoints de cada fila ------------------------------------------------------------------


@dataclass(frozen=True)
class Pedido:
    metodo: str
    ruta: str  # la de la API, con sus parámetros: «/api/proyectos/{id_proyecto}»
    cuerpo: object = None  # un dict, o una función del escenario que lo arma
    consulta: dict = field(default_factory=dict)
    # Qué dato del escenario va en un parámetro de la ruta, si no es el del mismo nombre.
    alias: dict = field(default_factory=dict)
    # Lo que el pedido necesita nuevo en cada celda (una observación abierta, un enlace para revocar…):
    # lo arma el director técnico antes del pedido, y devuelve los parámetros de la ruta.
    preparar: Callable[[dict], dict] | None = None

    def __str__(self) -> str:
        return f"{self.metodo} {self.ruta}"


_secuencia = itertools.count(1)


def _proyecto_nuevo(e: dict) -> dict:
    return cuerpo_proyecto(f"ROL-{next(_secuencia):03d}", e["id_cliente"])


def _usuario_nuevo(e: dict) -> dict:
    return {"nombre": "Alta", "apellido": "Por Rol", "email": f"alta{next(_secuencia)}@roles.local", "rol": "consultor_interno"}


def _ok(respuesta) -> dict:
    assert 200 <= respuesta.status_code < 300, respuesta.text
    return respuesta.json() if respuesta.content else {}


def _usuario_desactivado(e: dict) -> dict:
    director = e["director"]
    nuevo = _ok(director.post("/api/usuarios", json=_usuario_nuevo(e)))["usuario"]["id_usuario"]
    _ok(director.patch(f"/api/usuarios/{nuevo}", json={"activo": False}))
    return {"id_usuario": nuevo}


def _direccion_bloqueada(e: dict) -> dict:
    """Una dirección bloqueada, escrita en la base: diez inicios fallidos tardarían diez Argon2."""
    direccion = f"198.51.100.{next(_secuencia) % 250 + 1}"
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO acceso_direccion (direccion, intentos_fallidos, bloqueada_hasta, ventana_inicio, "
                "solicitudes_en_ventana) VALUES (:d, 10, :hasta, :ahora, 0) ON CONFLICT (direccion) DO UPDATE "
                "SET intentos_fallidos = 10, bloqueada_hasta = :hasta"
            ),
            {"d": direccion, "hasta": reloj.ahora() + timedelta(minutes=30), "ahora": reloj.ahora()},
        )
        db.commit()
    return {"direccion": direccion}


def _vigente(e: dict) -> dict:
    """La versión vigente de la alternativa del escenario: las filas anteriores le suman versiones."""
    alternativa = _ok(e["director"].get(f"/api/alternativas/{e['id_alternativa']}"))
    return {"id_version_vigente": alternativa["version"]["id_version"]}


def _observacion(e: dict, responder: bool = False) -> dict:
    director = e["director"]
    url = f"/api/versiones/{_vigente(e)['id_version_vigente']}/observaciones"
    observacion = _ok(director.post(url, json=_OBSERVACION))["id_observacion"]
    if responder:
        _ok(director.post(f"/api/observaciones/{observacion}/respuestas", json=_RESPUESTA))
    return {"id_observacion": observacion}


def _seleccionada(e: dict) -> dict:
    _ok(e["director"].patch(f"/api/proyectos/{e['id_proyecto_compartido']}/seleccion", json={"alternativas": ["A"]}))
    return {}


def _vencimiento(e: dict) -> dict:
    return {"fecha_vencimiento": (reloj.hoy() + timedelta(days=7)).isoformat()}


def _enlace(e: dict) -> dict:
    _seleccionada(e)
    url = f"/api/proyectos/{e['id_proyecto_compartido']}/enlaces"
    return {"id_enlace": _ok(e["director"].post(url, json=_vencimiento(e)))["enlace"]["id_enlace"]}


def _medicion(e: dict) -> dict:
    """Lo dibujado en el paso 2 del alta: el terreno y los accesos de referencia (D79)."""
    cuerpo = cuerpo_proyecto("MEDICION", e["id_cliente"])
    return {"terreno": cuerpo["terreno"], "accesos": [a["ubicacion"] for a in cuerpo["accesos"]]}


def _sector(e: dict) -> dict:
    """Un cuadrado de unos 60 m en el centro del terreno de referencia (D79)."""
    c = terreno_y_accesos_4326()[0].centroid
    d = 0.0003
    anillo = [[c.x - d, c.y - d], [c.x + d, c.y - d], [c.x + d, c.y + d], [c.x - d, c.y + d], [c.x - d, c.y - d]]
    return {"sector": {"type": "Polygon", "coordinates": [anillo]}}


# Un triángulo en la faja 4 de POSGAR 2007 (D80).
_PLANILLA = {"contenido": "\n".join(["este;norte", "4500000;6500000", "4500100;6500000", "4500100;6500100"])}

# Sugerida y sin sector: no le impide nada a la alternativa del escenario.
_OBSERVACION = {"tipo": "comercial", "criticidad": "sugerida", "descripcion": "Evaluar lotes de 12 m de frente."}
_RESPUESTA = {"accion": "justificacion", "descripcion": "La demanda está cubierta con 10 m."}


ENDPOINTS: dict[str, list[Pedido]] = {
    "Gestionar usuarios y roles": [
        Pedido("GET", "/api/usuarios"),
        Pedido("POST", "/api/usuarios", _usuario_nuevo),
        Pedido("GET", "/api/usuarios/{id_usuario}"),
        Pedido("PATCH", "/api/usuarios/{id_usuario}", {"apellido": "Modificado"}),
        Pedido("POST", "/api/usuarios/{id_usuario}/contrasena-temporal"),
        Pedido("POST", "/api/usuarios/{id_usuario}/reactivacion", preparar=_usuario_desactivado),
        Pedido("GET", "/api/direcciones-bloqueadas"),
        Pedido("DELETE", "/api/direcciones-bloqueadas/{direccion}", preparar=_direccion_bloqueada),
    ],
    "Registrar proyectos, delimitar terrenos y configurar parámetros": [
        Pedido("POST", "/api/clientes", lambda e: cuerpo_cliente()),
        Pedido("POST", "/api/proyectos", _proyecto_nuevo),
        Pedido(
            "PUT",
            "/api/proyectos/{id_proyecto}/areas-reservadas",
            {"areas_reservadas": []},
            alias={"id_proyecto": "id_proyecto_registro"},
        ),
        Pedido(
            "POST",
            "/api/proyectos/{id_proyecto}/parametros",
            lambda e: e["parametros"],
            alias={"id_proyecto": "id_proyecto_registro"},
        ),
        # Lo que el alta y los parámetros calculan mientras se editan (D78 a D80).
        Pedido("POST", "/api/parametros/validacion", lambda e: e["parametros"]),
        Pedido("POST", "/api/terrenos/medicion", _medicion),
        Pedido("POST", "/api/terrenos/importacion", _PLANILLA),
    ],
    "Generar alternativas y recalcular sectores": [
        Pedido("POST", "/api/proyectos/{id_proyecto}/alternativas", lambda e: cuerpo_generacion()),
        Pedido("POST", "/api/versiones/{id_version}/sector", {"manzanas": ["M2"]}),
        Pedido("POST", "/api/versiones/{id_version}/recalculos", lambda e: cuerpo_recalculo(["M2"])),
        Pedido("POST", "/api/versiones/{id_version}/copias"),
    ],
    "Consultar alternativas": [
        Pedido("GET", "/api/proyectos"),
        Pedido("GET", "/api/proyectos/{id_proyecto}"),
        Pedido("GET", "/api/clientes"),
        Pedido("GET", "/api/clientes/{id_cliente}"),
        Pedido("GET", "/api/parametros/referencia"),
        Pedido("GET", "/api/alternativas/{id_alternativa}"),
        Pedido("GET", "/api/versiones/{id_version}"),
        Pedido("GET", "/api/proyectos/{id_proyecto}/comparacion", consulta={"versiones": ["{id_version}", "{id_version_2}"]}),
        Pedido("GET", "/api/alternativas/{id_alternativa}/observaciones"),
        # Las versiones del conjunto de parámetros (D82).
        Pedido("GET", "/api/proyectos/{id_proyecto}/parametros"),
    ],
    "Registrar observaciones": [
        Pedido(
            "POST",
            "/api/versiones/{id_version}/observaciones",
            _OBSERVACION,
            alias={"id_version": "id_version_vigente"},
            preparar=_vigente,
        ),
        # La vista previa del sector que se dibuja (D79).
        Pedido("POST", "/api/versiones/{id_version}/observaciones/sector", _sector),
        # Cerrar (o reabrir): la conformidad del emisor (D69).
        Pedido(
            "PATCH",
            "/api/observaciones/{id_observacion}",
            {"estado": "cerrada"},
            preparar=lambda e: _observacion(e, responder=True),
        ),
    ],
    "Responder observaciones": [
        Pedido("POST", "/api/observaciones/{id_observacion}/respuestas", _RESPUESTA, preparar=_observacion),
    ],
    "Seleccionar alternativas, compartirlas y revocarlas": [
        Pedido(
            "PATCH",
            "/api/proyectos/{id_proyecto}/seleccion",
            {"alternativas": ["A"]},
            alias={"id_proyecto": "id_proyecto_compartido"},
        ),
        Pedido(
            "POST",
            "/api/proyectos/{id_proyecto}/enlaces",
            _vencimiento,
            alias={"id_proyecto": "id_proyecto_compartido"},
            preparar=_seleccionada,
        ),
        Pedido("GET", "/api/proyectos/{id_proyecto}/enlaces", alias={"id_proyecto": "id_proyecto_compartido"}),
        Pedido("PATCH", "/api/enlaces/{id_enlace}", {"revocado": True}, preparar=_enlace),
        # La descripción para el cliente (p. 51; D76).
        Pedido("PATCH", "/api/alternativas/{id_alternativa}", {"descripcion": "Para el cliente."}),
    ],
}

# Lo que el Cliente ve por el enlace: la celda «Solo compartidas».
COMPARTIDOS = [Pedido("GET", "/api/compartido"), Pedido("GET", "/api/compartido/alternativas/{codigo}")]

# --- El escenario: lo arma el director técnico una vez -------------------------------------------


@pytest.fixture(scope="module")
def escenario(cliente) -> dict:
    """Un cliente, un proyecto para registrar (áreas y parámetros), otro con una alternativa recalculada
    (v1 y v2), otro compartido con un enlace vigente (el del Cliente), y un usuario sobre el que operar."""
    id_cliente = cliente.post("/api/clientes", json=cuerpo_cliente()).json()["id_cliente"]
    registro = cliente.post("/api/proyectos", json=cuerpo_proyecto("ROL-REG", id_cliente)).json()
    trazado = cliente.post("/api/proyectos", json=cuerpo_proyecto("ROL-TRZ", id_cliente)).json()
    alternativa = cliente.post(f"/api/proyectos/{trazado['id_proyecto']}/alternativas", json=cuerpo_generacion()).json()
    v1 = alternativa["version"]["id_version"]
    v2 = cliente.post(f"/api/versiones/{v1}/recalculos", json=cuerpo_recalculo(["M3"])).json()["version"]["id_version"]
    objetivo = cliente.post(
        "/api/usuarios",
        json={"nombre": "Objetivo", "apellido": "De Roles", "email": "objetivo@roles.local", "rol": "proyectista"},
    ).json()["usuario"]["id_usuario"]
    compartido = _ok(cliente.post("/api/proyectos", json=cuerpo_proyecto("ROL-CMP", id_cliente)))
    _ok(cliente.post(f"/api/proyectos/{compartido['id_proyecto']}/alternativas", json=cuerpo_generacion()))
    _ok(cliente.patch(f"/api/proyectos/{compartido['id_proyecto']}/seleccion", json={"alternativas": ["A"]}))
    fecha = (reloj.hoy() + timedelta(days=30)).isoformat()
    enlace = _ok(cliente.post(f"/api/proyectos/{compartido['id_proyecto']}/enlaces", json={"fecha_vencimiento": fecha}))
    return {
        "director": cliente,
        "id_proyecto_compartido": compartido["id_proyecto"],
        "token": enlace["token"],
        "codigo": "A",
        "id_cliente": id_cliente,
        "id_proyecto_registro": registro["id_proyecto"],
        "id_proyecto": trazado["id_proyecto"],
        "id_alternativa": alternativa["id_alternativa"],
        "id_version": v1,
        "id_version_2": v2,
        "id_usuario": objetivo,
        "parametros": cliente.get("/api/parametros/referencia").json()["valores"],
    }


@pytest.fixture
def clientes_por_rol(cliente, cliente_proyectista, cliente_consultor, escenario) -> dict:
    """El Cliente: un navegador sin sesión, con el token de un enlace vigente en el encabezado (D71)."""
    del_cliente = TestClient(app)
    del_cliente.headers["Authorization"] = f"Bearer {escenario['token']}"
    return dict(zip(ROLES, (cliente, cliente_proyectista, cliente_consultor, del_cliente), strict=True))


# --- Las celdas ----------------------------------------------------------------------------------

def _pedidos(fila: str, valor: str) -> list[Pedido]:
    """Los endpoints de una celda: los de su fila y, en «Solo compartidas», también los del enlace."""
    return ENDPOINTS[fila] + (COMPARTIDOS if valor == "Solo compartidas" else [])


CELDAS = [
    pytest.param(fila, rol, valor, pedido, id=f"{fila} | {rol} | {pedido}")
    for fila, valores in TABLA
    for rol, valor in zip(ROLES, valores, strict=True)
    for pedido in _pedidos(fila, valor)
]
RESULTADOS: dict[tuple[str, str], list[str]] = {}


def _pedir(cliente, pedido: Pedido, e: dict):
    datos = e | (pedido.preparar(e) if pedido.preparar else {})
    ruta = pedido.ruta.format(**(datos | {parametro: datos[dato] for parametro, dato in pedido.alias.items()}))
    cuerpo = pedido.cuerpo(e) if callable(pedido.cuerpo) else pedido.cuerpo
    consulta = {k: [str(v).format(**datos) for v in vs] for k, vs in pedido.consulta.items()}
    return cliente.request(pedido.metodo, ruta, json=cuerpo, params=consulta)


def _esperado(rol: str, valor: str, pedido: Pedido) -> str | int:
    if valor == "Si":
        return "2xx"
    if valor == "Solo compartidas":
        # Lo compartido sí; los endpoints del estudio, no: el token no es una sesión.
        return "2xx" if pedido in COMPARTIDOS else 401
    return 401 if rol == "Cliente" else 403


@pytest.mark.parametrize(("fila", "rol", "valor", "pedido"), CELDAS)
def test_celda_de_la_tabla(fila, rol, valor, pedido, escenario, clientes_por_rol):
    respuesta = _pedir(clientes_por_rol[rol], pedido, escenario)
    esperado = _esperado(rol, valor, pedido)
    if esperado == "2xx":
        cumple = 200 <= respuesta.status_code < 300
    else:
        cumple = respuesta.status_code == esperado
    RESULTADOS.setdefault((fila, rol), []).append("ok" if cumple else f"{pedido}: {respuesta.status_code}")
    assert cumple, f"{rol} en «{fila}» ({valor}): {pedido} dio {respuesta.status_code}, se esperaba {esperado}. {respuesta.text[:300]}"


def test_imprimir_la_tabla():
    """Con -s, la tabla de la p. 54 como la respondió la API: ✓ se cumple, ✗ no. Ninguna celda puede quedar
    sin probar (·)."""
    ancho = max(len(fila) for fila, _ in TABLA)
    print()
    print(f"{'Funcionalidad (p. 54)':<{ancho}}  " + "  ".join(f"{rol:<18}" for rol in ROLES))
    for fila, valores in TABLA:
        celdas = []
        for rol, valor in zip(ROLES, valores, strict=True):
            resultados = RESULTADOS.get((fila, rol), [])
            if not resultados:
                marca = "·"
            elif all(r == "ok" for r in resultados):
                marca = "✓"
            else:
                marca = "✗"
            celdas.append(f"{marca} {valor:<16}")
        print(f"{fila:<{ancho}}  " + "  ".join(celdas))
    fallidas = [(clave, r) for clave, rs in RESULTADOS.items() for r in rs if r != "ok"]
    assert not fallidas, fallidas
    sin_probar = [(fila, rol) for fila, _ in TABLA for rol in ROLES if not RESULTADOS.get((fila, rol))]
    assert not sin_probar, f"Celdas sin probar: {sin_probar}"


# --- La meta-prueba: todo endpoint declara su función y está en la tabla -------------------------


def _rutas() -> list[tuple[str, str, APIRoute]]:
    rutas = []
    for incluido in app.routes:
        router = getattr(incluido, "original_router", None)
        for ruta in getattr(router, "routes", []):
            if isinstance(ruta, APIRoute):
                for metodo in ruta.methods:
                    rutas.append((metodo, API_PREFIX + ruta.path, ruta))
    return rutas


def _dependencias(dependant):
    for dependencia in dependant.dependencies:
        yield dependencia.call
        yield from _dependencias(dependencia)


def test_todo_endpoint_declara_una_funcion_de_la_tabla_y_esta_en_su_fila():
    """Un endpoint nuevo sin `requiere(Funcion.X)`, o que no figure en la fila de su función, no pasa."""
    en_la_prueba = {(p.metodo, p.ruta): fila for fila, pedidos in ENDPOINTS.items() for p in pedidos}
    declarados = {}
    for metodo, ruta, objeto in _rutas():
        funciones = {f for f in (getattr(c, "funcion", None) for c in _dependencias(objeto.dependant)) if f}
        dependencias = set(_dependencias(objeto.dependant))
        clave = (metodo, ruta)
        if clave in PUBLICOS:
            assert not funciones, clave
            continue
        if clave in SOLO_SESION:
            assert not funciones and sesion_actual in dependencias, clave
            continue
        if clave in SOLO_ENLACE:
            # Solo lectura, con el enlace como única identidad (CU15).
            assert metodo == "GET" and not funciones, clave
            assert enlace_actual in dependencias and sesion_actual not in dependencias, clave
            continue
        assert enlace_actual not in dependencias, f"{metodo} {ruta}: el token de un enlace solo abre /compartido"
        assert len(funciones) == 1, f"{metodo} {ruta} tiene que declarar una función de la p. 54: {funciones}"
        declarados[clave] = str(funciones.pop())
    assert set(declarados) == set(en_la_prueba), set(declarados) ^ set(en_la_prueba)
    for clave, funcion in declarados.items():
        assert FUNCION_DE_FILA[en_la_prueba[clave]] == funcion, (clave, funcion)
    # Las públicas, las de solo sesión y las del enlace existen de verdad.
    todas = {(m, r) for m, r, _ in _rutas()}
    assert PUBLICOS | SOLO_SESION | SOLO_ENLACE <= todas
    assert {(p.metodo, p.ruta) for p in COMPARTIDOS} == SOLO_ENLACE
