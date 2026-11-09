"""Seleccionar, compartir y ver lo compartido (CU14, CU15, RF16; p. 45; Seguridad, p. 54; D70, D71).

- Compartir con una observación bloqueante sin responder da 409 (p. 45); después de responderla, se puede.
- El vencimiento: obligatorio y de 30 días como máximo; vencido o revocado, el cliente no entra (410).
- El token se guarda hasheado, y nunca va en la dirección.
- El enlace está atado a versiones: lo que se genere después no cambia lo que ve el cliente.
- El cliente ve exactamente lo que menciona el CU15, y nada del estudio.
"""

import hashlib
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import reloj as reloj_api
from app.core.permisos import Rol
from app.main import app
from tests.datos_referencia import cuerpo_recalculo
from tests.identidades import USUARIOS, iniciar_sesion

DESCRIPCION = "Los lotes del cierre norte no alcanzan la superficie mínima."


def hoy_mas(dias: int) -> str:
    return (reloj_api.hoy() + timedelta(days=dias)).isoformat()


@pytest.fixture
def proyecto(crear_proyecto, generar) -> dict:
    """Un proyecto con la alternativa A."""
    datos = crear_proyecto()
    datos["A"] = generar(datos["id_proyecto"])
    return datos


def seleccionar(cliente, proyecto: dict, codigos=("A",)):
    return cliente.patch(f"/api/proyectos/{proyecto['id_proyecto']}/seleccion", json={"alternativas": list(codigos)})


def compartir(cliente, proyecto: dict, dias: int = 7, **cambios):
    return cliente.post(f"/api/proyectos/{proyecto['id_proyecto']}/enlaces", json={"fecha_vencimiento": hoy_mas(dias)} | cambios)


def compartido(cliente, proyecto: dict, codigos=("A",), dias: int = 7) -> str:
    """Selecciona y comparte; devuelve el token."""
    assert seleccionar(cliente, proyecto, codigos).status_code == 200
    respuesta = compartir(cliente, proyecto, dias)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["token"]


def del_cliente(token: str) -> TestClient:
    """El navegador del cliente: sin sesión, con el token en el encabezado, como lo manda la página (D71)."""
    navegador = TestClient(app)
    navegador.headers["Authorization"] = f"Bearer {token}"
    return navegador


