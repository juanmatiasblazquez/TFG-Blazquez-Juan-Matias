"""Errores con un solo formato (D32): causa, sugerencia, problemas por campo, en español
(RNF01). El 422 de la generación es el de CU06: con causa y sugerencia, y sin guardar nada."""

import pytest
from shapely import Point, Polygon, box
from sqlalchemy import text

from tests.datos_referencia import cuerpo_generacion, cuerpo_proyecto, en_4326_junto_al_de_referencia


def cantidad_de_versiones(db) -> int:
    return db.scalar(text("SELECT count(*) FROM version_alternativa"))


def problemas(respuesta) -> dict[str, str]:
    return {p["campo"]: p["mensaje"] for p in respuesta.json()["problemas"]}


# --- Generación: lo que el motor no puede hacer ---------------------------------------------


def test_un_terreno_donde_no_entra_un_lote_da_422_con_causa_y_sugerencia_y_no_guarda_nada(
    cliente, crear_proyecto, db
):
    """Una franja de 300 × 30 m con la grilla a lo largo: entra la calle, pero a cada lado
    quedan 9 m de fondo (D40). Es un polígono válido, así que el proyecto se registra."""
    franja = box(-150, -15, 150, 15)
    proyecto = crear_proyecto(
        terreno=en_4326_junto_al_de_referencia(franja), accesos=[en_4326_junto_al_de_referencia(Point(-150, 0))]
    )
    antes = cantidad_de_versiones(db)

    respuesta = cliente.post(
        f"/api/proyectos/{proyecto['id_proyecto']}/alternativas", json=cuerpo_generacion(orientacion_grados=0)
    )

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["causa"].startswith("En el terreno no entra ningún lote que cumpla los mínimos")
    assert "orientación" in cuerpo["sugerencia"]
    assert cantidad_de_versiones(db) == antes
    assert cliente.get(f"/api/proyectos/{proyecto['id_proyecto']}").json()["alternativas"] == []


def test_una_red_que_no_conecta_los_accesos_da_422_con_la_geometria_del_problema(
    cliente, crear_proyecto, db, monkeypatch
):
    """La alternativa de la p. 43: si el motor no logra una red conexa con los accesos, 422 con la
    causa, la sugerencia y la parte de la red aislada en 4326, para marcarla en el mapa, sin
    guardar nada. Con la calle de borde del motor 0.7.0 (D50) los terrenos de prueba ya conectan, así
    que el motor levanta el error a propósito, con la geometría en el sistema de cálculo; la regla
    del motor se prueba en el motor."""
    import motor_trazados as mt
    from motor_trazados import coordenadas
    from shapely import MultiLineString

    from app.models import Proyecto
    from app.services.conversiones import leida

    proyecto = crear_proyecto()
    registro = db.get(Proyecto, proyecto["id_proyecto"])
    centro = coordenadas.a_metros(leida(registro.terreno.geom), registro.srid_calculo).centroid
    aislada = MultiLineString([[(centro.x, centro.y), (centro.x + 50, centro.y)]])

    def sin_red(self, solicitud):
        raise mt.ErrorConectividad("La red quedó partida en 2 partes que no se conectan entre sí.", "Probá otra orientación.", aislada)

    monkeypatch.setattr(mt.MotorGeneracion, "generar", sin_red)
    antes = cantidad_de_versiones(db)

    respuesta = cliente.post(f"/api/proyectos/{proyecto['id_proyecto']}/alternativas", json=cuerpo_generacion())

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert "partida" in cuerpo["causa"]
    assert "orientación" in cuerpo["sugerencia"]
    assert cuerpo["geometria"]["type"] == "MultiLineString"
    longitud, latitud = cuerpo["geometria"]["coordinates"][0][0]
    assert -64.2 < longitud < -64.0 and -31.6 < latitud < -31.4
    assert cantidad_de_versiones(db) == antes


def test_un_patron_que_no_existe_se_rechaza_al_validar(cliente, crear_proyecto):
    proyecto = crear_proyecto()
    respuesta = cliente.post(
        f"/api/proyectos/{proyecto['id_proyecto']}/alternativas", json=cuerpo_generacion(patron_red="radial")
    )
    assert respuesta.status_code == 422
    assert problemas(respuesta) == {"estrategia.patron_red": "Tiene que ser uno de estos valores: 'grilla'."}


@pytest.mark.parametrize(
    ("cambio", "campo", "mensaje"),
    [
        ({"orientacion_grados": 20.125}, "estrategia.orientacion_grados", "Admite hasta 2 decimales."),
        ({"orientacion_grados": 360}, "estrategia.orientacion_grados", "Tiene que ser menor que 360."),
        ({"semilla": -1}, "estrategia.semilla", "Tiene que ser mayor o igual que 0."),
        ({"semilla": 2**31}, "estrategia.semilla", "Tiene que ser menor o igual que 2147483647."),
    ],
)
def test_la_estrategia_respeta_las_columnas_del_er(cliente, crear_proyecto, cambio, campo, mensaje):
    proyecto = crear_proyecto()
    respuesta = cliente.post(f"/api/proyectos/{proyecto['id_proyecto']}/alternativas", json=cuerpo_generacion(**cambio))
    assert respuesta.status_code == 422
    assert problemas(respuesta) == {campo: mensaje}


