"""CU08: indicadores de un trazado armado a mano, con valores conocidos."""

from dataclasses import replace

import pytest
from shapely import box

from motor_trazados import Incumplimiento, TipoIncumplimiento
from motor_trazados.indicadores import CalculadorIndicadores
from trazados import ACCESO, P_TRAZADOS as P, libre, lote_frente_a_la_calle, trazado

# Calle de 120 × 12 m, diez lotes de 12 × 30 m al norte y verde de 120 × 30 m al sur.
SUPERFICIE_TERRENO = 120 * 72


def calcular(resultado):
    return CalculadorIndicadores().calcular(resultado, SUPERFICIE_TERRENO, [ACCESO], P)


def diez_lotes():
    return [lote_frente_a_la_calle(12 * k, 12, 30, k + 1) for k in range(10)]


def test_indicadores_de_un_trazado_conocido():
    indicadores = calcular(trazado(diez_lotes()))
    assert indicadores.cantidad_celdas == 10
    assert indicadores.cantidad_fracciones_no_conformes == 0
    assert indicadores.superficie_aprovechable == pytest.approx(3600)
    assert indicadores.porcentaje_aprovechamiento == pytest.approx(100 * 3600 / 8640)
    assert indicadores.porcentaje_circulacion == pytest.approx(100 * 1440 / 8640)
    assert indicadores.porcentaje_espacio_verde == pytest.approx(100 * 3600 / 8640)
    assert indicadores.longitud_red == pytest.approx(120)
    # Sin áreas reservadas, la base de los porcentajes es el terreno, bit a bit (D61).
    assert indicadores.superficie_reservada == 0
    assert indicadores.superficie_disponible == SUPERFICIE_TERRENO
    # El frente de cada lote se proyecta en x = 6, 18, …, 114 sobre el eje: media 60 m.
    assert indicadores.distancia_media_acceso == pytest.approx(60)
    # El verde de 120 × 30 m sobre los 3.600 m² de lotes: la cesión alcanzada es el 100 %.
    assert indicadores.superficie_espacio_verde == pytest.approx(3600)
    assert indicadores.superficie_verde_computable == pytest.approx(3600)
    assert indicadores.superficie_espacio_libre == 0
    assert indicadores.porcentaje_cesion == pytest.approx(100)
    assert indicadores.cantidad_lotes_grandes == 0


def test_el_verde_de_una_punta_no_computa_para_la_cesion():
    """Con el lado menor de 42 m, la manzana del trazado (30 m) es una punta: su verde se informa en
    el verde total, pero con «más cercanía» no computa para la cesión (D55, D58)."""
    indicadores = CalculadorIndicadores().calcular(
        trazado(diez_lotes()), SUPERFICIE_TERRENO, [ACCESO], replace(P, lado_minimo_manzana=42.0)
    )
    assert indicadores.superficie_espacio_verde == pytest.approx(3600)
    assert indicadores.porcentaje_espacio_verde == pytest.approx(100 * 3600 / 8640)
    assert indicadores.superficie_verde_computable == 0
    assert indicadores.porcentaje_cesion == 0


def test_con_menos_lotes_el_verde_de_una_punta_computa():
    """La misma punta con «menos lotes»: el verde computable es todo el verde (D58)."""
    from motor_trazados import CriterioEspacioVerde

    p = replace(P, lado_minimo_manzana=42.0, criterio_espacio_verde=CriterioEspacioVerde.MENOS_LOTES)
    indicadores = CalculadorIndicadores().calcular(trazado(diez_lotes()), SUPERFICIE_TERRENO, [ACCESO], p)
    assert indicadores.superficie_verde_computable == pytest.approx(3600)
    assert indicadores.porcentaje_cesion == pytest.approx(100)


def test_un_lote_grande_es_util_y_se_cuenta_aparte():
    """Un lote de 24 × 30 m (720 m² > 600) no es un incumplimiento: es útil, y el indicador lo
    cuenta como lote grande (D47)."""
    lotes = [*diez_lotes()[:8], lote_frente_a_la_calle(96, 24, 30, 9)]
    indicadores = calcular(trazado(lotes))
    assert indicadores.cantidad_celdas == 9
    assert indicadores.cantidad_fracciones_no_conformes == 0
    assert indicadores.cantidad_lotes_grandes == 1


def test_el_libre_se_suma_aparte_y_no_cuenta_para_la_cesion():
    resultado = trazado([*diez_lotes(), libre(box(0, 36, 120, 40))], verdes=[box(0, -16, 30, -6)])
    indicadores = calcular(resultado)
    assert indicadores.superficie_espacio_verde == pytest.approx(300)
    assert indicadores.superficie_espacio_libre == pytest.approx(480)
    assert indicadores.porcentaje_cesion == pytest.approx(100 * 300 / 3600)
    assert indicadores.porcentaje_espacio_verde == pytest.approx(100 * 300 / 8640)


def test_una_fraccion_no_conforme_no_es_celda_util():
    resultado = trazado(diez_lotes())
    marcada = Incumplimiento(TipoIncumplimiento.FONDO_MINIMO, "M1-L10", "fondo", box(108, 6, 120, 36))
    indicadores = calcular(replace(resultado, incumplimientos=(marcada,)))
    assert indicadores.cantidad_celdas == 9
    assert indicadores.cantidad_fracciones_no_conformes == 1
    assert indicadores.superficie_aprovechable == pytest.approx(3240)
    # Sin el último lote (x = 114), la media de 6, 18, …, 102 es 54 m.
    assert indicadores.distancia_media_acceso == pytest.approx(54)


def test_sin_celdas_utiles_no_hay_distancia_media():
    indicadores = calcular(trazado([]))
    assert indicadores.distancia_media_acceso is None
    assert indicadores.porcentaje_cesion is None  # sin lotes no hay base para la cesión
