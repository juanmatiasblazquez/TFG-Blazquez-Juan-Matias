"""Remanentes (D41, D43): qué pieza es un lote, cuándo una fracción se suma a su vecino y cuándo
un remanente es espacio verde o libre. Casos armados a mano, justo arriba y justo abajo de cada
umbral, con los valores de referencia (verde: 1.000 m², 20 m de ancho y acceso a una calle;
lote: relación fondo/frente 3 y ancho útil de 10 m; tope de unión: 1,5 veces el lote típico).

Una calle local de 12 m corre por y ∈ [−12, 0], con su eje en y = −6: toda pieza apoyada en
y = 0 da a la calle.
"""

import pytest
from shapely import LineString, MultiLineString, Polygon, box
from shapely.affinity import rotate

from motor_trazados import CeldaGenerada, TipoCelda
from motor_trazados.geometria import IndiceEjes, alcanza_ancho, ancho
from motor_trazados.remanentes import ClasificadorRemanentes, es_espacio_verde, toca_la_red
from motor_trazados.subdivisores import SubdivisorLoteo
from motor_trazados.valores_referencia import PARAMETROS_LOTEO_REFERENCIA as P

CALLE = box(-20, -12, 400, 0)
EJES = IndiceEjes([LineString([(-20, -6), (400, -6)])])


def pieza(geometria: Polygon, numero: int) -> CeldaGenerada:
    return CeldaGenerada(geometria, TipoCelda.LOTE, 0.0, 0.0, 1, f"M1-L{numero:02d}")


def clasificar(*geometrias):
    piezas = [pieza(g, k) for k, g in enumerate(geometrias, 1)]
    return ClasificadorRemanentes().clasificar(piezas, CALLE, EJES, P)


# --- Ancho: el diámetro del mayor círculo inscripto -----------------------------------------


@pytest.mark.parametrize(
    ("poligono", "esperado"),
    [
        (box(0, 0, 30, 30), 30.0),  # una plaza cuadrada
        (box(0, 0, 12, 100), 12.0),  # una franja: su ancho
        (Polygon([(0, 0), (40, 0), (0, 30)]), 20.0),  # triángulo 30-40-50: radio inscripto 10
        (box(0, 0, 100, 40).union(box(0, 0, 10, 200)), 40.0),  # una L: su parte más ancha
    ],
)
def test_el_ancho_es_el_diametro_del_mayor_circulo_inscripto(poligono, esperado):
    assert ancho(poligono) == pytest.approx(esperado, abs=0.01)


FORMAS_DE_ANCHO = [
    box(0, 0, 12, 30),
    rotate(box(0, 0, 11.67, 27.75), 20, origin=(0, 0)),
    Polygon([(0, 0), (40, 0), (0, 30)]),
    box(0, 0, 100, 40).union(box(0, 0, 10, 200)),
    box(0, 0, 30, 6).union(box(0, 0, 6, 30)),
    Polygon([(0, 4.24), (4.24, 0), (12, 0), (12, 30), (0, 30)]),  # lote en esquina, con ochava
    box(0, 0, 60, 60).difference(box(20, 20, 40, 40).buffer(3)),  # una plaza con un hueco curvo
]


@pytest.mark.parametrize("poligono", FORMAS_DE_ANCHO)
@pytest.mark.parametrize("delta", [-0.004, 0.004, -0.02, 0.02])
def test_alcanza_ancho_dice_lo_mismo_que_el_circulo_inscripto(poligono, delta):
    """`alcanza_ancho` decide sin buscar el círculo (D43): erosiona el polígono la mitad del
    mínimo. Tiene que decir lo mismo que `ancho + tolerancia ≥ mínimo`, también a milímetros del
    umbral."""
    minimo = ancho(poligono) + 0.01 + delta
    assert alcanza_ancho(poligono, minimo) is (ancho(poligono) + 0.01 >= minimo)


# --- Espacio verde: superficie, ancho y acceso, con la tolerancia del verificador -----------


@pytest.mark.parametrize(
    ("poligono", "verde"),
    [
        (box(0, 0, 25, 40.004), True),  # 1.000,1 m² y 25 m de ancho
        (box(0, 0, 25, 39.996), False),  # 999,9 m²: no llega a la superficie mínima
        (box(0, 0, 20.05, 60), True),  # 20,05 m de ancho
        (box(0, 0, 19.95, 60), False),  # 19,95 m: no llega al ancho mínimo
        (box(0, 0, 19.995, 60), True),  # a menos de 1 cm del mínimo no se excluye
    ],
)
def test_el_verde_necesita_la_superficie_y_el_ancho_minimos(poligono, verde):
    assert es_espacio_verde(poligono, CALLE, P) is verde


