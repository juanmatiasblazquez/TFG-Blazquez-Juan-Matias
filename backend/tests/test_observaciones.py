"""Registrar y responder observaciones (CU11, CU12, RF17; D69).

- CU11: la observación queda abierta y la alternativa, observada; un sector que excede el terreno da 422
  con la parte que sale (3.a).
- CU12: la respuesta por comentario (3.b) y por recálculo (3.a), vinculada a la versión que resultó, en la
  misma transacción.
- Los estados de la observación (abierta, respondida, cerrada; reabrir) y de la alternativa.
"""

import pytest
from shapely.geometry import box, mapping

from tests.datos_referencia import cuerpo_generacion, cuerpo_recalculo, terreno_y_accesos_4326

DESCRIPCION = "Las celdas del cierre norte no alcanzan la superficie mínima."


def poligono(geometria) -> dict:
    return {"type": "Polygon", "coordinates": [[list(p) for p in anillo] for anillo in mapping(geometria)["coordinates"]]}


def sector_adentro() -> dict:
    """Un cuadrado de unos 60 m en el centro del terreno de referencia."""
    terreno, _ = terreno_y_accesos_4326()
    c = terreno.centroid
    return poligono(box(c.x - 0.0003, c.y - 0.0003, c.x + 0.0003, c.y + 0.0003))


def sector_que_sale() -> dict:
    """Un cuadrado alrededor de un vértice del terreno: tres cuartos quedan afuera."""
    terreno, _ = terreno_y_accesos_4326()
    x, y = terreno.exterior.coords[0]
    return poligono(box(x - 0.0003, y - 0.0003, x + 0.0003, y + 0.0003))


def cuerpo(**cambios) -> dict:
    return {"tipo": "dimensional", "criticidad": "bloqueante", "descripcion": DESCRIPCION, "sector": sector_adentro()} | cambios


def respuesta_con(accion: str = "justificacion", **cambios) -> dict:
    return {"accion": accion, "descripcion": "Se revisó: cumple con la Ord. 8060."} | cambios


@pytest.fixture
def alternativa(crear_proyecto, generar) -> dict:
    return generar(crear_proyecto()["id_proyecto"])


def registrar(cliente, alternativa: dict, **cambios) -> dict:
    respuesta = cliente.post(f"/api/versiones/{alternativa['version']['id_version']}/observaciones", json=cuerpo(**cambios))
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def estado(cliente, alternativa: dict) -> str:
    return cliente.get(f"/api/alternativas/{alternativa['id_alternativa']}").json()["estado"]


def observaciones(cliente, alternativa: dict) -> list[dict]:
    respuesta = cliente.get(f"/api/alternativas/{alternativa['id_alternativa']}/observaciones")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


# --- CU11 ------------------------------------------------------------------------------------------


def test_registrar_la_deja_abierta_y_la_alternativa_observada(cliente, alternativa):
    assert estado(cliente, alternativa) == "generada"
    registrada = registrar(cliente, alternativa)
    assert registrada["designacion"] == "O-1"
    assert registrada["estado"] == "abierta"
    assert (registrada["tipo"], registrada["criticidad"]) == ("dimensional", "bloqueante")
    assert registrada["numero_version"] == 1
    assert registrada["sector"]["type"] == "Polygon"
    assert registrada["emisor"]["nombre"] == "Dora"
    assert registrada["respuestas"] == []
    assert estado(cliente, alternativa) == "observada"
    assert [o["id_observacion"] for o in observaciones(cliente, alternativa)] == [registrada["id_observacion"]]
    # Sin sector también se puede (RF17: «opcionalmente»), y la designación sigue.
    sin_sector = registrar(cliente, alternativa, sector=None, criticidad="sugerida", tipo="comercial")
    assert (sin_sector["designacion"], sin_sector["sector"]) == ("O-2", None)


def test_3a_el_sector_que_excede_el_terreno_da_422_con_la_parte_de_afuera(cliente, alternativa):
    respuesta = cliente.post(
        f"/api/versiones/{alternativa['version']['id_version']}/observaciones", json=cuerpo(sector=sector_que_sale())
    )
    assert respuesta.status_code == 422, respuesta.text
    error = respuesta.json()
    assert error["causa"] == "El sector dibujado excede el límite del terreno."
    assert error["problemas"][0]["campo"] == "sector"
    assert "afuera" in error["problemas"][0]["mensaje"]
    # La parte que sale, para marcarla en el mapa.
    assert error["geometria"]["type"] in ("Polygon", "MultiPolygon")
    assert observaciones(cliente, alternativa) == []
    assert estado(cliente, alternativa) == "generada"


