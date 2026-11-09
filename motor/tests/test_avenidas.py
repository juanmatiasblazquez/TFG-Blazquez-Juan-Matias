"""Ley 4146, art. 12 (D48): calles de 12 m con 6 m de calzada, y no menos del 20 % de la longitud
total de calles como avenidas de al menos 20 m.

- En los cinco casos de referencia se llega al 20 %, con las avenidas mínimas: sin cualquiera
  de ellas no se llega.
- En el rectangular, las avenidas son las calles de borde a las que abren los accesos (D50); las
  longitudinales y las transversales son locales.
- El triángulo de 24° del barrido, con la grilla a 15°, no llegaba: cualquier calle de borde o
  longitudinal más ancha deja los lotes sin el fondo mínimo, y las tres transversales no alcanzan.
  Llega sumando dos transversales (D53). Si ni así se llega (con un 60 % pedido), da el
  incumplimiento con su causa y su sugerencia.
- Sin una jerarquía de 20 m tampoco se llega, con otra causa.
- Con 0 % (la casilla «Exigir avenidas» desmarcada, D85), todas las calles son locales y la
  circulación baja en los cinco casos.

El barrido de 96 terrenos (`pytest -m barrido`, en test_particion.py) exige además el 20 %.
"""

from dataclasses import replace

import pytest
from contorno import con_contorno
from shapely import Point, Polygon
from shapely.affinity import translate

from motor_trazados import (
    CalleBorde,
    Estrategia,
    MotorGeneracion,
    PatronRed,
    SolicitudGeneracion,
    TipoIncumplimiento,
    TipoProyecto,
    jerarquias_en_uso,
)
from motor_trazados.generador_red import (
    BORDE,
    LONGITUDINAL,
    TRANSVERSAL,
    GeneradorRed,
    _Trazado,
    jerarquia_mayor,
    jerarquia_menor,
)
from motor_trazados.geometria import MarcoLocal, ajustar
from motor_trazados.referencia import CASOS, solicitud_caso
from motor_trazados.valores_referencia import JERARQUIAS_REFERENCIA, PARAMETROS_LOTEO_REFERENCIA as P
from motor_trazados.verificador import es_avenida, faltante_avenidas, porcentaje_avenidas

ORIGEN = (4_400_000.0, 6_510_000.0)


def en_el_marco(s):
    """El dominio y los accesos como los ve el generador: en el marco local del motor."""
    marco = MarcoLocal.para(s.terreno, s.estrategia.orientacion)
    return ajustar(marco.a_local(s.terreno)), [marco.a_local(a) for a in s.accesos]


def generada(s):
    dominio, accesos = en_el_marco(s)
    return GeneradorRed().generar_con_avenidas(dominio, accesos, s.estrategia, s.parametros, s.jerarquias)


@pytest.mark.parametrize("nombre", sorted(CASOS))
def test_los_casos_de_referencia_llegan_al_20_por_ciento(nombre):
    s = solicitud_caso(nombre)
    resultado = MotorGeneracion().generar(s)
    assert resultado.indicadores.porcentaje_avenidas >= 20 - 1e-6
    assert TipoIncumplimiento.PROPORCION_AVENIDAS not in {i.tipo for i in resultado.incumplimientos}
    assert TipoIncumplimiento.ANCHO_CALLE not in {i.tipo for i in resultado.incumplimientos}
    # Las avenidas son de la jerarquía mayor, y ninguna longitudinal hace falta.
    g = generada(s)
    assert g.motivo is None and g.avenidas
    assert all(tipo != LONGITUDINAL for tipo, _ in g.avenidas), g.avenidas
    # Llegan sin transversales de más: la regla de D53 no cambia los casos.
    assert g.transversales_de_mas == 0


@pytest.mark.parametrize("nombre", sorted(CASOS))
def test_las_avenidas_son_las_minimas(nombre):
    """Sin cualquiera de las avenidas elegidas, la red, trazada de nuevo, no llega al 20 %."""
    s = solicitud_caso(nombre)
    dominio, accesos = en_el_marco(s)
    g = generada(s)
    trazado = _Trazado(dominio, accesos, s.parametros, jerarquia_menor(s.jerarquias), jerarquia_mayor(s.jerarquias))
    assert not faltante_avenidas(g.red, s.parametros)
    for avenida in g.avenidas:
        sin_ella = trazado.intentar([c for c in g.avenidas if c != avenida])
        assert sin_ella is None or faltante_avenidas(sin_ella, s.parametros) > 0, (nombre, avenida)


