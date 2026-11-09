"""La medición del terreno del alta (figura 15, «Terreno» y «Validación de la geometría»; D79).

- Se mide en el sistema de cálculo, como al registrar: la superficie y el perímetro son los que guarda el
  alta.
- Las reglas son las del motor (`validar_terreno`, `validar_accesos`, `validar_reservadas`), con los
  campos del pedido del alta.
- No guarda nada: lo que está mal va en las reglas, con 200.
"""

import pytest
from shapely import Point, Polygon
from shapely.geometry import mapping

from tests.datos_referencia import areas_4326, cuerpo_proyecto, terreno_y_accesos_4326


def poligono(geometria: Polygon) -> dict:
    return {"type": "Polygon", "coordinates": [[list(p) for p in mapping(geometria)["coordinates"][0]]]}


def punto(geometria: Point) -> dict:
    return {"type": "Point", "coordinates": [geometria.x, geometria.y]}


def medir(cliente, terreno: Polygon, accesos: list[Point], areas: list[Polygon] = (), **cambios) -> dict:
    cuerpo = {
        "terreno": poligono(terreno),
        "accesos": [punto(a) for a in accesos],
        "areas_reservadas": [poligono(a) for a in areas],
    } | cambios
    respuesta = cliente.post("/api/terrenos/medicion", json=cuerpo)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def reglas(medicion: dict) -> dict[str, bool]:
    return {r["clave"]: r["cumple"] for r in medicion["reglas"]}


def test_mide_como_el_alta(cliente, crear_proyecto):
    terreno, accesos = terreno_y_accesos_4326("reservada_centro")
    areas = areas_4326("reservada_centro")
    medicion = medir(cliente, terreno, accesos, areas)
    assert (medicion["srid_calculo"], medicion["sistema"]) == (5346, "POSGAR 2007 / Argentina 4")
    assert reglas(medicion) == {"poligono": True, "accesos": True, "areas": True}
    assert medicion["problemas"] == []

    proyecto = crear_proyecto(caso="reservada_centro")
    assert medicion["superficie_m2"] == proyecto["terreno"]["properties"]["superficie_m2"]
    assert medicion["perimetro_m"] == proyecto["terreno"]["properties"]["perimetro_m"]

    # V1… en el orden del dibujo, y un lado por vértice; el último cierra en V1.
    cantidad = len(terreno.exterior.coords) - 1
    assert [v["designacion"] for v in medicion["vertices"]] == [f"V{k + 1}" for k in range(cantidad)]
    assert medicion["vertices"][0]["posicion"] == list(terreno.exterior.coords[0])
    assert (medicion["lados"][-1]["desde"], medicion["lados"][-1]["hasta"]) == (f"V{cantidad}", "V1")
    assert sum(lado["largo_m"] for lado in medicion["lados"]) == pytest.approx(medicion["perimetro_m"], abs=0.05)
    assert [a["designacion"] for a in medicion["areas"]] == ["R1"]
    assert medicion["areas"][0]["superficie_m2"] > 0


def test_lo_que_esta_mal_va_en_las_reglas_con_el_campo_del_alta(cliente):
    terreno, accesos = terreno_y_accesos_4326()
    # Un acceso en el centro del terreno, lejos del perímetro.
    medicion = medir(cliente, terreno, [accesos[0], terreno.centroid])
    assert reglas(medicion) == {"poligono": True, "accesos": False}
    assert [p["campo"] for p in medicion["problemas"]] == ["accesos[1]"]
    assert medicion["superficie_m2"] is not None

    # Sin accesos todavía: el polígono se mide igual.
    sin_accesos = medir(cliente, terreno, [])
    assert reglas(sin_accesos) == {"poligono": True, "accesos": False}
    assert [p["campo"] for p in sin_accesos["problemas"]] == ["accesos"]

    # Un área que sale del terreno: el campo es el del alta.
    x, y = terreno.exterior.coords[0]
    afuera = Polygon([(x - 0.0005, y - 0.0005), (x + 0.0005, y - 0.0005), (x + 0.0005, y + 0.0005), (x - 0.0005, y + 0.0005)])
    con_area = medir(cliente, terreno, accesos, [afuera])
    assert reglas(con_area)["areas"] is False
    assert [p["campo"] for p in con_area["problemas"]] == ["areas_reservadas[0]"]


def test_un_poligono_que_se_cruza_no_tiene_superficie(cliente):
    terreno, accesos = terreno_y_accesos_4326()
    a, b, c, d = list(terreno.exterior.coords)[:4]
    moño = Polygon([a, c, b, d])
    medicion = medir(cliente, moño, accesos)
    assert reglas(medicion)["poligono"] is False
    assert (medicion["superficie_m2"], medicion["perimetro_m"]) == (None, None)
    assert medicion["problemas"][0]["campo"] == "terreno"
    # Los lados se miden igual: el portal los rotula mientras se corrige.
    assert len(medicion["lados"]) == 4


def test_un_sistema_que_no_sirve_da_422(cliente):
    terreno, accesos = terreno_y_accesos_4326()
    respuesta = cliente.post(
        "/api/terrenos/medicion",
        json={"terreno": poligono(terreno), "accesos": [punto(a) for a in accesos], "srid_calculo": 4326},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["problemas"][0]["campo"] == "srid_calculo"


def test_el_pedido_es_el_del_alta_sin_los_datos_del_proyecto(cliente):
    """La forma de lo dibujado es la del alta: un acceso es un punto, y no hace falta el resto."""
    cuerpo = cuerpo_proyecto("X", 1)
    respuesta = cliente.post("/api/terrenos/medicion", json={"terreno": cuerpo["terreno"], "codigo": "X"})
    assert respuesta.status_code == 422
