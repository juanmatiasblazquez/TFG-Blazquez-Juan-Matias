"""La calle de borde por lado (D86), contra la de todo el contorno (D50).

- La regla, lado por lado (`generador_red.limite_con_calle`): los lados casi paralelos a las filas, los
  de una entrante y los de un acceso llevan calle; los que cruzan la grilla de punta, no. Las áreas
  reservadas siempre (D59).
- `contorno` reproduce los números del motor 0.10.x en los siete casos: la casilla del portal vuelve
  exactamente a la D50.
- `por_lado`, el valor de referencia, en los siete casos: los lotes de la tabla de la D86, nunca menos
  que con el contorno, la partición cerrada, el art. 48, la red conexa y ningún incumplimiento.
- El rectangular por lado: el lado oeste no lleva calle, las calles de la grilla llegan al límite y las
  manzanas de ese lado no tienen esquina contra él.
- La U por lado: la calle de su entrante es una recta de la grilla, y no deja puntas.
"""

import math
from dataclasses import replace
from functools import lru_cache

import pytest
from contorno import con_contorno
from shapely import LineString, Point, Polygon, box

from motor_trazados import CalleBorde, MotorGeneracion, TipoIncumplimiento
from motor_trazados.generador_red import (
    BORDE,
    LONGITUDINAL,
    TRANSVERSAL,
    UMBRAL_PARALELO,
    _Trazado,
    jerarquia_mayor,
    jerarquia_menor,
    lados_entrantes,
    limite_con_calle,
)
from motor_trazados.geometria import TOLERANCIA, MarcoLocal, ajustar, lados, paralelos, union_cobertura
from motor_trazados.referencia import CASOS, solicitud_caso
from motor_trazados.valores_referencia import JERARQUIAS_REFERENCIA, PARAMETROS_LOTEO_REFERENCIA as P
from motor_trazados.verificador import alcanza_lado_menor
from particion import assert_particion

COLECTORA, LOCAL = JERARQUIAS_REFERENCIA
POR_LADO = CalleBorde.POR_LADO

# Los lotes de los siete casos (D86): con la calle de borde en todo el contorno, los del motor 0.10.x
# (D85), y por lado.
LOTES_CONTORNO = {
    "referencia": 261, "irregular": 116, "l": 119, "u": 195, "triangulo": 143, "reservada_centro": 228,
    "reservada_borde": 99,
}
LOTES_POR_LADO = {
    "referencia": 261, "irregular": 127, "l": 123, "u": 217, "triangulo": 143, "reservada_centro": 236,
    "reservada_borde": 100,
}


def con_calle(terreno, accesos=(), reservadas=()) -> list[LineString]:
    """Los lados del terreno con calle de borde por lado, como líneas."""
    return list(limite_con_calle(terreno, reservadas, POR_LADO, accesos).geoms)


def cubierto(linea: LineString, lineas: list[LineString]) -> bool:
    """La línea es uno de los lados con calle: sus puntas y su punto medio están sobre alguno."""
    puntos = (Point(linea.coords[0]), Point(linea.coords[-1]), linea.interpolate(0.5, normalized=True))
    return any(all(otra.distance(p) <= TOLERANCIA for p in puntos) for otra in lineas)


# --- La regla ------------------------------------------------------------------------------------


def test_el_valor_de_referencia_es_por_lado():
    assert P.calle_borde is POR_LADO
    assert UMBRAL_PARALELO == 45.0


def test_en_un_rectangulo_la_llevan_los_lados_paralelos_a_las_filas():
    """En el marco local las longitudinales son paralelas al eje x: llevan calle el sur y el norte; el
    este y el oeste cruzan la grilla de punta."""
    terreno = box(0, 0, 400, 200)
    lineas = con_calle(terreno)
    assert len(lineas) == 2
    assert all(paralelos(math.atan2(l.coords[-1][1] - l.coords[0][1], l.coords[-1][0] - l.coords[0][0]), 0.0) for l in lineas)
    assert limite_con_calle(terreno).equals(terreno.boundary)  # con todo el contorno, el límite entero


def test_un_lado_con_un_acceso_la_lleva_aunque_cruce_la_grilla():
    terreno = box(0, 0, 400, 200)
    oeste = LineString([(0, 0), (0, 200)])
    assert not cubierto(oeste, con_calle(terreno))
    assert cubierto(oeste, con_calle(terreno, accesos=(Point(0, 80),)))