def test_un_remanente_que_no_da_a_ninguna_calle_no_es_verde():
    """Decisión del autor (D41): un verde sin acceso público no tiene «ubicación adecuada»."""
    apoyado, separado = box(0, 0, 40, 40), box(0, 5, 40, 45)
    assert toca_la_red(apoyado, CALLE) and es_espacio_verde(apoyado, CALLE, P)
    assert not toca_la_red(separado, CALLE) and not es_espacio_verde(separado, CALLE, P)


def test_los_umbrales_del_verde_son_configurables():
    from dataclasses import replace

    chico = box(0, 0, 15, 50)  # 750 m², 15 m de ancho
    assert not es_espacio_verde(chico, CALLE, P)
    assert es_espacio_verde(chico, CALLE, replace(P, superficie_minima_verde=600, ancho_minimo_verde=15))


# --- Clasificación y fusión -------------------------------------------------------------------


# --- Criterio de forma (D43): lo que no tiene forma de lote es remanente --------------------


def test_una_l_angosta_es_remanente():
    """Brazos de 6 m: 30 m de frente, 30 de fondo, 324 m² y relación 1, pero en ningún lugar
    entra un círculo de 10 m."""
    (celda,) = clasificar(box(200, 0, 230, 6).union(box(200, 0, 206, 30)))
    assert celda.tipo is TipoCelda.ESPACIO_LIBRE


def test_un_lote_bandera_es_remanente():
    """Un pasillo de 10 × 30 m hasta un fondo de 25 × 20 m: 10 m de frente, 800 m² y ancho útil
    de 20 m, pero 50 m de fondo: relación 5 > 3."""
    (celda,) = clasificar(box(100, 0, 110, 30).union(box(95, 30, 120, 50)))
    assert celda.tipo is TipoCelda.ESPACIO_LIBRE


def test_la_franja_de_11_5_por_140_es_remanente():
    """La franja que motivó el criterio (D41, D43): 11,5 m de frente, 140 de fondo y 1.610 m².
    Alcanza los mínimos, pero su relación es 12,2. Tampoco es verde: 11,5 m de ancho < 20."""
    (celda,) = clasificar(box(300, 0, 311.5, 140))
    assert celda.tipo is TipoCelda.ESPACIO_LIBRE


def test_un_lote_normal_de_la_grilla_no_cae_por_la_forma():
    """El lote del caso rectangular (11,67 × 27,75 m) y uno de frente mínimo (10 × 30 m)."""
    assert [c.tipo for c in clasificar(box(0, 0, 11.67, 27.75))] == [TipoCelda.LOTE]
    assert [c.tipo for c in clasificar(box(0, 0, 10, 30))] == [TipoCelda.LOTE]


def test_un_lote_que_cumple_los_minimos_sigue_siendo_lote():
    (celda,) = clasificar(box(0, 0, 12, 30))
    assert celda.tipo is TipoCelda.LOTE and celda.designacion == "M1-L01"
    assert celda.frente == pytest.approx(12) and celda.fondo == pytest.approx(30)


def test_una_fraccion_angosta_se_suma_al_lote_vecino_si_el_resultado_cumple():
    """La punta de 6 m no alcanza el frente mínimo; sumada al lote vecino da 18 × 30 m = 540 m²,
    que cumple todo y es justo el tope de unión (1,5 × 360 m²)."""
    celdas = clasificar(box(0, 0, 12, 30), box(12, 0, 24, 30), box(24, 0, 30, 30))
    assert [c.tipo for c in celdas] == [TipoCelda.LOTE, TipoCelda.LOTE]
    assert celdas[1].geometria.area == pytest.approx(540)


def test_si_la_suma_pasa_la_superficie_maxima_la_fraccion_queda_como_remanente():
    """Con 9 m, el lote sumado tendría 21 × 30 = 630 m² > 600: la fracción queda libre."""
    celdas = clasificar(box(0, 0, 12, 30), box(12, 0, 24, 30), box(24, 0, 33, 30))
    assert [c.tipo for c in celdas] == [TipoCelda.LOTE, TipoCelda.LOTE, TipoCelda.ESPACIO_LIBRE]
    assert celdas[2].designacion == "M1-EL01"
    assert celdas[1].geometria.area == pytest.approx(360)


@pytest.mark.parametrize(("ancho_fraccion", "se_une"), [(5.99, True), (6.01, False)])
def test_la_union_no_pasa_el_tope_de_un_lote_y_medio(ancho_fraccion, se_une):
    """Lotes típicos de 12 × 30 m (360 m²): el tope es 540 m² (D43). Con una fracción de 5,99 m
    el lote unido tiene 539,7 m² y se une; con 6,01 m tendría 540,3 m², que pasa el tope aunque
    no pase la superficie máxima (600 m²), y la fracción queda como remanente."""
    celdas = clasificar(box(0, 0, 12, 30), box(12, 0, 24, 30), box(24, 0, 24 + ancho_fraccion, 30))
    if se_une:
        assert [c.tipo for c in celdas] == [TipoCelda.LOTE, TipoCelda.LOTE]
        assert celdas[1].geometria.area == pytest.approx(30 * (12 + ancho_fraccion))
    else:
        assert [c.tipo for c in celdas] == [TipoCelda.LOTE, TipoCelda.LOTE, TipoCelda.ESPACIO_LIBRE]
        assert celdas[1].geometria.area == pytest.approx(360)