def test_un_sector_que_se_cruza_a_si_mismo_da_422(cliente, alternativa):
    terreno, _ = terreno_y_accesos_4326()
    c = terreno.centroid
    d = 0.0003
    moño = {"type": "Polygon", "coordinates": [[[c.x - d, c.y - d], [c.x + d, c.y + d], [c.x + d, c.y - d], [c.x - d, c.y + d], [c.x - d, c.y - d]]]}
    respuesta = cliente.post(f"/api/versiones/{alternativa['version']['id_version']}/observaciones", json=cuerpo(sector=moño))
    assert respuesta.status_code == 422
    assert respuesta.json()["problemas"][0]["campo"] == "sector"


def test_la_vista_previa_del_sector_mide_como_al_registrar(cliente, alternativa):
    """Mientras se dibuja (figura 19; D79): la superficie y, si sale, cuánto y dónde, con el mismo mensaje
    que daría registrarla. No registra nada."""
    ruta = f"/api/versiones/{alternativa['version']['id_version']}/observaciones/sector"
    adentro = cliente.post(ruta, json={"sector": sector_adentro()})
    assert adentro.status_code == 200, adentro.text
    medido = adentro.json()
    # Unos 60 m de lado.
    assert 2500 < medido["superficie_m2"] < 5000
    assert (medido["afuera_m2"], medido["afuera"], medido["problema"]) == (0.0, None, None)

    sale = cliente.post(ruta, json={"sector": sector_que_sale()}).json()
    assert sale["afuera_m2"] > sale["superficie_m2"] / 2
    assert sale["afuera"]["type"] in ("Polygon", "MultiPolygon")
    registro = cliente.post(
        f"/api/versiones/{alternativa['version']['id_version']}/observaciones", json=cuerpo(sector=sector_que_sale())
    )
    assert sale["problema"] == registro.json()["problemas"][0]["mensaje"]
    assert observaciones(cliente, alternativa) == []
    assert cliente.post("/api/versiones/999999/observaciones/sector", json={"sector": sector_adentro()}).status_code == 404


def test_los_valores_son_los_del_acta(cliente, alternativa):
    """Tipo y criticidad del Anexo 1.5: otro valor da 422 con la lista."""
    url = f"/api/versiones/{alternativa['version']['id_version']}/observaciones"
    respuesta = cliente.post(url, json=cuerpo(tipo="estetica"))
    assert respuesta.status_code == 422
    assert "normativa" in respuesta.json()["problemas"][0]["mensaje"]
    assert cliente.post(url, json=cuerpo(criticidad="urgente")).status_code == 422


def test_se_observa_la_version_vigente(cliente, alternativa):
    v1 = alternativa["version"]["id_version"]
    v2 = cliente.post(f"/api/versiones/{v1}/recalculos", json=cuerpo_recalculo(["M2"]))
    assert v2.status_code == 201, v2.text
    respuesta = cliente.post(f"/api/versiones/{v1}/observaciones", json=cuerpo())
    assert respuesta.status_code == 409
    assert "no es la vigente" in respuesta.json()["causa"]
    nueva = cliente.post(f"/api/versiones/{v2.json()['version']['id_version']}/observaciones", json=cuerpo())
    assert nueva.status_code == 201
    assert nueva.json()["numero_version"] == 2


# --- CU12 ------------------------------------------------------------------------------------------


def test_3b_responder_con_un_comentario(cliente, cliente_proyectista, alternativa):
    registrada = registrar(cliente, alternativa)
    respuesta = cliente_proyectista.post(
        f"/api/observaciones/{registrada['id_observacion']}/respuestas", json=respuesta_con("aclaracion")
    )
    assert respuesta.status_code == 201, respuesta.text
    observacion = respuesta.json()
    assert observacion["estado"] == "respondida"
    [unica] = observacion["respuestas"]
    assert unica["accion"] == "aclaracion"
    assert unica["usuario"]["nombre"] == "Pedro"
    assert (unica["id_version_resultante"], unica["numero_version_resultante"]) == (None, None)
    # Era la única abierta: la alternativa vuelve a generada (D69).
    assert estado(cliente, alternativa) == "generada"


