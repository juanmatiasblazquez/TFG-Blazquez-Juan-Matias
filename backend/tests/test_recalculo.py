"""CU09 por la API: fijar sectores y recalcular (secuencia de la p. 44; D56).

- El recálculo da 201 con la versión n + 1 de la misma alternativa, con su origen, su sector fijado
  y las marcas de lo fijado; el 201 es lo mismo que el GET de `Location`.
- Lo fijado se guarda idéntico (las celdas y las manzanas, al bit) y la versión de origen no
  cambia (RNF04).
- Lo guardado es lo que da el motor corrido aparte sobre la versión leída de la base.
- Los cursos alternativos (3.a, 5.a) y los errores del pedido dan 422 en el campo, y no guardan nada.
- La vista previa del sector (paso 3), el GET de una versión y la comparación de dos versiones.
"""

import math
from dataclasses import replace

import motor_trazados as mt
import pytest
from geoalchemy2.shape import to_shape
from shapely import MultiLineString, box
from sqlalchemy import text

from app.models import VersionAlternativa
from app.services import fijacion
from app.services.solicitud import armar_solicitud
from tests.datos_referencia import cuerpo_recalculo
from tests.test_inmutabilidad import huella

MEDIO_CENTESIMO = 0.005 + 1e-9


@pytest.fixture
def generada(crear_proyecto, generar) -> dict:
    """El rectangular, con su alternativa A (v1)."""
    id_proyecto = crear_proyecto()["id_proyecto"]
    return generar(id_proyecto)


def recalcular(cliente, id_version: int, manzanas, **cambios):
    return cliente.post(f"/api/versiones/{id_version}/recalculos", json=cuerpo_recalculo(manzanas, **cambios))


def orientacion(alternativa: dict, giro: float) -> float:
    return round((alternativa["version"]["estrategia"]["orientacion_grados"] + giro) % 180, 2)


def test_el_recalculo_crea_la_version_2_y_la_de_origen_queda_intacta(cliente, generada, db):
    v1 = generada["version"]["id_version"]
    antes = huella(db, v1)

    respuesta = recalcular(cliente, v1, ["M2", "M3"], orientacion_grados=orientacion(generada, 90))

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo == cliente.get(respuesta.headers["Location"]).json()
    assert cuerpo["id_alternativa"] == generada["id_alternativa"] and cuerpo["codigo"] == "A"
    version = cuerpo["version"]
    assert version["numero"] == 2 and version["id_version_origen"] == v1
    assert [(v["numero"], v["id_version_origen"]) for v in cuerpo["versiones"]] == [(1, None), (2, v1)]
    # La alternativa pasa a tener la versión 2 como vigente.
    assert cliente.get(f"/api/alternativas/{generada['id_alternativa']}").json()["version"]["numero"] == 2
    db.expire_all()
    assert huella(db, v1) == antes

    fijacion_ = version["fijacion"]
    assert fijacion_["manzanas"] == ["M2", "M3"] and fijacion_["numero_origen"] == 1
    assert fijacion_["cantidad_lotes"] > 0
    # D60: los anclajes son los de la vista previa; a lo sumo se unen todos, y los empalmes van aparte.
    sector = cliente.post(f"/api/versiones/{v1}/sector", json={"manzanas": ["M2", "M3"]}).json()
    assert fijacion_["cantidad_anclajes"] == sector["cantidad_anclajes"] > 0
    assert 0 < fijacion_["cantidad_anclajes_unidos"] <= fijacion_["cantidad_anclajes"]
    assert fijacion_["cantidad_empalmes"] >= 0
    assert version["tipo"] == "recalculada"
    assert fijacion_["sector"]["type"] == "MultiPolygon" and fijacion_["superficie_m2"] > 0
    filas = {f["indicador"]: f for f in version["diferencias_con_origen"]}
    for campo, valor in generada["version"]["indicadores"].items():
        if campo in filas:
            assert filas[campo]["origen"] == valor and filas[campo]["nueva"] == version["indicadores"][campo]
    fijadas = [f["properties"]["designacion"] for f in version["capas"]["manzanas"]["features"] if f["properties"]["fijada"]]
    assert fijadas == ["M2", "M3"]
    assert any(f["properties"]["fijado"] for f in version["capas"]["ejes"]["features"])


