"""Polígonos irregulares (D40): las restricciones duras se cumplen igual que en un rectángulo.

- Todo lote tiene frente sobre la red, medido sobre la geometría (D26).
- La red es conexa con todos los accesos, en el grafo y en la superficie de calle (D34).
- Lo que no es lote es un remanente bien clasificado: no es un lote válido (incumple algo o pasa
  la superficie máxima, D47) o es de una manzana que no alcanza el lado menor del art. 48 (D50), y
  es espacio verde exactamente cuando tiene la superficie, el ancho y el acceso de un verde (D41).
"""

import pytest
from shapely import Point, box

from motor_trazados import Estrategia, MotorGeneracion, PatronRed, TipoCelda, TipoIncumplimiento
from motor_trazados.generador_red import GeneradorRed
from motor_trazados.geometria import IndiceEjes, medir, poligonos, union_cobertura
from motor_trazados.referencia import CASOS, solicitud_caso
from motor_trazados.remanentes import es_espacio_verde
from motor_trazados.valores_referencia import JERARQUIAS_REFERENCIA, PARAMETROS_LOTEO_REFERENCIA as P
from motor_trazados.verificador import (
    alcanza_lado_menor,
    es_lote,
    es_lote_grande,
    incumplimientos_de_lote,
    verde_computable,
)
from test_particion import FORMAS, solicitud

def casos():
    """Las formas del barrido de la partición con la grilla a 20°, y los casos con nombre."""
    return [(nombre, solicitud(FORMAS[nombre], 20)) for nombre in sorted(FORMAS)] + [
        (nombre, solicitud_caso(nombre)) for nombre in sorted(CASOS) if nombre != "referencia"
    ]


@pytest.fixture(scope="module", params=casos(), ids=lambda caso: caso[0])
def generado(request):
    nombre, s = request.param
    return s, MotorGeneracion().generar(s)


def test_todo_lote_tiene_frente_sobre_la_red(generado):
    s, resultado = generado
    circulacion = union_cobertura(resultado.corredores)
    ejes = IndiceEjes([tramo.eje for tramo in resultado.red.tramos()])
    assert resultado.lotes
    for lote in resultado.lotes:
        medida = medir(lote.geometria, circulacion, ejes)
        assert medida.linea_frente is not None, lote.designacion
        assert circulacion.distance(medida.linea_frente) <= 0.01
    tipos = {i.tipo for i in resultado.incumplimientos}
    assert TipoIncumplimiento.SIN_FRENTE not in tipos


def test_la_red_es_conexa_con_todos_los_accesos(generado):
    s, resultado = generado
    assert resultado.red.es_conexa(s.accesos)
    circulacion = union_cobertura(resultado.corredores)
    assert len(poligonos(circulacion)) == 1
    assert all(circulacion.distance(acceso) <= 0.01 for acceso in s.accesos)
    assert TipoIncumplimiento.CONECTIVIDAD not in {i.tipo for i in resultado.incumplimientos}


def test_los_remanentes_estan_bien_clasificados(generado):
    s, resultado = generado
    circulacion = union_cobertura(resultado.corredores)
    ejes = IndiceEjes([tramo.eje for tramo in resultado.red.tramos()])
    for celda in resultado.celdas:
        medida = medir(celda.geometria, circulacion, ejes)
        if celda.tipo is TipoCelda.LOTE:
            assert es_lote(celda.geometria, medida, s.parametros), celda.designacion
        else:
            no_es_lote = incumplimientos_de_lote(celda.geometria, medida, s.parametros)
            manzana = resultado.manzanas[celda.indice_manzana - 1]
            sin_lotes = not alcanza_lado_menor(manzana, s.parametros)
            assert no_es_lote or es_lote_grande(celda.geometria, s.parametros) or sin_lotes, celda.designacion
            verde = es_espacio_verde(celda.geometria, circulacion, s.parametros)
            assert (celda.tipo is TipoCelda.ESPACIO_VERDE) == verde, celda.designacion


def test_los_indicadores_suman_el_verde_el_libre_y_la_cesion(generado):
    s, resultado = generado
    i = resultado.indicadores
    verde = sum(c.geometria.area for c in resultado.celdas if c.tipo is TipoCelda.ESPACIO_VERDE)
    libre = sum(c.geometria.area for c in resultado.celdas if c.tipo is TipoCelda.ESPACIO_LIBRE)
    lotes = sum(c.geometria.area for c in resultado.lotes)
    # La cesión cuenta solo el verde computable: sin las puntas del art. 48 (D55).
    computable = verde_computable(resultado.celdas, resultado.manzanas, s.parametros)
    assert i.superficie_espacio_verde == pytest.approx(verde)
    assert i.superficie_verde_computable == pytest.approx(computable)
    assert computable <= verde + 1e-6
    assert i.superficie_espacio_libre == pytest.approx(libre)
    assert i.porcentaje_cesion == pytest.approx(100 * computable / lotes)
    # Sobre la superficie disponible: el terreno menos las áreas reservadas (D61).
    disponible = s.terreno.area - sum(area.area for area in resultado.reservadas)
    assert i.porcentaje_espacio_verde == pytest.approx(100 * verde / disponible)
    cesion = TipoIncumplimiento.CESION_ESPACIO_VERDE in {x.tipo for x in resultado.incumplimientos}
    assert cesion == (i.porcentaje_cesion < s.parametros.porcentaje_espacio_verde)


def test_las_formas_de_la_verificacion_tienen_lotes_y_verde_y_casi_todas_libre():
    """Los casos se eligieron para que el portal muestre las tres clases (D41). Con la calle de
    borde (D50), las puntas de la L son verde y ya no tiene espacio libre; por lado (D86), la U
    tampoco: no deja puntas."""
    for nombre in ("irregular", "l", "u", "triangulo"):
        resultado = MotorGeneracion().generar(solicitud_caso(nombre))
        tipos = {c.tipo for c in resultado.celdas}
        libre = {TipoCelda.ESPACIO_LIBRE} if nombre not in ("l", "u") else set()
        assert tipos == {TipoCelda.LOTE, TipoCelda.ESPACIO_VERDE} | libre, nombre


def test_las_calles_del_brazo_que_ninguna_transversal_cruza_llegan_a_la_calle_de_borde():
    """Una L con el brazo al este, entre x = 440 y 560: ninguna transversal de la grilla cruza el
    brazo. Hasta el motor 0.6.0 sus calles quedaban sueltas y las unía una transversal de enlace
    (D40). Con la calle de borde (D50), toda calle de la grilla termina en ella: las del brazo no se
    podan y la red es conexa sin enlace."""
    dominio = box(0, 0, 560, 130).union(box(440, 0, 560, 270))
    acceso = Point(280, 0)
    red = GeneradorRed().generar(
        dominio, [acceso], Estrategia(PatronRed.GRILLA, 0.0, 1), P, JERARQUIAS_REFERENCIA
    )
    en_el_brazo = [t for t in red.tramos() if min(t.eje.coords[0][1], t.eje.coords[-1][1]) > 130]
    assert en_el_brazo, "las calles del brazo se podaron"
    assert red.es_conexa([acceso])
    assert not red.componentes_aisladas()


def test_el_terreno_de_la_entrante_queda_loteado(resultado_irregular):
    """En el caso irregular, el sector al norte de la entrante (antes encerrado) tiene lotes."""
    assert not [
        c for c in resultado_irregular.celdas if c.tipo is not TipoCelda.LOTE and c.geometria.area > 5000
    ]