def test_3a_responder_con_un_recalculo_vincula_la_version_nueva(cliente, cliente_proyectista, alternativa):
    """El CU09 dentro de la respuesta: la versión n + 1 es «recalculada» y la respuesta queda vinculada a
    ella (CU12, paso 5). La versión observada no cambia."""
    v1 = alternativa["version"]
    registrada = registrar(cliente, alternativa)
    respuesta = cliente_proyectista.post(
        f"/api/observaciones/{registrada['id_observacion']}/respuestas",
        json=respuesta_con(
            "recalculo_parcial",
            descripcion="Se recalculó el cierre norte conservando M2.",
            recalculo={"id_version": v1["id_version"], "manzanas": ["M2"]} | cuerpo_generacion(),
        ),
    )
    assert respuesta.status_code == 201, respuesta.text
    [unica] = respuesta.json()["respuestas"]
    assert unica["accion"] == "recalculo_parcial"
    assert unica["numero_version_resultante"] == 2
    nueva = cliente.get(f"/api/versiones/{unica['id_version_resultante']}").json()["version"]
    assert nueva["tipo"] == "recalculada"
    assert nueva["id_version_origen"] == v1["id_version"]
    assert nueva["generada_por"]["nombre"] == "Pedro"
    # «Responde a O-1» (p. 50; D74), y la versión observada no responde a nada.
    assert nueva["responde_a"] == [registrada["designacion"]] == ["O-1"]
    assert cliente.get(f"/api/versiones/{v1['id_version']}").json()["version"]["responde_a"] == []
    assert [m["properties"]["designacion"] for m in nueva["capas"]["manzanas"]["features"] if m["properties"]["fijada"]] == ["M2"]
    leida = cliente.get(f"/api/alternativas/{alternativa['id_alternativa']}").json()
    assert leida["version"]["id_version"] == unica["id_version_resultante"]
    assert leida["estado"] == "generada"
    # La observación sigue colgando de la versión observada.
    assert observaciones(cliente, alternativa)[0]["numero_version"] == 1


def test_si_el_recalculo_falla_no_queda_ni_la_version_ni_la_respuesta(cliente, cliente_proyectista, alternativa):
    """Fijar todas las manzanas no deja nada que recalcular (CU09, 3.a): 422, y la observación sigue
    abierta, sin respuesta y sin versión nueva."""
    registrada = registrar(cliente, alternativa)
    todas = [m["properties"]["designacion"] for m in alternativa["version"]["capas"]["manzanas"]["features"]]
    respuesta = cliente_proyectista.post(
        f"/api/observaciones/{registrada['id_observacion']}/respuestas",
        json=respuesta_con(
            "recalculo_parcial",
            recalculo={"id_version": alternativa["version"]["id_version"], "manzanas": todas} | cuerpo_generacion(),
        ),
    )
    assert respuesta.status_code == 422, respuesta.text
    [observacion] = observaciones(cliente, alternativa)
    assert (observacion["estado"], observacion["respuestas"]) == ("abierta", [])
    assert len(cliente.get(f"/api/alternativas/{alternativa['id_alternativa']}").json()["versiones"]) == 1
    assert estado(cliente, alternativa) == "observada"


def test_el_recalculo_parte_de_la_version_vigente(cliente, alternativa):
    registrada = registrar(cliente, alternativa)
    v1 = alternativa["version"]["id_version"]
    otra = registrar(cliente, alternativa, criticidad="sugerida")
    # Una respuesta con recálculo crea la v2.
    primera = cliente.post(
        f"/api/observaciones/{registrada['id_observacion']}/respuestas",
        json=respuesta_con("recalculo_parcial", recalculo={"id_version": v1, "manzanas": ["M2"]} | cuerpo_generacion()),
    )
    assert primera.status_code == 201, primera.text
    # La segunda, armada sobre la v1, ya no sirve: la vigente es la v2.
    respuesta = cliente.post(
        f"/api/observaciones/{otra['id_observacion']}/respuestas",
        json=respuesta_con("recalculo_parcial", recalculo={"id_version": v1, "manzanas": ["M2"]} | cuerpo_generacion()),
    )
    assert respuesta.status_code == 409
    assert "la vigente es la 2" in respuesta.json()["causa"]


def test_la_accion_y_el_recalculo_van_juntos(cliente, alternativa):
    registrada = registrar(cliente, alternativa)
    url = f"/api/observaciones/{registrada['id_observacion']}/respuestas"
    sin_recalculo = cliente.post(url, json=respuesta_con("recalculo_parcial"))
    assert sin_recalculo.status_code == 422
    assert sin_recalculo.json()["problemas"][0]["campo"] == "recalculo"
    con_recalculo = cliente.post(
        url,
        json=respuesta_con(
            "justificacion",
            recalculo={"id_version": alternativa["version"]["id_version"], "manzanas": ["M2"]} | cuerpo_generacion(),
        ),
    )
    assert con_recalculo.status_code == 422
    assert cliente.post(url, json=respuesta_con("ajuste_local")).status_code == 422