def test_el_tope_de_union_es_configurable():
    from dataclasses import replace

    piezas = [pieza(g, k) for k, g in enumerate((box(0, 0, 12, 30), box(12, 0, 24, 30), box(24, 0, 30, 30)), 1)]
    estricto = ClasificadorRemanentes().clasificar(piezas, CALLE, EJES, replace(P, factor_union_maximo=1.2))
    assert [c.tipo for c in estricto] == [TipoCelda.LOTE, TipoCelda.LOTE, TipoCelda.ESPACIO_LIBRE]


def test_las_fracciones_vecinas_sin_lote_forman_una_sola_zona():
    """Dos piezas de 12 × 10 m (fondo de 10 m) sin lotes vecinos: un solo espacio libre."""
    celdas = clasificar(box(40, 0, 52, 10), box(52, 0, 64, 10))
    assert [(c.tipo, c.designacion) for c in celdas] == [(TipoCelda.ESPACIO_LIBRE, "M1-EL01")]
    assert celdas[0].geometria.area == pytest.approx(240)


def test_una_zona_grande_y_ancha_sobre_la_calle_es_espacio_verde():
    """60 × 22 m: no es lote (22 m de fondo < 25), pero tiene 1.320 m², 22 m de ancho y frente."""
    (celda,) = clasificar(box(70, 0, 130, 22))
    assert celda.tipo is TipoCelda.ESPACIO_VERDE and celda.designacion == "M1-EV01"


# --- Fondo máximo en las manzanas de borde (D40) --------------------------------------------


def test_una_manzana_de_borde_profunda_deja_un_remanente_detras_de_los_lotes():
    """120 × 60 m con frente abajo: 10 lotes de 12 m, cuyo fondo útil es min(3 × 12, 600 / 12)
    = 36 m. Lo que queda detrás (120 × 24 m) es una pieza más."""
    manzana = box(0, 0, 120, 60)
    piezas = SubdivisorLoteo().subdividir(manzana, [LineString([(0, 0), (120, 0)])], P, 1)
    assert len(piezas) == 11
    for lote in piezas[:10]:
        assert lote.geometria.bounds[3] == pytest.approx(36)
        assert lote.geometria.area == pytest.approx(12 * 36)
    assert piezas[10].geometria.area == pytest.approx(120 * 24)


def test_una_manzana_con_frente_de_los_dos_lados_no_se_corta_por_fondo():
    """120 × 80 m con frentes abajo y arriba: dos franjas de 40 m, sin corazón de manzana."""
    manzana = box(0, 0, 120, 80)
    frentes = [LineString([(0, 0), (120, 0)]), LineString([(0, 80), (120, 80)])]
    piezas = SubdivisorLoteo().subdividir(manzana, frentes, P, 1)
    assert len(piezas) == 20
    assert all(p.geometria.area == pytest.approx(12 * 40) for p in piezas)


def test_si_el_fondo_util_no_alcanza_el_minimo_no_se_corta():
    """Con relación máxima 2 y frente de 12 m, el fondo útil sería 24 m < 25: no se corta."""
    from dataclasses import replace

    manzana = box(0, 0, 120, 60)
    piezas = SubdivisorLoteo().subdividir(
        manzana, [LineString([(0, 0), (120, 0)])], replace(P, relacion_fondo_frente_max=2), 1
    )
    assert len(piezas) == 10


def test_la_franja_de_la_calle_no_cruza_una_ranura_del_terreno():
    """Una calle colectora (20 m) llega al borde de una ranura de 6 m. Su franja se alarga 60 m
    para no dejar cuñas, pero el pedazo que reaparece del otro lado no es calle de este tramo
    (D40)."""
    from motor_trazados.corredores import MaterializadorCorredores
    from motor_trazados.red import RedCirculacion
    from trazados import COLECTORA

    dominio = box(0, 0, 200, 100).difference(box(100, 40, 106, 100))
    red = RedCirculacion()
    tramo = red.agregar_tramo((0, 70), (100, 70), None, COLECTORA)
    franja = MaterializadorCorredores()._franja(tramo, dominio, red)
    assert franja.geom_type == "Polygon"
    assert franja.bounds[2] == pytest.approx(100, abs=0.01)
    assert not franja.intersects(MultiLineString([[(106, 41), (106, 99)]]).buffer(1))
