"""Lotes grandes (D47): un lote que pasa la superficie máxima no es un incumplimiento. Por cada uno,
en este orden:

1. se subdivide, si los lotes que resultan cumplen frente, fondo, superficie y forma, y ninguno
   pasa la máxima;
2. si no, con «menos lotes perdidos» es el primer candidato del asignador a espacio verde, si solo
   cumple los criterios del verde (D46). Con «más cercanía» compite como cualquier otra pieza
   (D51);
3. si tampoco, queda como lote grande: se informa en los indicadores, sin marca de incumplimiento.

Un caso armado a mano para cada camino, con los valores de referencia (superficie máxima 600 m²).
Una calle local de 12 m corre por y ∈ [−6, 6], con su eje en y = 0: toda pieza apoyada en y = 6 da
a la calle.
"""

from dataclasses import replace

from shapely import LineString, Point, Polygon, box

from motor_trazados import CeldaGenerada, CriterioEspacioVerde, MotorGeneracion, TipoCelda
from motor_trazados.asignador import AsignadorEspaciosVerdes
from motor_trazados.geometria import IndiceEjes, union_cobertura
from motor_trazados.indicadores import CalculadorIndicadores
from motor_trazados.red import RedCirculacion
from motor_trazados.remanentes import distancias_al_verde
from motor_trazados.subdivisores import SubdivisorLoteo
from motor_trazados.valores_referencia import PARAMETROS_LOTEO_REFERENCIA as P
from motor_trazados.verificador import VerificadorRestricciones, es_lote_grande
from trazados import LOCAL, P_TRAZADOS, lote_frente_a_la_calle, trazado

CALLE = box(-60, -6, 300, 6)
EJE = LineString([(-60, 0), (300, 0)])


def red() -> RedCirculacion:
    r = RedCirculacion()
    r.agregar_tramo(EJE.coords[0], EJE.coords[-1], None, LOCAL)
    return r


def lote(geometria: Polygon, numero: int = 1) -> CeldaGenerada:
    return CeldaGenerada(geometria, TipoCelda.LOTE, 0.0, 0.0, 1, f"M1-L{numero:02d}")


def subdividir_grandes(*geometrias):
    piezas = [lote(g, k) for k, g in enumerate(geometrias, 1)]
    return MotorGeneracion()._subdividir_grandes(SubdivisorLoteo(), piezas, CALLE, red(), P)


# --- Camino 1: se subdivide ---------------------------------------------------------------------


def test_un_lote_grande_que_admite_lotes_se_subdivide():
    """42 × 30 m = 1.260 m². En dos partes darían 630 m², que todavía pasan la máxima; en tres, 14
    × 30 = 420 m², que cumplen todo. Vale el menor k con todas las partes chicas. Solo sería un
    verde válido, pero subdividir va antes."""
    partes = subdividir_grandes(box(0, 6, 42, 36))
    assert [round(p.geometria.area, 6) for p in partes] == [420.0, 420.0, 420.0]
    assert union_cobertura([p.geometria for p in partes]).equals(box(0, 6, 42, 36))
    assert not any(es_lote_grande(p.geometria, P) for p in partes)


def test_un_lote_que_no_pasa_la_maxima_no_se_toca():
    (pieza,) = subdividir_grandes(box(0, 6, 20, 36))  # 600 m²: justo la máxima
    assert pieza.geometria.equals(box(0, 6, 20, 36))


# --- Camino 2: el asignador lo convierte primero en verde ---------------------------------------

# Una punta de 12 m de frente que se ensancha hacia atrás: 36 m de fondo (relación 3), 1.332 m² y
# 30,2 m de ancho útil. Es un lote, y es grande. Con 12 m de frente no admite dos lotes de 10.
PUNTA = Polygon([(0, 6), (12, 6), (12, 42), (-50, 42)])


def test_un_lote_grande_que_no_admite_lotes_queda_entero():
    (pieza,) = subdividir_grandes(PUNTA)
    assert pieza.geometria.equals(PUNTA)
    assert SubdivisorLoteo().redividir(PUNTA, CALLE, P) == []


