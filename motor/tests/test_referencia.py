"""El comando de los casos de referencia escribe un GeoJSON por capa sobre Córdoba e
indicadores.json, en una carpeta por caso."""

import json

from motor_trazados.referencia import CASOS, CENTRO, main

CAPAS = ("terreno", "accesos", "ejes", "calles", "manzanas", "lotes", "espacios_verdes", "incumplimientos")


def coordenadas(geometria):
    if geometria["type"] == "Point":
        return [geometria["coordinates"]]
    pila, puntos = [geometria["coordinates"]], []
    while pila:
        actual = pila.pop()
        if isinstance(actual[0], (int, float)):
            puntos.append(actual)
        else:
            pila.extend(actual)
    return puntos


def test_el_comando_escribe_las_capas_y_los_indicadores(tmp_path, resultado_referencia, capsys):
    main(["--salida", str(tmp_path)])
    carpeta = tmp_path / "referencia"
    for capa in CAPAS:
        coleccion = json.loads((carpeta / f"{capa}.geojson").read_text(encoding="utf-8"))
        assert coleccion["type"] == "FeatureCollection"
        if capa == "incumplimientos":
            # Con el asignador, el rectangular cumple todo (D44): la capa existe, vacía.
            assert coleccion["features"] == []
            continue
        assert coleccion["features"], f"la capa {capa} está vacía"
        for feature in coleccion["features"]:
            for longitud, latitud in coordenadas(feature["geometry"]):
                # EPSG:4326 (RFC 7946): el terreno se extiende unos 270 m al este y al oeste de
                # su centro, y unos 210 m al norte y al sur.
                assert abs(longitud - CENTRO[0]) < 0.004 and abs(latitud - CENTRO[1]) < 0.003
    lotes = json.loads((carpeta / "lotes.geojson").read_text(encoding="utf-8"))["features"]
    assert len(lotes) == len(resultado_referencia.lotes)
    assert {"designacion", "frente", "fondo", "superficie", "cumple", "motivos"} <= lotes[0]["properties"].keys()

    datos = json.loads((carpeta / "indicadores.json").read_text(encoding="utf-8"))
    assert datos["srid_calculo"] == 5346
    utiles = resultado_referencia.indicadores.cantidad_celdas
    assert datos["indicadores"]["cantidad_celdas"] == utiles
    # Con el asignador, el rectangular cumple todo, también la cesión (D44).
    assert datos["incumplimientos"] == {}
    assert "indicadores.json" in capsys.readouterr().out


def test_con_todos_escribe_cada_caso_con_sus_espacios_verdes_y_libres(tmp_path):
    main(["--todos", "--salida", str(tmp_path)])
    for nombre in CASOS:
        datos = json.loads((tmp_path / nombre / "indicadores.json").read_text(encoding="utf-8"))
        assert datos["cantidad"]["celdas"]["lote"] > 0
        for capa in ("espacios_verdes", "espacios_libres"):
            assert (tmp_path / nombre / f"{capa}.geojson").exists()
    # Las formas de la verificación visual tienen las tres clases de celda (D41), salvo la L, cuyas
    # puntas son verde con la calle de borde (D50), y la U, que por lado no deja puntas (D86).
    for nombre in ("irregular", "l", "u", "triangulo"):
        indicadores = json.loads((tmp_path / nombre / "indicadores.json").read_text(encoding="utf-8"))
        esperadas = {"lote", "espacio_verde"} | ({"espacio_libre"} if nombre not in ("l", "u") else set())
        assert set(indicadores["cantidad"]["celdas"]) == esperadas, nombre
