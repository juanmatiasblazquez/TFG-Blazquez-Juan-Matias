"""CU03 → CU06 de punta a punta: crear el proyecto, generar, leer de la base y comparar con lo
que devuelve el motor por su cuenta (secuencia de la p. 43; D30)."""

import motor_trazados
import pytest
from geoalchemy2.shape import to_shape
from motor_trazados import Estrategia, MotorGeneracion, PatronRed, SolicitudGeneracion, TipoProyecto
from motor_trazados.coordenadas import a_geograficas_todas, a_metros
from motor_trazados.referencia import ROTACION, SEMILLA, srid_referencia
from motor_trazados.valores_referencia import JERARQUIAS_REFERENCIA, PARAMETROS_LOTEO_REFERENCIA

from app.models import Proyecto, VersionAlternativa

# El error de guardar un valor en numeric(…, 2) es de medio centésimo como mucho. Un valor que cae
# justo en el medio (11,875 → 11,88) lo alcanza, y en coma flotante lo pasa por un pelo.
MEDIO_CENTESIMO = 0.005 + 1e-9


def test_crear_un_proyecto_lo_deja_listo_para_generar(cliente, crear_proyecto):
    proyecto = crear_proyecto()
    assert proyecto["srid_calculo"] == srid_referencia() == 5346  # faja 4, por la longitud
    assert proyecto["estado"] == "listo_para_generar"
    # El responsable es quien inició la sesión: el director técnico de prueba (D63).
    assert proyecto["responsable"]["apellido"] == "Directora"
    # 480 × 270 m, medido en el sistema de cálculo como lo mide el motor.
    assert proyecto["terreno"]["properties"]["superficie_m2"] == pytest.approx(129600, abs=0.01)
    assert proyecto["terreno"]["properties"]["perimetro_m"] == pytest.approx(1500, abs=0.01)
    assert [f["properties"]["designacion"] for f in proyecto["accesos"]["features"]] == ["A1", "A2"]

    parametros = proyecto["parametros"]
    assert (parametros["version"], parametros["vigente"]) == (1, True)
    assert parametros["porcentaje_espacio_verde"] == PARAMETROS_LOTEO_REFERENCIA.porcentaje_espacio_verde
    assert parametros["loteo"]["frente_minimo_m"] == PARAMETROS_LOTEO_REFERENCIA.frente_minimo
    assert [(j["orden"], j["radio_ochava_m"]) for j in parametros["jerarquias"]] == [
        (j.orden, j.radio_ochava) for j in JERARQUIAS_REFERENCIA
    ]
    assert proyecto["alternativas"] == []
    assert cliente.get(f"/api/proyectos/{proyecto['id_proyecto']}").json() == proyecto


def test_el_201_trae_la_ubicacion_y_lo_mismo_que_el_get(cliente, crear_proyecto):
    proyecto = crear_proyecto()
    respuesta = cliente.post(
        f"/api/proyectos/{proyecto['id_proyecto']}/alternativas",
        json={"estrategia": {"patron_red": "grilla", "orientacion_grados": ROTACION, "semilla": SEMILLA}},
    )
    assert respuesta.status_code == 201
    alternativa = respuesta.json()
    assert respuesta.headers["location"] == f"/api/alternativas/{alternativa['id_alternativa']}"
    assert cliente.get(respuesta.headers["location"]).json() == alternativa
    assert alternativa["codigo"] == "A"
    version = alternativa["version"]
    assert (version["numero"], version["version_parametros"]) == (1, 1)
    assert version["version_motor"] == motor_trazados.__version__
    assert version["estrategia"] == {"patron_red": "grilla", "orientacion_grados": ROTACION, "semilla": SEMILLA}
    # El caso de referencia (D27): con el asignador de espacios verdes cumple todo, también la
    # cesión; de los 286 lotes, los que pasaron a ser plaza son verde (D44).
    assert version["cumple_restricciones"] is True
    assert version["capas"]["incumplimientos"]["features"] == []
    i = version["indicadores"]
    assert i["porcentaje_cesion"] >= 10
    assert 0 < i["cantidad_celdas"] < 286
    tipos = {f["properties"]["tipo"] for f in version["capas"]["celdas"]["features"]}
    assert tipos == {"lote", "espacio_verde"}
    accesos = sorted(f["properties"]["acceso"] for f in version["capas"]["nodos"]["features"] if f["properties"]["acceso"])
    assert accesos == ["A1", "A2"]