def test_lo_fijado_se_guarda_identico(cliente, generada, db):
    v1 = generada["version"]["id_version"]
    v2 = recalcular(cliente, v1, ["M2", "M3"], orientacion_grados=orientacion(generada, 45)).json()["version"]["id_version"]

    def geometrias(tabla: str, id_version: int, solo_fijadas: bool) -> dict:
        condicion = " AND fijada" if solo_fijadas else ""
        filas = db.execute(
            text(f"SELECT designacion, ST_AsBinary(geom) FROM {tabla} WHERE id_version = :v{condicion}"),
            {"v": id_version},
        )
        return {d: bytes(g) for d, g in filas}

    for tabla in ("celda", "manzana"):
        nuevas = geometrias(tabla, v2, True)
        de_origen = geometrias(tabla, v1, False)
        assert nuevas and all(nuevas[d] == de_origen[d] for d in nuevas), tabla
    # Un tramo fijado entero conserva el eje de origen al bit; uno partido en un empalme (D56) da
    # pedazos sobre el eje de origen que suman su longitud.
    version = db.get(VersionAlternativa, v2)
    origen = db.get(VersionAlternativa, v1)
    fijos = [t for t in version.tramos if t.fijado]
    pedazos: dict[int, list] = {}
    for tramo in fijos:
        eje = to_shape(tramo.eje)
        (de_origen,) = [t for t in origen.tramos if to_shape(t.eje).buffer(1e-7).covers(eje)]
        pedazos.setdefault(de_origen.id_tramo, []).append(tramo)
    enteros = 0
    for id_tramo, partes in pedazos.items():
        de_origen = next(t for t in origen.tramos if t.id_tramo == id_tramo)
        if len(partes) == 1:
            enteros += bytes(partes[0].eje.data) == bytes(de_origen.eje.data)
            continue
        assert float(sum(p.longitud_m for p in partes)) == pytest.approx(float(de_origen.longitud_m), abs=0.01 * len(partes))
    assert fijos and enteros > 0
    assert version.geom_fijada is not None


def test_lo_guardado_es_lo_que_da_el_motor_corrido_aparte(cliente, generada, db):
    v1 = generada["version"]["id_version"]
    giro = orientacion(generada, 90)
    v2 = recalcular(cliente, v1, ["M6", "M7"], orientacion_grados=giro).json()["version"]["id_version"]

    origen = db.get(VersionAlternativa, v1)
    proyecto = origen.alternativa.proyecto
    motor = mt.MotorGeneracion()
    fijados = fijacion.armar_fijados(motor, origen, ["M6", "M7"])
    estrategia = mt.Estrategia(mt.PatronRed.GRILLA, giro, generada["version"]["estrategia"]["semilla"])
    resultado = motor.recalcular(armar_solicitud(proyecto, proyecto.parametros_vigentes(), estrategia), fijados)

    guardada = db.get(VersionAlternativa, v2)
    assert [m.designacion for m in guardada.manzanas] == list(resultado.designaciones)
    assert sorted(c.designacion for c in guardada.celdas) == sorted(c.designacion for c in resultado.celdas)
    assert len(guardada.tramos) == len(resultado.red.tramos())
    assert guardada.cantidad_celdas == resultado.indicadores.cantidad_celdas
    for columna, valor in (
        ("superficie_aprovechable_m2", resultado.indicadores.superficie_aprovechable),
        ("longitud_red_m", resultado.indicadores.longitud_red),
        ("superficie_verde_computable_m2", resultado.indicadores.superficie_verde_computable),
    ):
        assert float(getattr(guardada, columna)) == pytest.approx(valor, abs=MEDIO_CENTESIMO), columna


def test_3a_si_lo_fijado_abarca_todo_el_terreno_da_422_y_no_guarda_nada(cliente, generada, db):
    v1 = generada["version"]["id_version"]
    todas = [f["properties"]["designacion"] for f in generada["version"]["capas"]["manzanas"]["features"]]
    for respuesta in (
        recalcular(cliente, v1, todas),
        cliente.post(f"/api/versiones/{v1}/sector", json={"manzanas": todas}),
    ):
        assert respuesta.status_code == 422
        assert "abarca todo el terreno" in respuesta.json()["causa"] and respuesta.json()["sugerencia"]
    assert len(cliente.get(f"/api/alternativas/{generada['id_alternativa']}").json()["versiones"]) == 1


