"""Ord. 8060, art. 48 (D50): «La dimensión del lado menor de cada manzana deberá ser de 42,00 m. como
mínimo. La dimensión del lado mayor no podrá exceder de 250,00 m. [...] si excediere los 200,00 m,
deberá proyectarse un pasaje peatonal».

- El lado menor de una manzana irregular es su ancho (el diámetro del mayor círculo inscripto, como
  el del lote y el del verde), y el mayor, el lado largo del rectángulo mínimo.
- En los cinco casos, toda manzana con lotes cumple los dos lados. El barrido de 96 terrenos lo
  exige también (`pytest -m barrido`, en test_particion.py).
- Una manzana que no alcanza el lado menor (una punta, un recorte) no se subdivide: es remanente,
  verde si cumple los criterios del verde y libre si no, aunque tenga forma de lote.
- Los trazados a mano que incumplen están en test_verificador.py.
"""

import pytest
from contorno import con_contorno
from shapely import LineString, Polygon, box

from motor_trazados import CeldaGenerada, MotorGeneracion, TipoCelda, TipoIncumplimiento
from motor_trazados.geometria import IndiceEjes
from motor_trazados.referencia import CASOS, solicitud_caso
from motor_trazados.remanentes import ClasificadorRemanentes
from motor_trazados.valores_referencia import PARAMETROS_LOTEO_REFERENCIA as P
from motor_trazados.verificador import alcanza_lado_menor, lado_mayor_manzana


@pytest.fixture(scope="module", params=sorted(CASOS))
def generado(request):
    s = solicitud_caso(request.param)
    return request.param, s, MotorGeneracion().generar(s)


def test_toda_manzana_con_lotes_cumple_el_art_48(generado):
    nombre, s, resultado = generado
    con_lotes = sorted({lote.indice_manzana for lote in resultado.lotes})
    for indice in con_lotes:
        manzana = resultado.manzanas[indice - 1]
        assert alcanza_lado_menor(manzana, s.parametros), (nombre, indice)
        assert lado_mayor_manzana(manzana) <= s.parametros.lado_maximo_sin_pasaje, (nombre, indice)
    tipos = {i.tipo for i in resultado.incumplimientos}
    assert not tipos & {TipoIncumplimiento.LADO_MENOR_MANZANA, TipoIncumplimiento.LADO_MAYOR_MANZANA}


def test_una_manzana_que_no_alcanza_el_lado_menor_no_tiene_lotes(generado):
    nombre, s, resultado = generado
    for indice, manzana in enumerate(resultado.manzanas, 1):
        if not alcanza_lado_menor(manzana, s.parametros):
            celdas = [c for c in resultado.celdas if c.indice_manzana == indice]
            assert celdas and all(c.tipo is not TipoCelda.LOTE for c in celdas), (nombre, indice)


def test_en_los_casos_irregulares_hay_puntas_sin_lotes():
    """Las esquinas agudas del irregular y del triángulo, y el recorte de la L, dejan manzanas que no
    alcanzan el lado menor (D50): son remanentes. La U ya no deja ninguna: con la calle de borde por
    lado, la calle de su entrante se alinea con la grilla y las manzanas de alrededor tienen dos fondos
    (D86). Con la calle de borde en todo el contorno dejaba sus recortes, como antes."""
    for nombre in ("irregular", "l", "u", "triangulo"):
        resultado = MotorGeneracion(asignar_espacios_verdes=False).generar(solicitud_caso(nombre))
        puntas = [m for m in resultado.manzanas if not alcanza_lado_menor(m, P)]
        assert bool(puntas) == (nombre != "u"), nombre
    resultado = MotorGeneracion(asignar_espacios_verdes=False).generar(con_contorno(solicitud_caso("u")))
    assert [m for m in resultado.manzanas if not alcanza_lado_menor(m, P)]


# --- La medida -----------------------------------------------------------------------------------


def test_en_un_rectangulo_los_lados_son_los_lados():
    manzana = box(0, 0, 111, 55.5)
    assert alcanza_lado_menor(manzana, P)
    assert lado_mayor_manzana(manzana) == pytest.approx(111)
    assert not alcanza_lado_menor(box(0, 0, 111, 41.98), P)
    assert alcanza_lado_menor(box(0, 0, 111, 41.995), P)  # una diferencia menor a 1 cm no cuenta


def test_en_un_triangulo_el_lado_menor_es_el_ancho_y_no_la_altura():
    """Un triángulo de 100 m de base y 45 m de altura: el rectángulo mínimo diría 45 m, pero en su
    parte más ancha mide unos 39 m (el doble del radio inscripto). No llega."""
    triangulo = Polygon([(0, 0), (100, 0), (50, 45)])
    assert not alcanza_lado_menor(triangulo, P)


def test_en_una_l_angosta_no_alcanza_aunque_el_rectangulo_minimo_sea_grande():
    """Una manzana en L de brazos de 30 m: el rectángulo mínimo mide 80 × 80, pero ningún círculo
    de 42 m entra en ella."""
    ele = box(0, 0, 80, 30).union(box(0, 0, 30, 80))
    assert not alcanza_lado_menor(ele, P)
    assert lado_mayor_manzana(ele) == pytest.approx(80)


# --- Las puntas: remanente verde o libre ------------------------------------------------------


def test_la_pieza_de_una_manzana_sin_lado_menor_es_verde_o_libre_aunque_tenga_forma_de_lote():
    """Dos manzanas de 30 m de fondo sobre una calle local (y = −6 a 6), que no alcanzan los 42 m:
    llegan al clasificador como piezas sin lotes (`MotorGeneracion._sin_lotes`). La de 36 × 30 m
    (1.080 m², 30 m de ancho y frente a la calle) es verde; la de 15 × 30 m (450 m²) tendría forma de
    lote, pero es libre."""
    from motor_trazados.motor import _sin_lotes
    from motor_trazados.red import RedCirculacion
    from trazados import LOCAL

    calle = box(-10, -6, 100, 6)
    red = RedCirculacion()
    red.agregar_tramo((-10, 0), (100, 0), None, LOCAL)
    ejes = IndiceEjes([LineString([(-10, 0), (100, 0)])])
    verde, libre = box(0, 6, 36, 36), box(50, 6, 65, 36)
    piezas = [_sin_lotes(verde, 1), _sin_lotes(libre, 2)]
    celdas = ClasificadorRemanentes().clasificar(piezas, calle, ejes, P)
    assert [(c.designacion, c.tipo) for c in celdas] == [
        ("M1-EV01", TipoCelda.ESPACIO_VERDE),
        ("M2-EL01", TipoCelda.ESPACIO_LIBRE),
    ]
    # La misma pieza de 15 × 30 m, como lote candidato, sí sería un lote.
    lote = CeldaGenerada(libre, TipoCelda.LOTE, 0.0, 0.0, 2, "M2-L01")
    (como_lote,) = ClasificadorRemanentes().clasificar([lote], calle, ejes, P)
    assert como_lote.tipo is TipoCelda.LOTE