@pytest.mark.parametrize(("angulo", "lleva"), [(0, True), (30, True), (45, True), (50, False), (80, False)])
def test_la_llevan_los_lados_a_45_grados_o_menos_de_las_filas(angulo, lleva):
    """Un trapecio con la base sobre el eje x y el lado este inclinado `angulo` respecto de las filas:
    la base y el techo la llevan siempre; el este, si está a 45° o menos."""
    alto = 200.0
    desplazamiento = alto / math.tan(math.radians(angulo)) if angulo else 0.0
    if angulo == 0:
        terreno = Polygon([(0, 0), (600, 0), (600, 1), (0, 1)])  # el lado este no importa: es de 1 m
        este = LineString([(0, 0), (600, 0)])
    else:
        terreno = Polygon([(0, 0), (300, 0), (300 + desplazamiento, alto), (0, alto)])
        este = LineString([(300, 0), (300 + desplazamiento, alto)])
    assert cubierto(este, con_calle(terreno)) is lleva


def test_los_lados_de_una_entrante_la_llevan():
    """La L: el codo (los dos lados fuera de la cápsula convexa) lleva calle aunque un lado cruce la
    grilla de punta; el extremo este del brazo sur, no."""
    terreno = box(0, 0, 400, 150).union(box(0, 0, 150, 350))
    entrantes = lados_entrantes(terreno)
    assert len(entrantes) == 2
    lineas = con_calle(terreno)
    assert all(cubierto(e, lineas) for e in entrantes)
    assert not cubierto(LineString([(400, 0), (400, 150)]), lineas)
    assert not cubierto(LineString([(0, 0), (0, 350)]), lineas)


def test_las_areas_reservadas_siempre_la_llevan():
    terreno = box(0, 0, 400, 200)
    area = box(100, 50, 160, 120)
    lineas = con_calle(terreno, reservadas=(area,))
    assert any(l.equals(area.exterior) for l in lineas)


# --- Los siete casos -------------------------------------------------------------------------------


@lru_cache(maxsize=None)
def generado(nombre: str, calle_borde: CalleBorde):
    s = solicitud_caso(nombre)
    s = replace(s, parametros=replace(s.parametros, calle_borde=calle_borde))
    return s, MotorGeneracion().generar(s)


@pytest.mark.parametrize("nombre", sorted(CASOS))
def test_con_todo_el_contorno_son_los_lotes_del_motor_anterior(nombre):
    """La casilla «Calle de borde en todo el contorno» vuelve a la D50: los mismos lotes que el motor
    0.10.x (la tabla de la D85)."""
    _, r = generado(nombre, CalleBorde.CONTORNO)
    assert len(r.lotes) == LOTES_CONTORNO[nombre]


@pytest.mark.parametrize("nombre", sorted(CASOS))
def test_por_lado_cumple_todo_y_no_pierde_lotes(nombre):
    s, r = generado(nombre, POR_LADO)
    assert len(r.lotes) == LOTES_POR_LADO[nombre]
    assert len(r.lotes) >= LOTES_CONTORNO[nombre]
    assert_particion(s, r)
    assert r.red.es_conexa(s.accesos) and not r.red.componentes_aisladas()
    assert r.incumplimientos == (), [(i.tipo.value, i.elemento, i.detalle) for i in r.incumplimientos]
    for indice in sorted({lote.indice_manzana for lote in r.lotes}):
        assert alcanza_lado_menor(r.manzanas[indice - 1], s.parametros), (nombre, indice)


def test_por_lado_gana_lotes_y_baja_la_circulacion_en_los_casos():
    """En los siete casos, por lado: 1.207 lotes contra 1.161 (+4 %), y la circulación nunca sube más
    que unas décimas (la del irregular, por la calle alineada de su entrante)."""
    total = sum(len(generado(n, POR_LADO)[1].lotes) for n in CASOS)
    assert total == sum(LOTES_POR_LADO.values()) == 1207
    assert sum(LOTES_CONTORNO.values()) == 1161
    for nombre in CASOS:
        circulacion = generado(nombre, POR_LADO)[1].indicadores.porcentaje_circulacion
        assert circulacion <= generado(nombre, CalleBorde.CONTORNO)[1].indicadores.porcentaje_circulacion + 0.5, nombre


