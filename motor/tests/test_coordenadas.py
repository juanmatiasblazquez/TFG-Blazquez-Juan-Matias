"""D21: conversión entre EPSG:4326 y el sistema de cálculo (POSGAR 2007, Gauss-Krüger)."""

import pytest
from pyproj import Geod
from shapely import LineString, Point, Polygon, box
from shapely.affinity import translate

from motor_trazados.coordenadas import (
    a_geograficas,
    a_geograficas_todas,
    a_metros,
    faja_del_este,
    faja_posgar2007,
    nombre_sistema,
    srid_posgar2007,
    srid_sugerido,
    validar_srid_calculo,
)

CORDOBA = (-64.1833, -31.4167)  # Plaza San Martín, aproximada
FAJA_4 = 5346
GRS80 = Geod(ellps="GRS80")


@pytest.mark.parametrize(
    ("longitud", "faja"),
    [(-64.1833, 4), (-65.0, 3), (-64.5, 4), (-61.6, 4), (-61.5, 5), (-69.0, 2), (-80.0, 1), (-50.0, 7)],
)
def test_faja_por_longitud(longitud, faja):
    # Cada faja abarca ±1,5° de su meridiano central; en el límite exacto se toma la del este.
    assert faja_posgar2007(longitud) == faja


def test_srid_de_cada_faja():
    assert [srid_posgar2007(f) for f in range(1, 8)] == list(range(5343, 5350))
    with pytest.raises(ValueError):
        srid_posgar2007(8)


def test_el_srid_sugerido_para_cordoba_es_la_faja_4():
    terreno = Point(CORDOBA).buffer(0.002)
    assert srid_sugerido(terreno) == FAJA_4


def test_valor_dorado_de_un_punto_de_cordoba():
    """Si falla después de subir pyproj (o PROJ), cambió la transformación y las alternativas
    guardadas ya no se reproducen: es una decisión a registrar en docs/decisiones.md (D21)."""
    punto = a_metros(Point(CORDOBA), FAJA_4)
    assert punto.x == pytest.approx(4_387_480.687, abs=1e-3)
    assert punto.y == pytest.approx(6_524_185.508, abs=1e-3)


def test_ida_y_vuelta_desde_geograficas():
    original = Point(CORDOBA).buffer(0.003, quad_segs=4)
    vuelta = a_geograficas(a_metros(original, FAJA_4), FAJA_4)
    assert vuelta.hausdorff_distance(original) < 1e-9  # grados: menos de 0,1 mm


def test_ida_y_vuelta_desde_metros():
    centro = a_metros(Point(CORDOBA), FAJA_4)
    original = translate(box(-240, -135, 240, 135), centro.x, centro.y)
    vuelta = a_metros(a_geograficas(original, FAJA_4), FAJA_4)
    assert vuelta.hausdorff_distance(original) < 1e-6  # m
    assert vuelta.area == pytest.approx(original.area, abs=1e-3)


def superficie_relativa(longitud: float) -> float:
    """(superficie planimétrica en la faja 4) / (superficie elipsoidal) de un cuadrado de 1 km."""
    lado = 0.0105  # ≈ 1 km de latitud
    terreno = box(longitud, -31.42, longitud + lado, -31.42 + lado)
    elipsoidal = abs(GRS80.geometry_area_perimeter(terreno)[0])
    return a_metros(terreno, FAJA_4).area / elipsoidal


def test_superficie_sobre_el_meridiano_central():
    # En el meridiano central de la faja (−63°) el factor de escala es 1.
    assert superficie_relativa(-63.005) == pytest.approx(1, abs=1e-5)


def test_superficie_en_la_ciudad_de_cordoba():
    """A 1,2° del meridiano central, el plano agranda las superficies un 0,03 % (el factor de
    escala de Gauss-Krüger). En el borde de la faja no llega al 0,06 %."""
    relativa = superficie_relativa(-64.2)
    assert 1.0001 < relativa < 1.0006


def test_el_sistema_de_calculo_tiene_que_estar_en_metros():
    with pytest.raises(ValueError, match="metros"):
        validar_srid_calculo(4326)
    with pytest.raises(ValueError):
        a_metros(Polygon([(0, 0), (1, 0), (1, 1)]), 4326)


def test_convertir_de_a_muchas_da_lo_mismo_que_de_a_una():
    srid = srid_posgar2007(4)
    centro = a_metros(Point(-64.12, -31.505), srid)
    geometrias = [centro, centro.buffer(30), LineString([(centro.x, centro.y), (centro.x + 50, centro.y)])]
    todas = a_geograficas_todas(geometrias, srid)
    assert [g.wkb for g in todas] == [a_geograficas(g, srid).wkb for g in geometrias]
    assert a_geograficas_todas([], srid) == []


def test_un_codigo_que_no_existe_tambien_es_value_error():
    # La API traduce ValueError a un 422 con el campo; un CRSError de pyproj sería un 500.
    with pytest.raises(ValueError, match="no es un sistema de coordenadas conocido"):
        validar_srid_calculo(999999)


def test_el_nombre_del_sistema_de_calculo():
    assert nombre_sistema(FAJA_4) == "POSGAR 2007 / Argentina 4"


@pytest.mark.parametrize(
    ("este", "faja"), [(4_436_512.3, 4), (4_500_000, 4), (3_612_000, 3), (512_000, None), (9_100_000, None)]
)
def test_la_faja_sale_del_millon_del_este(este, faja):
    """El falso este de la faja n es n × 1.000.000 + 500.000 (D80)."""
    assert faja_del_este(este) == faja


def test_el_falso_este_de_la_faja_4_es_el_de_pyproj():
    x, _ = a_metros(Point(-63.0, -31.4), FAJA_4).coords[0]
    # Sobre el meridiano central el este es el falso este; los centímetros salen del cambio de marco de
    # pyproj entre WGS 84 y POSGAR 2007.
    assert x == pytest.approx(4_500_000, abs=1) and faja_del_este(x) == 4
