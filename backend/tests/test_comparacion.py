"""CU13: comparar dos o tres alternativas del mismo proyecto (RF15, p. 51; D54).

- Los valores son los mismos que da el GET de cada alternativa (copia única: `indicadores_de`).
- La diferencia es contra la primera, y el mejor se resalta solo donde la dirección no se discute.
- Lo que difiere se compara por valor: una versión de los parámetros con los mismos valores no
  aparece.
- Es de solo lectura, y responde 404 o 422 con el campo `alternativas`.

Se usa el caso irregular: genera en menos de un segundo, y sus dos criterios del verde dan
alternativas distintas (D51).
"""

import pytest

# El pedido del autor: qué indicadores tienen una dirección clara y cuáles son una disyuntiva.
SENTIDOS = {
    "cantidad_celdas": "mayor",
    "superficie_aprovechable_m2": "mayor",
    "porcentaje_aprovechamiento": "mayor",
    # Las de la p. 51 que suma la sesión 10, disyuntivas (D57); el verde, total y computable (D55).
    "superficie_media_celda_m2": None,
    "porcentaje_circulacion": None,
    "longitud_red_m": None,
    "porcentaje_avenidas": None,
    "porcentaje_espacio_verde": None,
    "superficie_verde_computable_m2": None,
    "porcentaje_cesion": None,
    "distancia_media_verde_m": "menor",
    "distancia_maxima_verde_m": "menor",
    "distancia_media_acceso_m": "menor",
    "cantidad_incumplimientos": "menor",
}


# La última fila de la p. 51, solo entre alternativas (D84).
BLOQUEANTES = "observaciones_bloqueantes_abiertas"


def comparar(cliente, id_proyecto: int, *ids: int):
    consulta = "&".join(f"alternativas={i}" for i in ids)
    return cliente.get(f"/api/proyectos/{id_proyecto}/comparacion?{consulta}")


def con_criterio(cliente, id_proyecto: int, criterio: str) -> int:
    """CU05: una versión nueva de los parámetros de referencia con este criterio del verde."""
    valores = cliente.get("/api/parametros/referencia").json()["valores"]
    valores["loteo"]["criterio_espacio_verde"] = criterio
    respuesta = cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["version"]


def esperados(valores: list, sentido: str | None) -> list[int]:
    """La regla de D54, escrita aparte: los índices con el mejor valor, salvo que todas empaten."""
    if sentido is None:
        return []
    compiten = [v for v in valores if v is not None]
    mejor = max(compiten) if sentido == "mayor" else min(compiten)
    ganadoras = [k for k, v in enumerate(valores) if v == mejor]
    return [] if len(ganadoras) == len(compiten) else ganadoras


def test_dos_orientaciones(cliente, crear_proyecto, generar):
    id_proyecto = crear_proyecto(caso="irregular")["id_proyecto"]
    a = generar(id_proyecto)
    b = generar(id_proyecto, orientacion_grados=110.0)
    respuesta = comparar(cliente, id_proyecto, a["id_alternativa"], b["id_alternativa"])
    assert respuesta.status_code == 200, respuesta.text
    c = respuesta.json()

    assert [x["codigo"] for x in c["alternativas"]] == ["A", "B"]
    assert [x["estrategia"]["orientacion_grados"] for x in c["alternativas"]] == [20.0, 110.0]
    assert all(x["numero"] == 1 and x["version_parametros"] == 1 for x in c["alternativas"])
    # Los indicadores del pedido, en su orden, con su sentido, y al final las bloqueantes abiertas.
    assert {f["indicador"]: f["sentido"] for f in c["indicadores"]} == SENTIDOS | {BLOQUEANTES: "menor"}
    assert [f["indicador"] for f in c["indicadores"]] == [*SENTIDOS, BLOQUEANTES]
    assert c["indicadores"][-1]["valores"] == [0, 0]

    leidas = [cliente.get(f"/api/alternativas/{x['id_alternativa']}").json() for x in (a, b)]
    for fila in c["indicadores"][:-1]:
        valores = [alternativa["version"]["indicadores"][fila["indicador"]] for alternativa in leidas]
        assert fila["valores"] == valores, fila["indicador"]
        assert fila["diferencias"][0] is None
        assert fila["diferencias"][1] == pytest.approx(valores[1] - valores[0], abs=0.005)
        assert fila["mejores"] == esperados(valores, fila["sentido"]), fila["indicador"]
    # Las orientaciones dan alternativas distintas: algún indicador con dirección tiene un mejor.
    assert any(f["mejores"] for f in c["indicadores"])

    # Solo difiere la orientación: los parámetros son la misma versión.
    assert c["diferencias"] == [{"campo": "estrategia.orientacion_grados", "valores": [20.0, 110.0]}]

    # El orden lo da el pedido: al revés, los valores y las diferencias se invierten.
    inversa = comparar(cliente, id_proyecto, b["id_alternativa"], a["id_alternativa"]).json()
    for directa, invertida in zip(c["indicadores"], inversa["indicadores"], strict=True):
        assert invertida["valores"] == directa["valores"][::-1]
        if directa["diferencias"][1] is not None:
            assert invertida["diferencias"][1] == pytest.approx(-directa["diferencias"][1], abs=0.005)


