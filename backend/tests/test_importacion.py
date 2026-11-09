"""La importación de los vértices del terreno desde una planilla (CU04, paso 3; figura 15; D80).

- En POSGAR 2007 (`este;norte`, como las planillas de mensura del Anexo 1.2) o en latitud y longitud.
- La faja sale del este y tiene que coincidir con el sistema de cálculo elegido.
- El separador es «;», «,» o el tabulador; con «;» o el tabulador, la coma decimal. `#` comenta una línea
  y el cierre repetido es opcional.
- 422 con los problemas por línea, en el campo `contenido`.
"""

import pytest
from motor_trazados import coordenadas

from tests.datos_referencia import terreno_y_accesos_4326

FAJA_4 = 5346


def importar(cliente, contenido: str, **cambios):
    return cliente.post("/api/terrenos/importacion", json={"contenido": contenido} | cambios)


def planilla_posgar(cerrada: bool = True) -> str:
    """El terreno de referencia como una planilla de mensura: «vertice;este;norte», con coma decimal."""
    terreno, _ = terreno_y_accesos_4326()
    metros = list(coordenadas.a_metros(terreno, FAJA_4).exterior.coords)
    if not cerrada:
        metros = metros[:-1]
    filas = [f"V{k + 1};{x:.3f};{y:.3f}".replace(".", ",") for k, (x, y) in enumerate(metros)]
    return "\n".join(["# Planilla de mensura (ficticia)", "Vértice;Este;Norte", *filas])


def mismo_poligono(importado: dict, terreno) -> None:
    leidas = importado["terreno"]["coordinates"][0]
    originales = list(terreno.exterior.coords)
    assert len(leidas) == len(originales)
    for (x, y), (xo, yo) in zip(leidas, originales, strict=True):
        # Milímetros en la planilla: menos de 1e-7 grados.
        assert (x, y) == (pytest.approx(xo, abs=1e-7), pytest.approx(yo, abs=1e-7))


def test_posgar_con_coma_decimal(cliente):
    respuesta = importar(cliente, planilla_posgar())
    assert respuesta.status_code == 200, respuesta.text
    importado = respuesta.json()
    assert (importado["formato"], importado["srid_calculo"], importado["sistema"]) == (
        "posgar",
        FAJA_4,
        "POSGAR 2007 / Argentina 4",
    )
    terreno, _ = terreno_y_accesos_4326()
    assert importado["cantidad_vertices"] == len(terreno.exterior.coords) - 1
    mismo_poligono(importado, terreno)
    # Sin el cierre repetido, el mismo polígono; con la faja elegida, también.
    sin_cierre = importar(cliente, planilla_posgar(cerrada=False), srid_calculo=FAJA_4)
    assert sin_cierre.status_code == 200, sin_cierre.text
    assert sin_cierre.json()["terreno"] == importado["terreno"]


def test_latitud_y_longitud_con_coma_como_separador(cliente):
    terreno, _ = terreno_y_accesos_4326()
    filas = [f"{y:.10f},{x:.10f}" for x, y in terreno.exterior.coords]
    respuesta = importar(cliente, "\n".join(["latitud,longitud", *filas]))
    assert respuesta.status_code == 200, respuesta.text
    importado = respuesta.json()
    assert (importado["formato"], importado["srid_calculo"]) == ("geograficas", FAJA_4)
    mismo_poligono(importado, terreno)


def test_la_faja_tiene_que_ser_la_del_sistema_elegido(cliente):
    respuesta = importar(cliente, planilla_posgar(), srid_calculo=5347)
    assert respuesta.status_code == 422
    problema = respuesta.json()["problemas"][0]
    assert problema["campo"] == "contenido"
    assert "faja 4" in problema["mensaje"] and "EPSG:5347" in problema["mensaje"]


def test_los_problemas_dicen_la_linea(cliente):
    lineas = planilla_posgar().splitlines()
    # La línea 4 (el segundo vértice) con un separador de miles; la 5 con un valor de menos.
    lineas[3] = "V2;4.436.512,30;6.521.000,00"
    lineas[4] = "V3;4436600,00"
    respuesta = importar(cliente, "\n".join(lineas))
    assert respuesta.status_code == 422
    error = respuesta.json()
    assert error["causa"] == "La planilla de vértices no se pudo importar."
    mensajes = [p["mensaje"] for p in error["problemas"]]
    assert mensajes[0].startswith("Línea 4: «4.436.512,30» no es un número")
    assert mensajes[1] == "Línea 5: tiene 2 valores y la cabecera, 3 columnas."
    assert {p["campo"] for p in error["problemas"]} == {"contenido"}


@pytest.mark.parametrize(
    ("contenido", "empieza"),
    [
        ("# solo un comentario\n\n", "La planilla no tiene datos"),
        ("x;y\n1;2\n", "Línea 1: la cabecera tiene las columnas «x», «y»"),
        ("este norte\n", "Línea 1: la primera línea es la cabecera"),
        ("este;norte\n4500000;6500000\n4500100;6500000\n", "Hay 2 vértice(s)"),
        ("este;norte\n500000;6500000\n500100;6500000\n500100;6500100\n", "Línea 2: el este 500.000,00 no es de ninguna faja"),
        ("latitud;longitud\n-131;-64\n-31;-64\n-31;-64,1\n", "Línea 2: la latitud -131,00"),
    ],
)
def test_lo_que_no_se_puede_leer(cliente, contenido, empieza):
    respuesta = importar(cliente, contenido)
    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["problemas"][0]["mensaje"].startswith(empieza)


def test_un_poligono_que_se_cruza_lo_rechaza_la_regla_del_motor(cliente):
    filas = ["4500000;6500000", "4500100;6500100", "4500100;6500000", "4500000;6500100"]
    respuesta = importar(cliente, "\n".join(["este;norte", *filas]))
    assert respuesta.status_code == 422
    assert "no es válido" in respuesta.json()["problemas"][0]["mensaje"]