def test_5a_si_lo_nuevo_no_se_conecta_da_422_con_la_geometria(cliente, generada, db, monkeypatch):
    """El motor levanta el error de conectividad (como en D50, con una red armada a mano): la API lo
    devuelve como 422 con la geometría en 4326, y no guarda nada."""
    v1 = generada["version"]["id_version"]
    origen = db.get(VersionAlternativa, v1)
    proyecto = origen.alternativa.proyecto
    centro = mt.coordenadas.a_metros(to_shape(proyecto.terreno.geom), proyecto.srid_calculo).centroid

    def sin_conexion(self, solicitud, fijados):
        raise mt.ErrorConectividad(
            "El sector recalculado no se puede conectar con el fijado: la red quedó partida en 2 partes.",
            "Probá otra orientación o fijá otras manzanas.",
            MultiLineString([[(centro.x, centro.y), (centro.x + 50, centro.y)]]),
        )

    monkeypatch.setattr(mt.MotorGeneracion, "recalcular", sin_conexion)
    respuesta = recalcular(cliente, v1, ["M2"])
    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert "no se puede conectar" in cuerpo["causa"] and cuerpo["geometria"]["type"] == "MultiLineString"
    assert len(cliente.get(f"/api/alternativas/{generada['id_alternativa']}").json()["versiones"]) == 1


def test_sin_manzanas_o_con_una_que_no_existe_da_422_en_el_campo(cliente, generada):
    v1 = generada["version"]["id_version"]
    for manzanas, texto in (([], "al menos una"), (["M2", "M99"], "M99")):
        respuesta = recalcular(cliente, v1, manzanas)
        assert respuesta.status_code == 422
        (problema,) = respuesta.json()["problemas"]
        assert problema["campo"] == "manzanas" and texto in problema["mensaje"]
    assert cliente.post("/api/versiones/999999/recalculos", json=cuerpo_recalculo(["M2"])).status_code == 404


def test_con_otras_jerarquias_vigentes_da_422(cliente, generada):
    """Las calles fijadas tienen el ancho de las jerarquías de origen: si cambiaron, no se mezclan."""
    v1 = generada["version"]["id_version"]
    valores = cliente.get("/api/parametros/referencia").json()["valores"]
    valores["jerarquias"][-1]["ancho_vereda_m"] = 3.5
    assert cliente.post(f"/api/proyectos/{generada['id_proyecto']}/parametros", json=valores).status_code == 201
    respuesta = recalcular(cliente, v1, ["M2"])
    assert respuesta.status_code == 422
    assert [p["campo"] for p in respuesta.json()["problemas"]] == ["jerarquias"]


def test_la_vista_previa_resalta_lo_fijado_sin_guardar_nada(cliente, generada):
    v1 = generada["version"]["id_version"]
    respuesta = cliente.post(f"/api/versiones/{v1}/sector", json={"manzanas": ["M2", "M3"]})
    assert respuesta.status_code == 200, respuesta.text
    sector = respuesta.json()
    assert sector["manzanas"] == ["M2", "M3"]
    assert sector["cantidad_lotes"] > 0 and sector["cantidad_celdas_utiles"] <= sector["cantidad_lotes"]
    assert 0 < sector["porcentaje_disponible"] < 100 and sector["cantidad_anclajes"] > 0
    assert sector["sector"]["type"] == "MultiPolygon" and sector["anclajes"]["type"] == "MultiPoint"

    # Un contorno que encierra M2 y M3 enteras elige esas dos, y nada más.
    manzanas = {f["properties"]["designacion"]: f for f in generada["version"]["capas"]["manzanas"]["features"]}
    from shapely.geometry import shape

    contorno = box(*shape(manzanas["M2"]["geometry"]).union(shape(manzanas["M3"]["geometry"])).buffer(1e-5).bounds)
    por_contorno = cliente.post(
        f"/api/versiones/{v1}/sector",
        json={"contorno": {"type": "Polygon", "coordinates": [list(map(list, contorno.exterior.coords))]}},
    ).json()
    assert {"M2", "M3"} <= set(por_contorno["manzanas"])
    assert all(m in manzanas for m in por_contorno["manzanas"])

    vacia = cliente.post(f"/api/versiones/{v1}/sector", json={})
    assert vacia.status_code == 422 and vacia.json()["problemas"][0]["campo"] == "manzanas"
    assert len(cliente.get(f"/api/alternativas/{generada['id_alternativa']}").json()["versiones"]) == 1


