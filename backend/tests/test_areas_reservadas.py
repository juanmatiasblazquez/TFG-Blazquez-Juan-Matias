"""Áreas reservadas por la API (CU04, pasos 5 y 6; CU06, paso 4; D59) y volver a una versión (D60).

- El alta registra las áreas del terreno (R1, R2…) y las sirve con su superficie.
- Cada versión guarda la copia de las áreas con las que se generó: si el proyecto las cambia
  (`PUT /proyectos/{id}/areas-reservadas`), una versión anterior no cambia, y su recálculo usa las
  suyas; una generación nueva usa las nuevas.
- Las validaciones dan 422 con causa, sugerencia y el campo, en el alta y en el PUT, y no guardan
  nada.
- Volver a una versión anterior crea la versión n + 1, que la copia; la elegida no cambia.
"""

import pytest
from shapely import box
from shapely.geometry import shape
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.datos_referencia import cuerpo_area, cuerpo_proyecto, cuerpo_recalculo, en_4326_como_los_casos
from tests.test_inmutabilidad import huella


def areas(cuerpo: dict) -> list[dict]:
    return [f["properties"] for f in cuerpo["features"]]


@pytest.fixture
def con_area(crear_proyecto) -> dict:
    """El rectangular con el área del medio (el caso `reservada_centro`)."""
    return crear_proyecto(caso="reservada_centro")


def test_el_alta_registra_las_areas_y_las_sirve_con_su_designacion(cliente, con_area):
    (r1,) = areas(con_area["areas_reservadas"])
    assert r1["designacion"] == "R1" and r1["denominacion"] == "Reserva para equipamiento comunitario"
    assert r1["clase"] is None and r1["superficie_m2"] == pytest.approx(6000, abs=0.01)
    assert cliente.get(f"/api/proyectos/{con_area['id_proyecto']}").json()["areas_reservadas"] == con_area["areas_reservadas"]


def test_la_version_guarda_la_copia_de_las_areas_y_su_superficie(cliente, con_area, generar):
    version = generar(con_area["id_proyecto"])["version"]
    (copia,) = version["capas"]["areas_reservadas"]["features"]
    (del_proyecto,) = con_area["areas_reservadas"]["features"]
    assert copia["geometry"] == del_proyecto["geometry"]
    assert copia["properties"]["designacion"] == "R1"
    assert copia["properties"]["denominacion"] == del_proyecto["properties"]["denominacion"]
    i = version["indicadores"]
    assert i["superficie_reservada_m2"] == pytest.approx(6000, abs=0.01)
    assert version["cumple_restricciones"] is True
    # Ninguna celda pisa el área: es una pieza aparte de la partición.
    area = shape(copia["geometry"])
    assert all(shape(c["geometry"]).intersection(area).area < 1e-12 for c in version["capas"]["celdas"]["features"])


def test_cambiar_las_areas_no_altera_una_version_anterior_y_la_nueva_usa_las_nuevas(cliente, con_area, generar, db):
    id_proyecto = con_area["id_proyecto"]
    a = generar(id_proyecto)
    v1 = a["version"]["id_version"]
    antes = huella(db, v1)
    db.rollback()

    # Otra área, al norte del medio.
    otra = en_4326_como_los_casos(box(-60, 9, 60, 59))
    respuesta = cliente.put(
        f"/api/proyectos/{id_proyecto}/areas-reservadas",
        json={"areas_reservadas": [cuerpo_area(otra, "Reserva de prueba", clase="municipal", destino="Escuela")]},
    )
    assert respuesta.status_code == 200, respuesta.text
    (r1,) = areas(respuesta.json()["areas_reservadas"])
    assert (r1["designacion"], r1["clase"], r1["destino"]) == ("R1", "municipal", "Escuela")

    db.expire_all()
    assert huella(db, v1) == antes
    assert cliente.get(f"/api/versiones/{v1}").json() == cliente.get(f"/api/alternativas/{a['id_alternativa']}").json()
    vieja = cliente.get(f"/api/versiones/{v1}").json()["version"]
    assert vieja["capas"]["areas_reservadas"] == a["version"]["capas"]["areas_reservadas"]

    b = generar(id_proyecto)["version"]
    (nueva,) = b["capas"]["areas_reservadas"]["features"]
    assert nueva["properties"]["denominacion"] == "Reserva de prueba"
    assert shape(nueva["geometry"]).centroid.distance(shape(vieja["capas"]["areas_reservadas"]["features"][0]["geometry"]).centroid) > 1e-4

    # El recálculo de la v1 usa las áreas de la v1, no las del proyecto.
    v2 = cliente.post(f"/api/versiones/{v1}/recalculos", json=cuerpo_recalculo(["M1"])).json()["version"]
    assert v2["capas"]["areas_reservadas"] == vieja["capas"]["areas_reservadas"]

    # Sin áreas: lista vacía.
    sin = cliente.put(f"/api/proyectos/{id_proyecto}/areas-reservadas", json={"areas_reservadas": []})
    assert sin.status_code == 200 and sin.json()["areas_reservadas"]["features"] == []