# --- El rectangular -------------------------------------------------------------------------------


def test_en_el_rectangular_el_oeste_no_lleva_calle_y_las_calles_llegan_al_limite():
    """El lado oeste cruza la grilla de punta y no tiene acceso: ningún tramo corre junto a él, y las
    filas terminan contra él: las tres longitudinales y las calles de borde del sur y del norte llegan
    al límite. El este lleva la suya, por A2. La red mide 224 m menos que con todo el contorno (3.590)."""
    s, r = generado("referencia", POR_LADO)
    marco = MarcoLocal.para(s.terreno, s.estrategia.orientacion)
    minx, miny, maxx, maxy = ajustar(marco.a_local(s.terreno)).bounds
    oeste = LineString([(minx, miny), (minx, maxy)])
    este = LineString([(maxx, miny), (maxx, maxy)])

    def junto(lado, tramo) -> bool:
        eje = marco.a_local(tramo.eje)
        return all(abs(lado.distance(Point(p)) - tramo.jerarquia.ancho_total / 2) <= TOLERANCIA for p in eje.coords)

    assert not any(junto(oeste, t) for t in r.red.tramos())
    assert any(junto(este, t) for t in r.red.tramos())
    llegan = [t for t in r.red.tramos() if any(oeste.distance(Point(p)) <= TOLERANCIA for p in marco.a_local(t.eje).coords)]
    assert len(llegan) == 3 + 2
    assert r.red.longitud_total() == pytest.approx(3366, abs=0.5)


def test_en_el_rectangular_las_ochavas_son_las_de_dos_calles():
    """Toda esquina entre dos calles tiene ochava: 16 manzanas × 4, menos las 8 de las cuatro manzanas
    del oeste contra el límite, que no lleva calle."""
    s, r = generado("referencia", POR_LADO)
    orientacion = math.radians(s.estrategia.orientacion)
    circulacion = union_cobertura(r.corredores)
    ochavas = []
    for manzana in r.manzanas:
        for lado in lados(manzana, circulacion):
            en_grilla = paralelos(lado.direccion, orientacion) or paralelos(lado.direccion, orientacion + math.pi / 2)
            if lado.toca and not en_grilla:
                ochavas.append(lado.largo)
    assert len(ochavas) == 16 * 4 - 8
    assert all(any(abs(largo - j.radio_ochava) <= 0.01 for j in JERARQUIAS_REFERENCIA) for largo in ochavas)


# --- La U -----------------------------------------------------------------------------------------


def test_en_la_u_la_calle_de_la_entrante_es_una_recta_de_la_grilla():
    """Los dos lados de la entrante que cruzan la grilla de punta fuerzan una transversal sobre el eje
    de su calle, y el fondo de la entrante, una longitudinal (las filas entran): las manzanas de
    alrededor tienen dos fondos, y la U no deja puntas."""
    s = solicitud_caso("u")
    marco = MarcoLocal.para(s.terreno, s.estrategia.orientacion)
    dominio = ajustar(marco.a_local(s.terreno))
    accesos = [marco.a_local(a) for a in s.accesos]
    trazado = _Trazado(dominio, accesos, s.parametros, jerarquia_menor(s.jerarquias), jerarquia_mayor(s.jerarquias))
    assert [f.clave[0] for f in trazado.forzadas[TRANSVERSAL]] == [BORDE, BORDE]
    assert [f.clave[0] for f in trazado.forzadas[LONGITUDINAL]] == [BORDE]
    _, r = generado("u", POR_LADO)
    assert all(alcanza_lado_menor(m, s.parametros) for m in r.manzanas)
    contorno = MotorGeneracion().generar(con_contorno(s))
    assert not all(alcanza_lado_menor(m, s.parametros) for m in contorno.manzanas)


def test_sin_la_calle_de_borde_no_hay_incumplimiento_de_conectividad():
    """La red por lado se verifica igual que la del contorno (D34): grafo y superficie de calle."""
    for nombre in CASOS:
        _, r = generado(nombre, POR_LADO)
        assert TipoIncumplimiento.CONECTIVIDAD not in {i.tipo for i in r.incumplimientos}, nombre