def test_lo_que_difiere_se_compara_por_valor(cliente, crear_proyecto, generar):
    """A con «más cercanía» (v1), B con «menos lotes» (v2) y C con «más cercanía» otra vez (v3),
    las tres con la misma estrategia. A y B difieren solo en el criterio. A y C tienen los mismos
    valores en versiones distintas de los parámetros: no difieren en nada, y por RNF05 dan la misma
    alternativa, así que no hay mejor en ningún indicador."""
    id_proyecto = crear_proyecto(caso="irregular")["id_proyecto"]
    a = generar(id_proyecto)
    assert con_criterio(cliente, id_proyecto, "menos_lotes") == 2
    b = generar(id_proyecto)
    assert con_criterio(cliente, id_proyecto, "cercania") == 3
    c = generar(id_proyecto)

    ab = comparar(cliente, id_proyecto, a["id_alternativa"], b["id_alternativa"]).json()
    assert ab["diferencias"] == [{"campo": "loteo.criterio_espacio_verde", "valores": ["cercania", "menos_lotes"]}]
    assert [x["version_parametros"] for x in ab["alternativas"]] == [1, 2]

    ac = comparar(cliente, id_proyecto, a["id_alternativa"], c["id_alternativa"]).json()
    assert [x["version_parametros"] for x in ac["alternativas"]] == [1, 3]
    assert ac["diferencias"] == []
    for fila in ac["indicadores"]:
        assert fila["valores"][0] == fila["valores"][1], fila["indicador"]
        assert fila["mejores"] == []

    # Tres: cada diferencia es contra la primera (C − A da cero o nulo).
    abc = comparar(cliente, id_proyecto, a["id_alternativa"], b["id_alternativa"], c["id_alternativa"]).json()
    assert [x["codigo"] for x in abc["alternativas"]] == ["A", "B", "C"]
    assert abc["diferencias"] == [
        {"campo": "loteo.criterio_espacio_verde", "valores": ["cercania", "menos_lotes", "cercania"]}
    ]
    for fila in abc["indicadores"]:
        assert len(fila["valores"]) == len(fila["diferencias"]) == 3
        assert fila["diferencias"][2] in (0, None), fila["indicador"]
        assert fila["mejores"] == esperados(fila["valores"], fila["sentido"]), fila["indicador"]


def test_el_estado_las_bloqueantes_y_el_criterio_de_cada_una(cliente, crear_proyecto, generar):
    """Lo que muestra cada mapa (la casilla «Seleccionada» o «Obs. bloqueante») y la insignia del criterio
    del verde (figura 20; D83, D84)."""
    id_proyecto = crear_proyecto(caso="irregular")["id_proyecto"]
    a = generar(id_proyecto)
    assert con_criterio(cliente, id_proyecto, "menos_lotes") == 2
    b = generar(id_proyecto)
    respuesta = cliente.patch(f"/api/proyectos/{id_proyecto}/seleccion", json={"alternativas": ["A"]})
    assert respuesta.status_code == 200, respuesta.text
    observacion = {"tipo": "dimensional", "criticidad": "bloqueante", "descripcion": "Revisar el cierre."}
    respuesta = cliente.post(f"/api/versiones/{b['version']['id_version']}/observaciones", json=observacion)
    assert respuesta.status_code == 201, respuesta.text

    c = comparar(cliente, id_proyecto, a["id_alternativa"], b["id_alternativa"]).json()
    assert [(x["estado"], x["bloqueantes_abiertas"], x["criterio_espacio_verde"]) for x in c["alternativas"]] == [
        ("seleccionada", 0, "cercania"),
        ("observada", 1, "menos_lotes"),
    ]
    fila = c["indicadores"][-1]
    assert (fila["indicador"], fila["valores"], fila["diferencias"], fila["mejores"]) == (BLOQUEANTES, [0, 1], [None, 1], [0])


def test_los_errores_dicen_el_campo(cliente, crear_proyecto, generar):
    id_proyecto = crear_proyecto(caso="irregular")["id_proyecto"]
    a = generar(id_proyecto)["id_alternativa"]
    otro = crear_proyecto(caso="irregular")["id_proyecto"]
    ajena = generar(otro)["id_alternativa"]

    for ids, causa in [
        ((a,), "dos o tres"),
        ((a, a + 1, a + 2, a + 3), "dos o tres"),
        ((a, a), "consigo misma"),
        ((a, ajena), "mismo proyecto"),
    ]:
        respuesta = comparar(cliente, id_proyecto, *ids)
        assert respuesta.status_code == 422, (ids, respuesta.text)
        error = respuesta.json()
        assert causa in error["causa"] and error["sugerencia"]
        assert {p["campo"] for p in error["problemas"]} == {"alternativas"}

    sin_lista = cliente.get(f"/api/proyectos/{id_proyecto}/comparacion")
    assert sin_lista.status_code == 422
    assert sin_lista.json()["problemas"] == [{"campo": "alternativas", "mensaje": "Mandá `alternativas` o `versiones`."}]

    assert comparar(cliente, id_proyecto, a, 999_999_999).status_code == 404
    assert comparar(cliente, 999_999_999, a, ajena).status_code == 404