@pytest.mark.parametrize(
    ("areas_locales", "campo", "texto"),
    [
        ([box(200, 0, 280, 60)], "areas_reservadas[0]", "sale del terreno"),
        ([box(-60, -50, 20, 0), box(0, -50, 60, 0)], "areas_reservadas[1]", "se superponen"),
        ([box(-240, -135, 240, 135)], "areas_reservadas", "cubren todo el terreno"),
        ([box(-100, -135, 0, -105)], "accesos[0]", "sobre el borde del área R1"),
    ],
    ids=["fuera", "superpuestas", "todo", "acceso"],
)
def test_las_validaciones_dan_422_con_el_campo_en_el_alta_y_en_el_put(
    cliente, crear_proyecto, nuevo_codigo, id_cliente, areas_locales, campo, texto
):
    """CU04, curso 6.a, y las reglas del motor (`validar_reservadas`): nada se guarda. Las áreas se
    dibujan en las coordenadas del rectangular (480 × 270 m; A1 en el sur, en x = -60)."""
    pedidas = [cuerpo_area(en_4326_como_los_casos(a), f"Área {k}") for k, a in enumerate(areas_locales, 1)]
    respuesta = cliente.post("/api/proyectos", json=cuerpo_proyecto(nuevo_codigo(), id_cliente, areas_reservadas=pedidas))
    assert respuesta.status_code == 422, respuesta.text
    error = respuesta.json()
    assert error["causa"] and error["sugerencia"]
    assert any(p["campo"] == campo and texto in p["mensaje"] for p in error["problemas"]), error["problemas"]

    proyecto = crear_proyecto()
    put = cliente.put(f"/api/proyectos/{proyecto['id_proyecto']}/areas-reservadas", json={"areas_reservadas": pedidas})
    assert put.status_code == 422
    assert any(p["campo"] == campo for p in put.json()["problemas"])
    assert cliente.get(f"/api/proyectos/{proyecto['id_proyecto']}").json()["areas_reservadas"]["features"] == []


def test_un_area_sin_denominacion_da_422_por_el_schema(cliente, nuevo_codigo, id_cliente):
    area = cuerpo_area(en_4326_como_los_casos(box(-60, -51, 60, -1)), "")
    respuesta = cliente.post("/api/proyectos", json=cuerpo_proyecto(nuevo_codigo(), id_cliente, areas_reservadas=[area]))
    assert respuesta.status_code == 422
    assert any(p["campo"].startswith("areas_reservadas") for p in respuesta.json()["problemas"])


def test_la_copia_de_las_areas_es_inmutable(con_area, generar, db):
    id_version = generar(con_area["id_proyecto"])["version"]["id_version"]
    for sentencia in (
        "UPDATE area_reservada_version SET denominacion = 'x' WHERE id_version = :v",
        "DELETE FROM area_reservada_version WHERE id_version = :v",
    ):
        with pytest.raises(DBAPIError, match="inmutables"):
            db.execute(text(sentencia), {"v": id_version})
        db.rollback()


# --- Volver a una versión anterior (D60) -----------------------------------------------------------


def test_volver_a_una_version_crea_otra_que_la_copia_y_no_toca_la_elegida(cliente, con_area, generar, db):
    a = generar(con_area["id_proyecto"])
    v1 = a["version"]["id_version"]
    v2 = cliente.post(f"/api/versiones/{v1}/recalculos", json=cuerpo_recalculo(["M1"], orientacion_grados=110)).json()
    antes = huella(db, v1)
    db.rollback()

    respuesta = cliente.post(f"/api/versiones/{v1}/copias")
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo == cliente.get(respuesta.headers["Location"]).json()
    v3 = cuerpo["version"]
    assert (v3["numero"], v3["id_version_origen"], v3["tipo"]) == (3, v1, "copia")
    assert v3["fijacion"] is None and v3["diferencias_con_origen"] is None
    assert [(v["numero"], v["id_version_origen"], v["tipo"]) for v in cuerpo["versiones"]] == [
        (1, None, "generada"),
        (2, v1, "recalculada"),
        (3, v1, "copia"),
    ]
    origen = a["version"]
    for capa in ("ejes", "calles", "manzanas", "celdas", "incumplimientos", "areas_reservadas"):
        sin_ids = lambda fc: [  # noqa: E731
            (f["geometry"], {k: v for k, v in f["properties"].items() if not k.startswith("id_")}) for f in fc["features"]
        ]
        assert sin_ids(v3["capas"][capa]) == sin_ids(origen["capas"][capa]), capa
    assert v3["indicadores"] == origen["indicadores"]
    assert (v3["estrategia"], v3["version_parametros"], v3["version_motor"]) == (
        origen["estrategia"],
        origen["version_parametros"],
        origen["version_motor"],
    )
    db.expire_all()
    assert huella(db, v1) == antes
    # La vigente es la copia (la de mayor número), y copiar la vigente no tiene sentido.
    assert cliente.get(f"/api/alternativas/{a['id_alternativa']}").json()["version"]["numero"] == 3
    vigente = cliente.post(f"/api/versiones/{v3['id_version']}/copias")
    assert vigente.status_code == 422 and "ya es la vigente" in vigente.json()["causa"]
    assert cliente.post("/api/versiones/999999/copias").status_code == 404
    # La v2 se puede recuperar igual: volver a ella crea la v4.
    v4 = cliente.post(f"/api/versiones/{v2['version']['id_version']}/copias").json()["version"]
    assert (v4["numero"], v4["id_version_origen"]) == (4, v2["version"]["id_version"])
    assert v4["indicadores"] == v2["version"]["indicadores"]
