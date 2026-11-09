"""La red como grafo (CU07, paso 1): conexidad, componentes y caminos mínimos, con grafos a mano."""

import pytest
from shapely import Point

from motor_trazados.red import RedCirculacion
from trazados import LOCAL


def red_en_l() -> RedCirculacion:
    """(0,0) → (100,0) → (100,50): una L de 150 m."""
    red = RedCirculacion()
    red.agregar_tramo((0, 0), (100, 0), None, LOCAL)
    red.agregar_tramo((100, 0), (100, 50), None, LOCAL)
    return red


def test_una_red_conexa_con_sus_accesos():
    assert red_en_l().es_conexa([Point(0, 0), Point(100, 50)])


def test_un_acceso_sobre_el_ancho_de_la_calle_abre_a_ella():
    # El corredor local mide 12 m: un acceso a 5 m del eje está en la boca de la calle.
    assert red_en_l().es_conexa([Point(0, 5)])
    assert not red_en_l().es_conexa([Point(0, 7)])


def test_dos_componentes_no_son_una_red_conexa():
    red = red_en_l()
    red.agregar_tramo((0, 100), (30, 100), None, LOCAL)
    assert not red.es_conexa([Point(0, 0)])
    assert red.componentes_aisladas() == [[(0.0, 100.0), (30.0, 100.0)]]


def test_una_red_vacia_no_es_conexa():
    assert not RedCirculacion().es_conexa([])


def test_longitud_total():
    assert red_en_l().longitud_total() == pytest.approx(150)


def test_distancias_desde_los_accesos():
    distancias = red_en_l().distancias_desde([Point(0, 0)])
    assert distancias == pytest.approx({(0.0, 0.0): 0, (100.0, 0.0): 100, (100.0, 50.0): 150})


def test_distancias_por_red_toman_el_acceso_mas_cercano_y_el_mismo_tramo():
    red = red_en_l()
    # Un destino sobre el primer tramo y otro sobre el segundo; dos accesos en los extremos.
    distancias = red.distancias_por_red([Point(0, 0), Point(100, 50)], [Point(30, 0), Point(100, 40)])
    assert distancias == pytest.approx([30, 10])


def test_la_matriz_de_distancias_da_cada_par():
    """Filas: orígenes; columnas: destinos (D44). Por el codo de la L, o derecho si están sobre
    el mismo tramo, sin sumar el tramo perpendicular hasta el eje (D26)."""
    red = red_en_l()
    matriz = red.matriz_distancias([Point(0, 0), Point(100, 50), Point(20, 3)], [Point(30, 0), Point(100, 40)])
    assert matriz.shape == (3, 2)
    assert matriz.ravel().tolist() == pytest.approx([30, 140, 120, 10, 10, 120])


def test_la_matriz_y_las_distancias_por_red_son_la_misma_cuenta():
    red = red_en_l()
    red.agregar_tramo((0, 0), (0, 50), None, LOCAL)
    red.agregar_tramo((0, 50), (100, 50), None, LOCAL)  # ahora hay dos caminos: un anillo
    origenes = [Point(10, 0), Point(0, 40)]
    destinos = [Point(60, 50), Point(100, 10), Point(5, 0)]
    matriz = red.matriz_distancias(origenes, destinos)
    assert red.distancias_por_red(origenes, destinos) == pytest.approx(matriz.min(axis=0).tolist())
    # (60, 50) desde (0, 40): 10 hasta la esquina y 60 por arriba.
    assert matriz[1, 0] == pytest.approx(70)


def test_un_destino_sin_camino_no_tiene_distancia():
    red = red_en_l()
    red.agregar_tramo((0, 100), (30, 100), None, LOCAL)
    assert red.distancias_por_red([Point(0, 0)], [Point(10, 100)]) == [None]


def test_partir_un_tramo_agrega_un_nodo_intermedio():
    red = red_en_l()
    nodo = red.partir_en(Point(40, 0))
    assert nodo == (40.0, 0.0)
    assert red.grado(nodo) == 2
    assert len(red.tramos()) == 3
    assert red.longitud_total() == pytest.approx(150)


def test_el_nodo_de_un_acceso_unido_con_un_conector_es_el_propio_acceso():
    red = red_en_l()
    red.agregar_tramo((100, 50), (100, 80), None, LOCAL)  # el conector termina en el acceso
    assert red.nodo_de_acceso(Point(100, 80)) == (100.0, 80.0)


def test_el_nodo_de_un_acceso_en_la_boca_de_la_calle_es_el_extremo_de_la_calle():
    # A 5 m del eje (corredor de 12 m): abre a la calle, y entra por su extremo (0, 0).
    assert red_en_l().nodo_de_acceso(Point(0, 5)) == (0.0, 0.0)


def test_un_acceso_que_no_abre_a_ninguna_calle_no_tiene_nodo():
    assert red_en_l().nodo_de_acceso(Point(50, 30)) is None


def test_los_nodos_se_identifican_al_milimetro():
    red = RedCirculacion()
    red.agregar_tramo((0, 0), (10, 0), None, LOCAL)
    red.agregar_tramo((10.0000001, 0), (20, 0), None, LOCAL)
    assert red.nodos() == [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