def test_en_el_rectangular_son_las_calles_de_borde_de_los_accesos():
    """Con la calle de borde en todo el contorno (D50), A1 abre a la calle de borde del lado sur (464 m)
    y A2 a la del este (254 m): las dos son «calles de los accesos» y llegan juntas a 718 de 3.590 m,
    justo el 20 % (D48). Ninguna transversal ni longitudinal hace falta. Por lado, en
    test_calle_borde.py (D86)."""
    s = con_contorno(solicitud_caso("referencia"))
    g = generada(s)
    assert [tipo for tipo, _ in g.avenidas] == [BORDE, BORDE]
    _, accesos = en_el_marco(s)
    for clave in g.avenidas:
        tramos = [t for t in g.red.tramos() if es_avenida(t.jerarquia, P)]
        assert any(g.red.servido(a, tramos) for a in accesos), clave
    assert porcentaje_avenidas(g.red, P) == pytest.approx(20.0, abs=0.05)


def triangulo_a_15(**cambios):
    """El triángulo de 24° del barrido con la grilla a 15°, con el acceso en el medio del lado
    mayor y la calle de borde en todo el contorno: es el terreno con el que se armó D53 (D86)."""
    return SolicitudGeneracion(
        TipoProyecto.LOTEO,
        translate(Polygon([(0, 0), (600, 0), (100, 220)]), *ORIGEN),
        (Point(ORIGEN[0] + 300, ORIGEN[1]),),
        replace(P, **{"calle_borde": CalleBorde.CONTORNO, **cambios}),
        JERARQUIAS_REFERENCIA,
        Estrategia(PatronRed.GRILLA, 15.0, 7),
    )


def test_el_triangulo_a_15_llega_con_dos_transversales_de_mas():
    """El fondo común de sus cinco filas es de 25,08 m: ninguna calle de borde ni longitudinal
    admite los 8 m más de una avenida, y las tres transversales llegan al 16,2 % (77 lotes). Con
    una transversal más se llega al 19,2 %, y con dos, al 20,3 %, sin ningún incumplimiento (D53).
    Las cuadras, contadas con el ancho de la avenida, no bajan de 42 m. Son 60 lotes: 67 hasta que
    las puntas dejaron de computar para la cesión (D55)."""
    s = triangulo_a_15()
    dominio, accesos = en_el_marco(s)
    g = generada(s)
    assert g.motivo is None and g.transversales_de_mas == 2
    assert all(tipo == TRANSVERSAL for tipo, _ in g.avenidas), g.avenidas
    assert porcentaje_avenidas(g.red, P) == pytest.approx(20.34, abs=0.01)
    base = _Trazado(dominio, accesos, P, jerarquia_menor(s.jerarquias), jerarquia_mayor(s.jerarquias))
    con_dos = _Trazado(
        dominio, accesos, P, jerarquia_menor(s.jerarquias), jerarquia_mayor(s.jerarquias), transversales_de_mas=2
    )
    assert con_dos.n == base.n + 2 and con_dos.cuadra >= P.lado_minimo_manzana
    resultado = MotorGeneracion().generar(s)
    assert len(resultado.lotes) == 60
    assert resultado.indicadores.porcentaje_avenidas >= 20 - 1e-6
    assert not resultado.incumplimientos


def test_si_ni_con_transversales_de_mas_se_llega_da_la_causa():
    """Con un 60 % pedido, ni sumando transversales hasta cuadras de 42 m se llega: queda la red
    sin transversales de más (la de más lotes), con todas las avenidas que se pudieron, y el
    incumplimiento con su causa y su sugerencia (D48, D53). Son 73 lotes (77 hasta D55)."""
    s = triangulo_a_15(porcentaje_minimo_avenidas=60.0)
    g = generada(s)
    assert g.transversales_de_mas == 0
    assert g.avenidas and all(tipo not in (BORDE, LONGITUDINAL) for tipo, _ in g.avenidas)
    assert "fondo mínimo" in g.motivo[0] and "16,2 %" in g.motivo[0] and "cuadras de 42 m" in g.motivo[0]
    resultado = MotorGeneracion().generar(s)
    assert len(resultado.lotes) == 73
    (avenidas,) = [i for i in resultado.incumplimientos if i.tipo is TipoIncumplimiento.PROPORCION_AVENIDAS]
    assert avenidas.elemento == "red"
    assert "Causa:" in avenidas.detalle and "Sugerencia:" in avenidas.detalle and "orientación" in avenidas.detalle