def test_una_observacion_se_responde_una_vez(cliente, alternativa):
    registrada = registrar(cliente, alternativa)
    url = f"/api/observaciones/{registrada['id_observacion']}/respuestas"
    assert cliente.post(url, json=respuesta_con()).status_code == 201
    otra = cliente.post(url, json=respuesta_con())
    assert otra.status_code == 409
    assert "ya está respondida" in otra.json()["causa"]


# --- Los estados ----------------------------------------------------------------------------------


def test_la_alternativa_sigue_observada_mientras_quede_una_abierta(cliente, alternativa):
    """También una sugerida la deja observada (CU11, paso 5), y vuelve a generada recién cuando no queda
    ninguna abierta (D69)."""
    bloqueante = registrar(cliente, alternativa)
    sugerida = registrar(cliente, alternativa, criticidad="sugerida", tipo="comercial", sector=None)
    assert cliente.post(f"/api/observaciones/{bloqueante['id_observacion']}/respuestas", json=respuesta_con()).status_code == 201
    assert estado(cliente, alternativa) == "observada"
    assert cliente.post(f"/api/observaciones/{sugerida['id_observacion']}/respuestas", json=respuesta_con()).status_code == 201
    assert estado(cliente, alternativa) == "generada"
    resumen = next(
        a for a in cliente.get(f"/api/proyectos/{alternativa['id_proyecto']}").json()["alternativas"]
        if a["id_alternativa"] == alternativa["id_alternativa"]
    )
    assert (resumen["observaciones_abiertas"], resumen["bloqueantes_abiertas"]) == (0, 0)


def test_cerrar_y_reabrir(cliente, alternativa, db):
    """`cerrar()` y `reabrir()` (p. 46), solo sobre una respondida. Cerrada es final; reabierta vuelve a
    observar la alternativa y admite otra respuesta."""
    from sqlalchemy import text

    primera = registrar(cliente, alternativa)
    url = f"/api/observaciones/{primera['id_observacion']}"
    assert cliente.patch(url, json={"estado": "cerrada"}).status_code == 409
    assert cliente.post(f"{url}/respuestas", json=respuesta_con()).status_code == 201
    cerrada = cliente.patch(url, json={"estado": "cerrada"})
    assert cerrada.status_code == 200, cerrada.text
    assert cerrada.json()["estado"] == "cerrada"
    assert cerrada.json()["fecha_cierre"] is not None
    assert cliente.patch(url, json={"estado": "abierta"}).status_code == 409
    assert estado(cliente, alternativa) == "generada"

    segunda = registrar(cliente, alternativa)
    url = f"/api/observaciones/{segunda['id_observacion']}"
    assert cliente.post(f"{url}/respuestas", json=respuesta_con()).status_code == 201
    assert estado(cliente, alternativa) == "generada"
    reabierta = cliente.patch(url, json={"estado": "abierta"})
    assert reabierta.status_code == 200
    assert reabierta.json()["estado"] == "abierta"
    assert estado(cliente, alternativa) == "observada"
    otra = cliente.post(f"{url}/respuestas", json=respuesta_con("aclaracion"))
    assert otra.status_code == 201
    assert [r["accion"] for r in otra.json()["respuestas"]] == ["justificacion", "aclaracion"]
    # La base guarda las dos respuestas; la observación cambió solo de estado.
    assert db.scalar(text("SELECT count(*) FROM respuesta_observacion WHERE id_observacion = :o"), {"o": segunda["id_observacion"]}) == 2


def test_el_proyectista_responde_pero_no_registra_ni_cierra(cliente, cliente_proyectista, cliente_consultor, alternativa):
    """La tabla de la p. 54 lo prueba en `test_tabla_roles.py`; acá, el recorrido con los dos roles."""
    url = f"/api/versiones/{alternativa['version']['id_version']}/observaciones"
    assert cliente_proyectista.post(url, json=cuerpo()).status_code == 403
    registrada = registrar(cliente, alternativa)
    assert cliente_consultor.post(f"/api/observaciones/{registrada['id_observacion']}/respuestas", json=respuesta_con()).status_code == 403
    assert cliente_proyectista.post(f"/api/observaciones/{registrada['id_observacion']}/respuestas", json=respuesta_con()).status_code == 201
    assert cliente_proyectista.patch(f"/api/observaciones/{registrada['id_observacion']}", json={"estado": "cerrada"}).status_code == 403
    # El consultor las ve.
    assert len(observaciones(cliente_consultor, alternativa)) == 1