def observar(cliente, alternativa: dict, criticidad: str = "bloqueante") -> dict:
    respuesta = cliente.post(
        f"/api/versiones/{alternativa['version']['id_version']}/observaciones",
        json={"tipo": "dimensional", "criticidad": criticidad, "descripcion": DESCRIPCION},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def responder(cliente, observacion: dict):
    respuesta = cliente.post(
        f"/api/observaciones/{observacion['id_observacion']}/respuestas",
        json={"accion": "justificacion", "descripcion": "Cumple: se midió de nuevo."},
    )
    assert respuesta.status_code == 201, respuesta.text


# --- CU14 -------------------------------------------------------------------------------------------


def test_compartir_y_ver_como_cliente(cliente, cliente_proyectista, proyecto):
    """El proyectista también comparte (la tabla de la p. 54 manda sobre el CU14, D29)."""
    seleccion = seleccionar(cliente_proyectista, proyecto)
    assert seleccion.status_code == 200, seleccion.text
    assert [a["estado"] for a in seleccion.json()["alternativas"]] == ["seleccionada"]
    creado = compartir(cliente_proyectista, proyecto)
    assert creado.status_code == 201, creado.text
    assert creado.headers["Cache-Control"] == "no-store"
    cuerpo = creado.json()
    assert cuerpo["enlace"]["estado"] == "vigente"
    assert cuerpo["enlace"]["creado_por"]["nombre"] == "Pedro"
    assert [(v["codigo_alternativa"], v["numero_version"]) for v in cuerpo["enlace"]["versiones"]] == [("A", 1)]
    navegador = del_cliente(cuerpo["token"])
    vista = navegador.get("/api/compartido")
    assert vista.status_code == 200, vista.text
    assert vista.headers["Cache-Control"] == "no-store"
    assert vista.json()["alternativas"] == ["A"]
    assert vista.json()["proyecto"]["nombre"] == proyecto["nombre"]
    alternativa = navegador.get("/api/compartido/alternativas/A")
    assert alternativa.status_code == 200, alternativa.text
    assert alternativa.json()["indicadores"]["cantidad_lotes"] == proyecto["A"]["version"]["indicadores"]["cantidad_celdas"]


def test_2a_una_bloqueante_sin_responder_impide_compartir_y_respondida_ya_no(cliente, proyecto):
    observacion = observar(cliente, proyecto["A"])
    respuesta = seleccionar(cliente, proyecto)
    assert respuesta.status_code == 409, respuesta.text
    error = respuesta.json()
    assert error["causa"] == "No se puede compartir una alternativa con observaciones bloqueantes sin responder."
    assert error["problemas"] == [
        {"campo": "alternativas[0]", "mensaje": "La alternativa A tiene una observación bloqueante sin responder: O-1 (dimensional)."}
    ]
    # No cambió nada, y no hay nada seleccionado para compartir.
    assert compartir(cliente, proyecto).status_code == 422
    responder(cliente, observacion)
    assert seleccionar(cliente, proyecto).status_code == 200
    assert compartir(cliente, proyecto).status_code == 201


def test_una_sugerida_no_bloquea(cliente, proyecto):
    observar(cliente, proyecto["A"], "sugerida")
    assert seleccionar(cliente, proyecto).status_code == 200
    assert compartir(cliente, proyecto).status_code == 201


def test_observar_la_saca_de_la_seleccion(cliente, proyecto):
    """Registrar una observación pasa la alternativa a «observada»: hay que volver a seleccionarla (D69)."""
    assert seleccionar(cliente, proyecto).status_code == 200
    observar(cliente, proyecto["A"], "sugerida")
    respuesta = compartir(cliente, proyecto)
    assert respuesta.status_code == 422
    assert respuesta.json()["causa"] == "No hay alternativas seleccionadas para compartir."


def test_compartir_vuelve_a_controlar_las_bloqueantes(cliente, proyecto, db):
    """Lo último antes de darle acceso al cliente: aunque una alternativa figure seleccionada (acá, forzado
    en la base), con una bloqueante abierta no se comparte."""
    observar(cliente, proyecto["A"])
    db.execute(text("UPDATE alternativa SET estado = 'seleccionada' WHERE id_alternativa = :a"), {"a": proyecto["A"]["id_alternativa"]})
    db.commit()
    assert compartir(cliente, proyecto).status_code == 409


def test_la_seleccion_es_exactamente_la_pedida(cliente, proyecto, generar):
    generar(proyecto["id_proyecto"])
    assert [a["estado"] for a in seleccionar(cliente, proyecto, ["A", "B"]).json()["alternativas"]] == ["seleccionada"] * 2
    assert [a["estado"] for a in seleccionar(cliente, proyecto, ["B"]).json()["alternativas"]] == ["generada", "seleccionada"]
    assert [a["estado"] for a in seleccionar(cliente, proyecto, []).json()["alternativas"]] == ["generada", "generada"]
    inexistente = seleccionar(cliente, proyecto, ["Z"])
    assert inexistente.status_code == 422
    assert inexistente.json()["problemas"][0]["campo"] == "alternativas[0]"


# --- El vencimiento ----------------------------------------------------------------------------------


def test_el_vencimiento_es_obligatorio_y_de_30_dias_como_maximo(cliente, proyecto):
    assert seleccionar(cliente, proyecto).status_code == 200
    url = f"/api/proyectos/{proyecto['id_proyecto']}/enlaces"
    sin_fecha = cliente.post(url, json={})
    assert sin_fecha.status_code == 422
    assert sin_fecha.json()["problemas"] == [{"campo": "fecha_vencimiento", "mensaje": "Falta este dato."}]
    for dias in (-1, 31):
        respuesta = compartir(cliente, proyecto, dias)
        assert respuesta.status_code == 422, dias
        assert respuesta.json()["problemas"][0]["campo"] == "fecha_vencimiento"
    assert cliente.post(url, json={"fecha_vencimiento": "mañana"}).status_code == 422
    a_30 = compartir(cliente, proyecto, 30)
    assert a_30.status_code == 201
    assert compartir(cliente, proyecto, 0).status_code == 201
    # El vencimiento es el último instante del día elegido: leído en la hora de Córdoba, es ese día (no el
    # siguiente), y así lo muestran la lista y la página del cliente.
    vence = datetime.fromisoformat(a_30.json()["enlace"]["fecha_vencimiento"]).astimezone(reloj_api.CORDOBA)
    assert vence.date().isoformat() == hoy_mas(30)
    assert (vence.hour, vence.minute, vence.second) == (23, 59, 59)


def test_vale_hasta_el_final_del_dia_elegido_y_despues_bloquea_el_ingreso(cliente, proyecto, reloj):
    token = compartido(cliente, proyecto, dias=0)
    navegador = del_cliente(token)
    assert navegador.get("/api/compartido").status_code == 200
    # Hasta el último segundo de hoy, en Córdoba.
    falta = reloj_api.fin_del_dia(reloj_api.hoy()) - reloj_api.ahora()
    reloj.adelantar(seconds=falta.total_seconds() - 1)
    assert navegador.get("/api/compartido").status_code == 200
    reloj.adelantar(seconds=1)
    vencido = navegador.get("/api/compartido")
    assert vencido.status_code == 410
    assert vencido.json()["causa"] == "Este enlace no está disponible."
    assert "Pedile al estudio" in vencido.json()["sugerencia"]
    assert navegador.get("/api/compartido/alternativas/A").status_code == 410
    # Si faltaban más de 12 h para el final del día, la sesión del director ya venció (D63): se entra de nuevo.
    director = TestClient(app)
    assert iniciar_sesion(director, USUARIOS[Rol.DIRECTOR_TECNICO][0]).status_code == 200
    [enlace] = director.get(f"/api/proyectos/{proyecto['id_proyecto']}/enlaces").json()
    assert enlace["estado"] == "vencido"


def test_revocado_bloquea_el_ingreso(cliente, proyecto):
    token = compartido(cliente, proyecto)
    navegador = del_cliente(token)
    assert navegador.get("/api/compartido").status_code == 200
    [enlace] = cliente.get(f"/api/proyectos/{proyecto['id_proyecto']}/enlaces").json()
    revocado = cliente.patch(f"/api/enlaces/{enlace['id_enlace']}", json={"revocado": True})
    assert revocado.status_code == 200
    assert revocado.json()["estado"] == "revocado"
    assert navegador.get("/api/compartido").status_code == 410
    assert navegador.get("/api/compartido/alternativas/A").status_code == 410
    # No tiene vuelta atrás.
    assert cliente.patch(f"/api/enlaces/{enlace['id_enlace']}", json={"revocado": False}).status_code == 422


def test_sin_token_401_y_un_token_que_no_existe_404(anonimo):
    assert anonimo.get("/api/compartido").status_code == 401
    assert del_cliente("no-es-un-token").get("/api/compartido").status_code == 404
    # El token en la dirección no se acepta: la API lo lee solo del encabezado (D71).
    assert anonimo.get("/api/compartido", params={"token": "x"}).status_code == 401


# --- El token ---------------------------------------------------------------------------------------


def test_el_token_se_guarda_hasheado(cliente, proyecto, db):
    token = compartido(cliente, proyecto)
    guardado = db.scalar(
        text("SELECT token FROM enlace_compartido WHERE id_proyecto = :p"), {"p": proyecto["id_proyecto"]}
    )
    assert guardado == hashlib.sha256(token.encode()).hexdigest()
    assert token not in guardado
    # La lista nunca lo muestra.
    assert token not in cliente.get(f"/api/proyectos/{proyecto['id_proyecto']}/enlaces").text


def test_ninguna_ruta_lleva_un_token_en_la_direccion():
    """El token viaja en `Authorization`, nunca en la ruta ni en la consulta: así no queda en los
    registros de Nginx ni de Uvicorn (D71)."""
    from fastapi.routing import APIRoute

    for incluido in app.routes:
        for ruta in getattr(getattr(incluido, "original_router", None), "routes", []):
            if isinstance(ruta, APIRoute):
                assert "token" not in ruta.path.lower(), ruta.path
                parametros = [p.name for p in ruta.dependant.query_params + ruta.dependant.path_params]
                assert not any("token" in p for p in parametros), (ruta.path, parametros)


# --- Lo que ve el cliente ----------------------------------------------------------------------------


def test_una_version_nueva_no_cambia_lo_que_ve_el_cliente(cliente, proyecto):
    """El enlace está atado a la versión que se compartió (p. 45)."""
    token = compartido(cliente, proyecto)
    navegador = del_cliente(token)
    antes = navegador.get("/api/compartido/alternativas/A").json()
    v1 = proyecto["A"]["version"]["id_version"]
    v2 = cliente.post(f"/api/versiones/{v1}/recalculos", json=cuerpo_recalculo(["M2"]))
    assert v2.status_code == 201, v2.text
    observar(cliente, v2.json())
    assert navegador.get("/api/compartido/alternativas/A").json() == antes
    assert navegador.get("/api/compartido").json()["alternativas"] == ["A"]
    # El estudio ve la versión nueva.
    assert cliente.get(f"/api/alternativas/{proyecto['A']['id_alternativa']}").json()["version"]["numero"] == 2


def test_una_alternativa_que_no_se_compartio_no_existe_para_el_cliente(cliente, proyecto, generar):
    generar(proyecto["id_proyecto"])
    token = compartido(cliente, proyecto, ["A"])
    navegador = del_cliente(token)
    assert navegador.get("/api/compartido").json()["alternativas"] == ["A"]
    respuesta = navegador.get("/api/compartido/alternativas/B")
    assert respuesta.status_code == 404
    assert respuesta.json()["causa"] == "Este enlace no comparte la alternativa B."


def test_el_cliente_ve_exactamente_lo_que_menciona_el_cu15(cliente, crear_proyecto, generar):
    """El conjunto exacto de claves: sumar un dato a la vista del cliente es una decisión, y cambia esta
    prueba. Nada del estudio (ids, versiones, estrategia, parámetros, observaciones, incumplimientos,
    código, CUIT ni contactos), salvo su nombre, quién compartió (la inicial, el apellido y el rol: D75) y
    la descripción del trazado (D76). Con un área reservada, para ver también su capa."""
    proyecto = crear_proyecto(caso="reservada_centro")
    proyecto["A"] = generar(proyecto["id_proyecto"])
    observar(cliente, proyecto["A"], "sugerida")
    navegador = del_cliente(compartido(cliente, proyecto))
    vista = navegador.get("/api/compartido").json()
    assert set(vista) == {"estudio", "proyecto", "alternativas", "compartido_por", "vence"}
    assert set(vista["proyecto"]) == {"nombre", "ubicacion", "cliente", "superficie_terreno_m2"}
    assert set(vista["compartido_por"]) == {"nombre", "rol"}
    alternativa = navegador.get("/api/compartido/alternativas/A").json()
    assert set(alternativa) == {"codigo", "descripcion", "indicadores", "capas"}
    assert set(alternativa["indicadores"]) == {
        "cantidad_lotes",
        "superficie_media_lote_m2",
        "superficie_aprovechable_m2",
        "porcentaje_aprovechamiento",
        "superficie_espacio_verde_m2",
        "porcentaje_espacio_verde",
        "longitud_red_m",
        "superficie_terreno_m2",
    }
    capas = alternativa["capas"]
    assert set(capas) == {"terreno", "accesos", "calles", "manzanas", "celdas", "areas_reservadas"}
    propiedades = {
        nombre: set().union(*(set(f["properties"]) for f in capa["features"]))
        for nombre, capa in capas.items()
        if nombre != "terreno"
    }
    assert propiedades == {
        "accesos": {"designacion"},
        "calles": {"jerarquia"},
        "manzanas": {"designacion"},
        "celdas": {"designacion", "tipo"},
        "areas_reservadas": {"designacion", "denominacion"},
    }
    assert capas["terreno"]["properties"] == {}
    todo = navegador.get("/api/compartido").text + navegador.get("/api/compartido/alternativas/A").text
    for interno in (proyecto["codigo"], DESCRIPCION, "id_version", "semilla", "cumple", "fijad", "@"):
        assert interno not in todo, interno


def test_cada_apertura_cuenta_un_acceso(cliente, proyecto):
    navegador = del_cliente(compartido(cliente, proyecto))
    for _ in range(3):
        assert navegador.get("/api/compartido").status_code == 200
    # Ver una alternativa no es abrir el enlace.
    assert navegador.get("/api/compartido/alternativas/A").status_code == 200
    [enlace] = cliente.get(f"/api/proyectos/{proyecto['id_proyecto']}/enlaces").json()
    assert enlace["cantidad_accesos"] == 3
    assert enlace["ultimo_acceso"] is not None
