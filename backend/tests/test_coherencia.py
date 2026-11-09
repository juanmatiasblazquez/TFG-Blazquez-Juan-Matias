"""La validación en vivo de los parámetros (figura 16, «Validación de coherencia»; D78).

- Las reglas las decide el motor (`coherencia_de_loteo`): las cuatro de la p. 49 primero, cumplidas o no,
  con su detalle en español.
- Los problemas son los mismos, con los mismos campos, que daría guardar los parámetros (CU05, 3.a).
- La calzada de cada jerarquía alcanza la mínima del art. 12 (B3 reducido).
- No guarda nada y no necesita un proyecto: sirve también en el paso 3 del alta.
"""

import copy

import pytest

# Las cuatro de la p. 49, en su orden, y después las del motor.
CLAVES = [
    "superficie",
    "frente_objetivo",
    "cesiones",
    "lote_minimo",
    "ancho_util",
    "tope_union",
    "calzada_calle",
    "avenida_calle",
    "lado_menor",
    "sin_pasaje",
    "lado_mayor",
    "calzada_jerarquias",
]


@pytest.fixture
def referencia(cliente) -> dict:
    return cliente.get("/api/parametros/referencia").json()["valores"]


def validar(cliente, valores: dict):
    respuesta = cliente.post("/api/parametros/validacion", json=valores)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def test_los_valores_de_referencia_cumplen_todas(cliente, referencia):
    coherencia = validar(cliente, referencia)
    assert [r["clave"] for r in coherencia["reglas"]] == CLAVES
    assert all(r["cumple"] for r in coherencia["reglas"])
    assert coherencia["problemas"] == []
    reglas = {r["clave"]: r for r in coherencia["reglas"]}
    assert reglas["superficie"]["descripcion"] == "Superficie mínima ≤ superficie máxima"
    # El detalle, con los valores en español.
    loteo = referencia["loteo"]
    minima = f"{loteo['superficie_minima_m2']:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    assert reglas["superficie"]["detalle"].startswith(f"{minima} m² ≤ ")


def test_una_incoherencia_da_los_mismos_campos_que_guardar(cliente, referencia, crear_proyecto):
    valores = copy.deepcopy(referencia)
    valores["loteo"]["superficie_minima_m2"] = valores["loteo"]["superficie_maxima_m2"] + 100
    coherencia = validar(cliente, valores)
    assert [r["clave"] for r in coherencia["reglas"] if not r["cumple"]] == ["superficie"]
    assert [p["campo"] for p in coherencia["problemas"]] == ["loteo.superficie_minima_m2"]

    id_proyecto = crear_proyecto()["id_proyecto"]
    guardar = cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores)
    assert guardar.status_code == 422
    assert guardar.json()["problemas"] == coherencia["problemas"]


def test_la_cuarta_regla_de_la_p49(cliente, referencia):
    """Frente mínimo × fondo mínimo ≤ superficie máxima (D78): si no, ningún lote cumpliría los tres."""
    valores = copy.deepcopy(referencia)
    valores["loteo"]["fondo_minimo_m"] = valores["loteo"]["superficie_maxima_m2"] / valores["loteo"]["frente_minimo_m"] + 5
    coherencia = validar(cliente, valores)
    assert [r["clave"] for r in coherencia["reglas"] if not r["cumple"]] == ["lote_minimo"]
    assert [p["campo"] for p in coherencia["problemas"]] == ["loteo.fondo_minimo_m"]


def test_la_calzada_de_una_jerarquia_alcanza_la_minima(cliente, referencia):
    """Ley 4146, art. 12 (B3 reducido, D78): el problema va en la calzada de esa jerarquía."""
    valores = copy.deepcopy(referencia)
    valores["jerarquias"][1]["ancho_calzada_m"] = valores["loteo"]["ancho_minimo_calzada_m"] - 1
    coherencia = validar(cliente, valores)
    assert [r["clave"] for r in coherencia["reglas"] if not r["cumple"]] == ["calzada_jerarquias"]
    assert [p["campo"] for p in coherencia["problemas"]] == ["jerarquias[1].ancho_calzada_m"]
    assert "Ley 4146, art. 12" in coherencia["problemas"][0]["mensaje"]


def test_sin_avenidas_la_colectora_no_se_usa_y_sus_reglas_no_van(cliente, referencia):
    """La casilla «Exigir avenidas» desmarcada (D85): con 0 %, el motor usa solo la jerarquía local. La API
    lo dice por jerarquía, para que el portal no muestre la que no se usa, y sin la regla del ancho de
    avenida."""
    assert [j["en_uso"] for j in referencia["jerarquias"]] == [True, True]
    assert validar(cliente, referencia)["jerarquias_en_uso"] == [True, True]
    valores = copy.deepcopy(referencia)
    valores["loteo"]["porcentaje_minimo_avenidas"] = 0
    coherencia = validar(cliente, valores)
    assert coherencia["jerarquias_en_uso"] == [False, True]
    assert [r["clave"] for r in coherencia["reglas"]] == [c for c in CLAVES if c != "avenida_calle"]
    assert coherencia["problemas"] == []
    # La colectora que no se usa no rompe la calzada mínima; con avenidas, sí.
    valores["jerarquias"][0]["ancho_calzada_m"] = valores["loteo"]["ancho_minimo_calzada_m"] - 1
    assert validar(cliente, valores)["problemas"] == []
    valores["loteo"]["porcentaje_minimo_avenidas"] = referencia["loteo"]["porcentaje_minimo_avenidas"]
    assert [p["campo"] for p in validar(cliente, valores)["problemas"]] == ["jerarquias[0].ancho_calzada_m"]


def test_un_valor_que_no_es_valido_no_tiene_reglas_todavia(cliente, referencia):
    valores = copy.deepcopy(referencia)
    valores["loteo"]["frente_minimo_m"] = 0
    coherencia = validar(cliente, valores)
    assert coherencia["reglas"] == []
    assert [p["campo"] for p in coherencia["problemas"]] == ["loteo.frente_minimo_m"]
    # Un valor que no es un número da 422, como al guardar.
    valores["loteo"]["frente_minimo_m"] = "diez"
    assert cliente.post("/api/parametros/validacion", json=valores).status_code == 422


def test_el_ancho_total_es_calzada_y_dos_veredas_y_no_se_guarda(cliente, referencia, crear_proyecto):
    """El ancho total lo calcula el motor (B3 reducido, D78): lo trae la referencia, y si vuelve en un
    pedido (lo leído se manda tal cual) se ignora."""
    for jerarquia in referencia["jerarquias"]:
        assert jerarquia["ancho_total_m"] == pytest.approx(jerarquia["ancho_calzada_m"] + 2 * jerarquia["ancho_vereda_m"])
    # Mientras se edita, el de lo editado (D78).
    editados = copy.deepcopy(referencia)
    editados["jerarquias"][0]["ancho_vereda_m"] += 1
    anchos = validar(cliente, editados)["anchos_totales"]
    assert anchos == [referencia["jerarquias"][0]["ancho_total_m"] + 2, *[j["ancho_total_m"] for j in referencia["jerarquias"][1:]]]
    valores = copy.deepcopy(referencia)
    valores["jerarquias"][0]["ancho_total_m"] = 99
    id_proyecto = crear_proyecto()["id_proyecto"]
    guardado = cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores)
    assert guardado.status_code == 201, guardado.text
    guardadas = [{k: v for k, v in j.items() if k != "id_jerarquia"} for j in guardado.json()["jerarquias"]]
    assert guardadas == referencia["jerarquias"]