@pytest.mark.parametrize("caso", ["referencia", "irregular"])
def test_lo_guardado_es_lo_que_genera_el_motor_por_su_cuenta(crear_proyecto, generar, db, caso):
    """La solicitud se arma acá a mano, desde los valores de referencia del motor y el terreno
    guardado: si el servicio cruzara un parámetro o una jerarquía, el resultado no coincidiría.
    El caso irregular (D40) tiene además espacios verdes y libres (D41)."""
    proyecto = crear_proyecto(caso=caso)
    alternativa = generar(proyecto["id_proyecto"])

    guardado = db.get(Proyecto, proyecto["id_proyecto"])
    srid = guardado.srid_calculo
    solicitud = SolicitudGeneracion(
        TipoProyecto.LOTEO,
        a_metros(to_shape(guardado.terreno.geom), srid),
        [a_metros(to_shape(a.geom), srid) for a in guardado.terreno.accesos],
        PARAMETROS_LOTEO_REFERENCIA,
        JERARQUIAS_REFERENCIA,
        Estrategia(PatronRed.GRILLA, ROTACION, SEMILLA),
    )
    esperado = MotorGeneracion().generar(solicitud)
    version = db.get(VersionAlternativa, alternativa["version"]["id_version"])

    assert len(version.nodos) == len(esperado.red.nodos())
    assert len(version.tramos) == len(esperado.red.tramos())
    assert [m.designacion for m in version.manzanas] == [f"M{i}" for i in range(1, len(esperado.manzanas) + 1)]
    manzanas_4326 = a_geograficas_todas(esperado.manzanas, srid)
    for manzana, m, m_4326 in zip(version.manzanas, esperado.manzanas, manzanas_4326, strict=True):
        assert to_shape(manzana.geom).equals_exact(m_4326, 0)
        assert float(manzana.superficie_m2) == pytest.approx(m.area, abs=MEDIO_CENTESIMO)
    ejes_4326 = a_geograficas_todas([t.eje for t in esperado.red.tramos()], srid)
    for tramo, t, eje_4326 in zip(version.tramos, esperado.red.tramos(), ejes_4326, strict=True):
        assert to_shape(tramo.eje).equals_exact(eje_4326, 0)
        assert tramo.jerarquia.orden == t.jerarquia.orden

    marcadas = {c.designacion for c in esperado.celdas_no_conformes()}
    celdas = {c.designacion: c for c in version.celdas}
    assert sorted(celdas) == sorted(c.designacion for c in esperado.celdas)
    celdas_4326 = a_geograficas_todas([c.geometria for c in esperado.celdas], srid)
    for c, c_4326 in zip(esperado.celdas, celdas_4326, strict=True):
        celda = celdas[c.designacion]
        assert to_shape(celda.geom).equals_exact(c_4326, 0), c.designacion
        assert celda.manzana.designacion == f"M{c.indice_manzana}"
        assert (celda.tipo, celda.cumple) == (str(c.tipo), c.designacion not in marcadas)
        assert float(celda.superficie_m2) == pytest.approx(c.geometria.area, abs=MEDIO_CENTESIMO)
        assert float(celda.frente_m) == pytest.approx(c.frente, abs=MEDIO_CENTESIMO)
        assert float(celda.fondo_m) == pytest.approx(c.fondo, abs=MEDIO_CENTESIMO)

    assert [(i.tipo, i.elemento, i.detalle) for i in version.incumplimientos] == [
        (str(i.tipo), i.elemento, i.detalle) for i in esperado.incumplimientos
    ]
    i = esperado.indicadores
    assert version.cumple_restricciones == esperado.cumple()
    assert version.cantidad_celdas == i.cantidad_celdas
    assert float(version.superficie_aprovechable_m2) == pytest.approx(i.superficie_aprovechable, abs=MEDIO_CENTESIMO)
    assert float(version.porcentaje_circulacion) == pytest.approx(i.porcentaje_circulacion, abs=MEDIO_CENTESIMO)
    assert float(version.porcentaje_espacio_verde) == pytest.approx(i.porcentaje_espacio_verde, abs=MEDIO_CENTESIMO)
    assert float(version.longitud_red_m) == pytest.approx(i.longitud_red, abs=MEDIO_CENTESIMO)
    assert float(version.distancia_media_acceso_m) == pytest.approx(i.distancia_media_acceso, abs=MEDIO_CENTESIMO)
    # Los indicadores de la 0006 (D47, D48).
    assert version.cantidad_lotes_grandes == i.cantidad_lotes_grandes
    assert float(version.porcentaje_avenidas) == pytest.approx(i.porcentaje_avenidas, abs=MEDIO_CENTESIMO)
    assert i.porcentaje_avenidas >= 20
    # Los de la 0007: la distancia de los lotes al verde más cercano (D51).
    assert float(version.distancia_media_verde_m) == pytest.approx(i.distancia_media_verde, abs=MEDIO_CENTESIMO)
    assert float(version.distancia_maxima_verde_m) == pytest.approx(i.distancia_maxima_verde, abs=MEDIO_CENTESIMO)
    assert 0 < i.distancia_media_verde <= i.distancia_maxima_verde
    assert version.duracion_ms > 0
    # Los que no tienen columna los deriva la API de lo guardado: tienen que dar lo mismo (D29).
    indicadores = alternativa["version"]["indicadores"]
    assert indicadores["porcentaje_aprovechamiento"] == pytest.approx(i.porcentaje_aprovechamiento, abs=MEDIO_CENTESIMO)
    assert indicadores["cantidad_fracciones_no_conformes"] == i.cantidad_fracciones_no_conformes
    # Los de los remanentes (D41) se guardan como los calcula el motor.
    assert float(version.superficie_espacio_verde_m2) == pytest.approx(i.superficie_espacio_verde, abs=MEDIO_CENTESIMO)
    assert float(version.superficie_espacio_libre_m2) == pytest.approx(i.superficie_espacio_libre, abs=MEDIO_CENTESIMO)
    assert float(version.porcentaje_cesion) == pytest.approx(i.porcentaje_cesion, abs=MEDIO_CENTESIMO)
    assert indicadores["porcentaje_cesion"] == float(version.porcentaje_cesion)