# --- Alta del proyecto: el terreno y los datos ----------------------------------------------


def test_un_poligono_que_se_cruza_a_si_mismo_da_422_en_el_terreno(cliente, nuevo_codigo, id_cliente):
    mono = Polygon([(-240, -135), (240, 135), (240, -135), (-240, 135)])
    acceso = en_4326_junto_al_de_referencia(Point(240, 0))
    cuerpo = cuerpo_proyecto(nuevo_codigo(), id_cliente, terreno=en_4326_junto_al_de_referencia(mono), accesos=[acceso])
    respuesta = cliente.post("/api/proyectos", json=cuerpo)
    assert respuesta.status_code == 422
    assert respuesta.json()["causa"] == "El terreno no es válido."
    assert "se cruza a sí mismo" in problemas(respuesta)["terreno"]


def test_un_acceso_fuera_del_perimetro_da_422_en_ese_acceso(cliente, nuevo_codigo, id_cliente):
    adentro = en_4326_junto_al_de_referencia(Point(0, 0))
    cuerpo = cuerpo_proyecto(nuevo_codigo(), id_cliente)
    cuerpo["accesos"][1]["ubicacion"]["coordinates"] = [adentro.x, adentro.y]
    respuesta = cliente.post("/api/proyectos", json=cuerpo)
    assert respuesta.status_code == 422
    assert "del perímetro" in problemas(respuesta)["accesos[1]"]


@pytest.mark.parametrize(
    ("srid", "mensaje"),
    [(4326, "no es un sistema proyectado en metros"), (999999, "no es un sistema de coordenadas conocido")],
)
def test_un_sistema_de_calculo_que_no_sirve_da_422(cliente, nuevo_codigo, id_cliente, srid, mensaje):
    respuesta = cliente.post("/api/proyectos", json=cuerpo_proyecto(nuevo_codigo(), id_cliente, srid_calculo=srid))
    assert respuesta.status_code == 422
    assert mensaje in problemas(respuesta)["srid_calculo"]


def test_un_codigo_repetido_da_409(cliente, nuevo_codigo, id_cliente):
    codigo = nuevo_codigo()
    assert cliente.post("/api/proyectos", json=cuerpo_proyecto(codigo, id_cliente)).status_code == 201
    respuesta = cliente.post("/api/proyectos", json=cuerpo_proyecto(codigo, id_cliente))
    assert respuesta.status_code == 409
    assert respuesta.json()["causa"] == f"Ya existe un proyecto con el código «{codigo}»."
    assert problemas(respuesta) == {"codigo": "Ya está en uso."}


def test_la_validacion_de_entrada_responde_en_espanol_y_por_campo(cliente, nuevo_codigo, id_cliente):
    cuerpo = cuerpo_proyecto(nuevo_codigo(), id_cliente, tipo="estacionamiento")
    del cuerpo["nombre"]
    cuerpo["terreno"]["coordinates"][0].pop()  # el anillo queda abierto
    respuesta = cliente.post("/api/proyectos", json=cuerpo)
    assert respuesta.status_code == 422
    assert respuesta.json()["causa"] == "Los datos enviados no son válidos."
    encontrados = problemas(respuesta)
    assert encontrados["nombre"] == "Falta este dato."
    assert "playas de estacionamiento todavía no está implementada" in encontrados["tipo"]
    assert encontrados["terreno.coordinates"].startswith("Cada anillo tiene que cerrarse")


def test_un_cuerpo_que_no_es_json_tambien_responde_en_espanol(cliente):
    respuesta = cliente.post("/api/proyectos", content=b"{no es json", headers={"Content-Type": "application/json"})
    assert respuesta.status_code == 422
    assert list(problemas(respuesta).values()) == ["El cuerpo no es un JSON válido."]


# --- Lo que no existe ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("metodo", "ruta", "causa"),
    [
        ("get", "/api/proyectos/999999", "No existe el proyecto 999999."),
        ("post", "/api/proyectos/999999/alternativas", "No existe el proyecto 999999."),
        ("get", "/api/alternativas/999999", "No existe la alternativa 999999."),
    ],
)
def test_lo_que_no_existe_da_404(cliente, metodo, ruta, causa):
    pedido = {"json": cuerpo_generacion()} if metodo == "post" else {}
    respuesta = getattr(cliente, metodo)(ruta, **pedido)
    assert respuesta.status_code == 404
    assert respuesta.json()["causa"] == causa