def test_la_estrategia_sugerida_para_recalcular_es_la_de_la_version_de_origen(cliente, generada):
    """D60: al recalcular se propone la estrategia de la versión, no una nueva: con otra orientación
    la grilla nueva se cruza con la fijada. También después de un recálculo con otra orientación."""
    v1 = generada["version"]["id_version"]
    sector = cliente.post(f"/api/versiones/{v1}/sector", json={"manzanas": ["M2", "M3"]}).json()
    assert sector["estrategia_sugerida"] == generada["version"]["estrategia"]
    giro = orientacion(generada, 90)
    v2 = recalcular(cliente, v1, ["M2", "M3"], orientacion_grados=giro).json()["version"]
    sector2 = cliente.post(f"/api/versiones/{v2['id_version']}/sector", json={"manzanas": ["M2"]}).json()
    assert sector2["estrategia_sugerida"] == v2["estrategia"]
    assert sector2["estrategia_sugerida"]["orientacion_grados"] == giro


def test_una_version_se_lee_y_dos_versiones_se_comparan(cliente, generada):
    v1 = generada["version"]["id_version"]
    v2 = recalcular(cliente, v1, ["M2", "M3"]).json()["version"]["id_version"]

    leida = cliente.get(f"/api/versiones/{v1}").json()
    assert leida["version"]["numero"] == 1 and [v["numero"] for v in leida["versiones"]] == [1, 2]
    assert cliente.get("/api/versiones/999999").status_code == 404

    id_proyecto = generada["id_proyecto"]
    # El proyecto lista las versiones de cada alternativa: el portal resuelve «A.2» con ellas.
    (resumen,) = cliente.get(f"/api/proyectos/{id_proyecto}").json()["alternativas"]
    assert [(v["id_version"], v["id_version_origen"]) for v in resumen["versiones"]] == [(v1, None), (v2, v1)]
    respuesta = cliente.get(f"/api/proyectos/{id_proyecto}/comparacion?versiones={v1}&versiones={v2}")
    assert respuesta.status_code == 200, respuesta.text
    comparacion = respuesta.json()
    assert [(a["codigo"], a["numero"]) for a in comparacion["alternativas"]] == [("A", 1), ("A", 2)]
    # Entre versiones no va la fila de las bloqueantes: es de la alternativa, no de la versión (D84).
    assert "observaciones_bloqueantes_abiertas" not in {f["indicador"] for f in comparacion["indicadores"]}
    lotes = next(f for f in comparacion["indicadores"] if f["indicador"] == "cantidad_celdas")
    assert lotes["valores"] == [
        generada["version"]["indicadores"]["cantidad_celdas"],
        cliente.get(f"/api/versiones/{v2}").json()["version"]["indicadores"]["cantidad_celdas"],
    ]
    for consulta in (f"versiones={v1}&versiones={v1}", f"versiones={v1}&alternativas={generada['id_alternativa']}"):
        assert cliente.get(f"/api/proyectos/{id_proyecto}/comparacion?{consulta}").status_code == 422


def test_el_verde_computable_se_guarda_aparte_del_total(cliente, crear_proyecto, generar):
    """D55: en la L las puntas son verde pero no computan: el verde total pasa al computable."""
    indicadores = generar(crear_proyecto(caso="l")["id_proyecto"])["version"]["indicadores"]
    assert indicadores["superficie_verde_computable_m2"] < indicadores["superficie_espacio_verde_m2"]
    assert indicadores["porcentaje_cesion"] >= 10 - 1e-6
    assert indicadores["superficie_media_celda_m2"] == pytest.approx(
        indicadores["superficie_aprovechable_m2"] / indicadores["cantidad_celdas"], abs=MEDIO_CENTESIMO
    )
    assert math.isfinite(indicadores["longitud_red_m"])