def test_un_poligono_irregular_genera_con_lotes_espacios_verdes_y_libres(cliente, crear_proyecto):
    """Hasta el motor 0.3.1 esto era un 422 «solo terrenos rectangulares» (D33). Ahora genera, y
    lo que no se puede lotear queda como espacio verde o libre (D40, D41)."""
    proyecto = crear_proyecto(caso="irregular")
    respuesta = cliente.post(
        f"/api/proyectos/{proyecto['id_proyecto']}/alternativas",
        json={"estrategia": {"patron_red": "grilla", "orientacion_grados": ROTACION, "semilla": SEMILLA}},
    )
    assert respuesta.status_code == 201, respuesta.text
    version = respuesta.json()["version"]
    celdas = [f["properties"] for f in version["capas"]["celdas"]["features"]]
    assert {c["tipo"] for c in celdas} == {"lote", "espacio_verde", "espacio_libre"}
    # Un remanente no es un lote: no se marca como no conforme ni cuenta como celda útil.
    assert all(c["cumple"] for c in celdas if c["tipo"] != "lote")
    assert all(c["designacion"].split("-")[1][:2] in ("EV", "EL") for c in celdas if c["tipo"] != "lote")
    i = version["indicadores"]
    assert i["cantidad_celdas"] == sum(1 for c in celdas if c["tipo"] == "lote" and c["cumple"])
    assert i["cantidad_fracciones_no_conformes"] == sum(1 for c in celdas if c["tipo"] == "lote" and not c["cumple"])
    verde = sum(c["superficie_m2"] for c in celdas if c["tipo"] == "espacio_verde")
    libre = sum(c["superficie_m2"] for c in celdas if c["tipo"] == "espacio_libre")
    assert i["superficie_espacio_verde_m2"] == pytest.approx(verde, abs=0.1)
    assert i["superficie_espacio_libre_m2"] == pytest.approx(libre, abs=0.1)
    assert 10 <= i["porcentaje_cesion"] < 100


def test_el_contorno_de_la_cesion_es_una_sola_linea(cliente, crear_proyecto, generar):
    """Las líneas rojas sueltas del portal eran los anillos interiores del contorno de la cesión
    (D39): ahora es una sola línea, el borde exterior. Con el asignador el rectangular cumple la
    cesión (D44): para que la incumpla, se pide un verde de 5 ha, que no entra en ninguna
    manzana."""
    id_proyecto = crear_proyecto()["id_proyecto"]
    valores = cliente.get("/api/parametros/referencia").json()["valores"]
    valores["loteo"]["superficie_minima_verde_m2"] = 50000
    assert cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores).status_code == 201
    alternativa = generar(id_proyecto)
    (cesion,) = [
        f for f in alternativa["version"]["capas"]["incumplimientos"]["features"]
        if f["properties"]["tipo"] == "cesion_espacio_verde"
    ]
    assert cesion["geometry"]["type"] == "MultiLineString"
    assert len(cesion["geometry"]["coordinates"]) == 1