def asignar_en_la_calle(criterio):
    """La punta y diez lotes de 12 × 36 m (432 m²) sobre la calle: 5.652 m² de lotes, sin verde.
    Faltan 565,2 m²."""
    lotes = [lote(PUNTA, 1)] + [lote(box(12 + 12 * k, 6, 24 + 12 * k, 42), k + 2) for k in range(10)]
    manzana = union_cobertura([c.geometria for c in lotes])
    p = replace(P, criterio_espacio_verde=criterio)
    asignacion = AsignadorEspaciosVerdes().asignar(lotes, [manzana], CALLE, red(), IndiceEjes([EJE]), p)
    assert asignacion.motivo is None
    return asignacion


def distancia_media(asignacion) -> float:
    lotes = [c.geometria for c in asignacion.celdas if c.tipo is TipoCelda.LOTE]
    verdes = [c.geometria for c in asignacion.celdas if c.tipo is TipoCelda.ESPACIO_VERDE]
    distancias = distancias_al_verde(lotes, verdes, CALLE, IndiceEjes([EJE]), red())
    return sum(distancias) / len(distancias)


def test_con_menos_lotes_el_asignador_convierte_primero_el_lote_grande():
    """Con «menos lotes perdidos» la punta va primero (D46) y alcanza sola: cuesta un lote, contra
    los tres de cualquier otra pieza."""
    asignacion = asignar_en_la_calle(CriterioEspacioVerde.MENOS_LOTES)
    (pieza,) = asignacion.piezas
    assert pieza.parcelas == ("M1-L01",) and pieza.base is None
    verdes = [c for c in asignacion.celdas if c.tipo is TipoCelda.ESPACIO_VERDE]
    assert len(verdes) == 1 and verdes[0].geometria.equals(PUNTA)
    assert sum(1 for c in asignacion.celdas if c.tipo is TipoCelda.LOTE) == 10


def test_con_mas_cercania_el_lote_grande_de_borde_no_se_elige_si_hay_una_candidata_mas_cercana():
    """Con «más cercanía» los lotes grandes no tienen prioridad (D51): compiten por cuánto acercan
    el verde a los lotes. La punta está en el extremo oeste y da a la calle con 12 m; los tres lotes
    del extremo este dan 36 m de frente a la calle y dejan a los lotes que quedan más cerca del
    verde. Gana esa pieza, aunque cueste tres lotes en lugar de uno, y la punta queda como lote
    grande."""
    cercania = asignar_en_la_calle(CriterioEspacioVerde.CERCANIA)
    menos_lotes = asignar_en_la_calle(CriterioEspacioVerde.MENOS_LOTES)
    (pieza,) = cercania.piezas
    assert "M1-L01" not in pieza.parcelas and len(pieza.parcelas) == 3
    assert any(c.tipo is TipoCelda.LOTE and c.geometria.equals(PUNTA) for c in cercania.celdas)
    assert distancia_media(cercania) < distancia_media(menos_lotes)


# --- Camino 3: queda como lote grande -----------------------------------------------------------


def test_un_lote_grande_que_no_admite_lotes_ni_es_verde_queda_como_lote_grande():
    """19 × 35 m = 665 m²: con 19 m de frente no admite dos lotes de 10, y con 665 m² no es un
    verde (1.000 m²). Queda entero, sin incumplimiento, y el indicador lo cuenta."""
    grande = box(0, 6, 19, 41)
    (pieza,) = subdividir_grandes(grande)
    assert pieza.geometria.equals(grande)
    # En el trazado de trazados.py: ocho lotes de 12 × 30 m y el grande al final de la calle.
    lotes = [lote_frente_a_la_calle(12 * k, 12, 30, k + 1) for k in range(8)]
    resultado = trazado([*lotes, lote(box(96, 6, 115, 41), 9)])
    assert VerificadorRestricciones().verificar(resultado, P_TRAZADOS, (Point(0, 0),)) == []
    indicadores = CalculadorIndicadores().calcular(resultado, 120 * 77, [Point(0, 0)], P)
    assert indicadores.cantidad_lotes_grandes == 1
    assert indicadores.cantidad_celdas == 9