def test_sin_una_jerarquia_de_20_m_no_hay_avenidas_y_la_causa_lo_dice():
    """Con la colectora de 18 m (veredas de 3 m), ninguna jerarquía es de avenida: la red queda
    como en D24 (las transversales con la mayor) y el art. 12 se marca."""
    s = solicitud_caso("referencia")
    angosta = replace(JERARQUIAS_REFERENCIA[0], ancho_vereda=3.0)
    assert not es_avenida(angosta, P)
    resultado = MotorGeneracion().generar(replace(s, jerarquias=(angosta, JERARQUIAS_REFERENCIA[1])))
    (avenidas,) = [i for i in resultado.incumplimientos if i.tipo is TipoIncumplimiento.PROPORCION_AVENIDAS]
    assert "Ninguna jerarquía de calle mide los 20 m de una avenida" in avenidas.detalle
    assert "18 m" in avenidas.detalle and "Sugerencia:" in avenidas.detalle
    assert resultado.indicadores.porcentaje_avenidas == 0


def test_sin_porcentaje_pedido_todas_las_calles_son_locales():
    s = solicitud_caso("referencia")
    sin_pedido = replace(s, parametros=replace(P, porcentaje_minimo_avenidas=0.0))
    g = generada(sin_pedido)
    assert g.avenidas == () and g.motivo is None
    assert {t.jerarquia for t in g.red.tramos()} == {JERARQUIAS_REFERENCIA[1]}


@pytest.mark.parametrize("nombre", sorted(CASOS))
def test_sin_avenidas_la_red_es_de_calle_unica_y_ocupa_menos(nombre):
    """La casilla «Exigir avenidas» desmarcada (D85): el generador usa solo las jerarquías que
    `jerarquias_en_uso` dice, la red no tiene incumplimientos de calle y la circulación baja."""
    s = solicitud_caso(nombre)
    sin = replace(s, parametros=replace(s.parametros, porcentaje_minimo_avenidas=0.0))
    con_avenidas, sin_avenidas = MotorGeneracion().generar(s), MotorGeneracion().generar(sin)
    for solicitud, resultado in ((s, con_avenidas), (sin, sin_avenidas)):
        en_uso = jerarquias_en_uso(solicitud.jerarquias, solicitud.parametros.porcentaje_minimo_avenidas)
        usables = {j for j, usa in zip(solicitud.jerarquias, en_uso, strict=True) if usa}
        assert {t.jerarquia for t in resultado.red.tramos()} <= usables
    tipos = {i.tipo for i in sin_avenidas.incumplimientos}
    assert TipoIncumplimiento.PROPORCION_AVENIDAS not in tipos and TipoIncumplimiento.ANCHO_CALLE not in tipos
    assert sin_avenidas.indicadores.porcentaje_avenidas == 0
    assert sin_avenidas.indicadores.porcentaje_circulacion < con_avenidas.indicadores.porcentaje_circulacion


def test_con_anchos_iguales_las_filas_son_de_dos_fondos_desde_la_calle_de_borde():
    """Las posiciones salen de los anchos (D48, D50): con todas las calles locales, las
    longitudinales del rectangular separan cuatro filas de dos fondos de 26,25 m, desde el borde
    interior de la calle de borde: (270 − 2 × 12 − 3 × 12) / 8."""
    s = solicitud_caso("referencia")
    dominio, accesos = en_el_marco(s)
    trazado = _Trazado(dominio, accesos, P, jerarquia_menor(s.jerarquias), jerarquia_mayor(s.jerarquias))
    red, calles = trazado.construir(lambda clave: False)
    _, miny, _, _ = dominio.bounds
    assert (trazado.filas, trazado.m) == (4, 3)
    fondo = trazado.fondo(trazado.jerarquias(lambda c: False, LONGITUDINAL, 3), trazado.alto)
    assert fondo == pytest.approx(26.25)
    ys = sorted({round(t.eje.coords[0][1], 6) for c in calles if c.tipo == LONGITUDINAL for t in c.tramos})
    assert ys == pytest.approx([miny + 12 + (2 * i + 2) * fondo + 12 * i + 6 for i in range(3)], abs=1e-6)
