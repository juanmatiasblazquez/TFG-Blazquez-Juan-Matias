"""CU06 de punta a punta: grilla de loteo con calle de borde sobre un terreno rectangular (D24, D50).

El caso de referencia (fixture `resultado_referencia`) es un rectángulo de 480 × 270 m rotado
20°, con la grilla orientada igual. Hay casos chicos aparte para la orientación oblicua y el
error de conectividad. Los terrenos irregulares están en test_poligonos_irregulares.py, y el
invariante de la partición en test_particion.py.
"""

import math
from dataclasses import replace

import pytest
from shapely import Point, box
from shapely.affinity import rotate

from motor_trazados import (
    ErrorConectividad,
    Estrategia,
    MotorGeneracion,
    PatronRed,
    SolicitudGeneracion,
    TipoCelda,
    TipoIncumplimiento,
    TipoProyecto,
)
from motor_trazados.geometria import (
    IndiceEjes,
    MarcoLocal,
    TOLERANCIA,
    TOLERANCIA_AREA,
    angulo,
    interseccion,
    lados,
    medir,
    paralelos,
    poligonos,
    union_cobertura,
)
from motor_trazados.red import RedCirculacion
from motor_trazados.valores_referencia import JERARQUIAS_REFERENCIA, PARAMETROS_LOTEO_REFERENCIA as P
from motor_trazados.verificador import alcanza_lado_menor, es_lote, es_lote_grande, incumplimientos_de_lote
from particion import assert_particion

COLECTORA, LOCAL = JERARQUIAS_REFERENCIA


def solicitud(terreno, accesos, orientacion) -> SolicitudGeneracion:
    return SolicitudGeneracion(
        TipoProyecto.LOTEO, terreno, accesos, P, JERARQUIAS_REFERENCIA, Estrategia(PatronRed.GRILLA, orientacion, 7)
    )


# --- Caso de referencia ---------------------------------------------------------------------


def test_la_red_es_conexa_e_incluye_todos_los_accesos(referencia, resultado_referencia):
    assert resultado_referencia.red.es_conexa(referencia.accesos)
    assert not resultado_referencia.red.componentes_aisladas()


def test_no_se_pierde_superficie(referencia, resultado_referencia):
    assert_particion(referencia, resultado_referencia)


def test_sin_asignador_son_288_lotes(resultado_referencia_sin_asignador):
    """Frente, fondo, superficie, relación y ancho útil se cumplen en todos los lotes, y no
    queda ningún remanente. Sin el asignador, lo único que falta es la cesión de espacio verde.

    Con la calle de borde (D50) son 16 manzanas de dos fondos: 4 filas entre la calle de borde y
    tres longitudinales, y 4 columnas entre tres transversales, con 9 lotes por franja (288). La
    calle de borde del sur es avenida, así que el fondo común baja de 26,25 a 25,25 m. Hasta el
    motor 0.6.0 eran 286, con franjas de un fondo contra el límite que no cumplían el art. 48."""
    r = resultado_referencia_sin_asignador
    assert [i.tipo for i in r.incumplimientos] == [TipoIncumplimiento.CESION_ESPACIO_VERDE]
    assert len(r.manzanas) == 16
    assert len(r.celdas) == len(r.lotes) == 288
    assert r.indicadores.cantidad_celdas == 288
    assert r.indicadores.superficie_espacio_verde == 0
    assert r.indicadores.porcentaje_cesion == 0
    circulacion = union_cobertura(r.corredores)
    ejes = IndiceEjes([tramo.eje for tramo in r.red.tramos()])
    for celda in r.celdas:
        assert celda.frente >= P.frente_minimo - TOLERANCIA
        assert celda.fondo >= P.fondo_minimo - TOLERANCIA
        assert es_lote(celda.geometria, medir(celda.geometria, circulacion, ejes), P), celda.designacion


def test_con_asignador_cumple_todas_las_restricciones(resultado_referencia, resultado_referencia_sin_asignador):
    """El asignador completa la cesión convirtiendo parcelas enteras en verde (D44): la
    alternativa cumple todo y pierde solo los lotes que pasaron a ser plaza."""
    r = resultado_referencia
    assert r.cumple(), [(i.tipo, i.detalle) for i in r.incumplimientos]
    assert r.indicadores.porcentaje_cesion >= P.porcentaje_espacio_verde
    assert {c.tipo for c in r.celdas} == {TipoCelda.LOTE, TipoCelda.ESPACIO_VERDE}
    perdidos = len(resultado_referencia_sin_asignador.lotes) - len(r.lotes)
    verde = sum(g.area for g in r.espacios_verdes)
    # Todo el verde sale de lotes: lo que perdieron los lotes es exactamente el verde.
    lotes_antes = sum(c.geometria.area for c in resultado_referencia_sin_asignador.lotes)
    lotes_despues = sum(c.geometria.area for c in r.lotes)
    assert lotes_antes - lotes_despues == pytest.approx(verde, abs=0.01)
    assert 0 < perdidos < 288


def test_cada_corredor_corresponde_a_su_tramo(resultado_referencia):
    """`corredores[i]` es la calle de `red.tramos()[i]`: está pegada a su eje y no se aleja más
    que medio ancho más la ochava."""
    tramos = resultado_referencia.red.tramos()
    assert len(tramos) == len(resultado_referencia.corredores)
    for tramo, corredor in zip(tramos, resultado_referencia.corredores):
        if corredor.is_empty:
            continue
        alcance = tramo.jerarquia.ancho_total / 2 + COLECTORA.radio_ochava + TOLERANCIA
        assert corredor.within(tramo.eje.buffer(alcance)), f"el corredor no es el del tramo {tramo.origen}"
        assert corredor.distance(tramo.eje.interpolate(0.5, normalized=True)) <= TOLERANCIA


def test_las_avenidas_son_las_minimas_para_el_20_por_ciento(referencia_contorno, resultado_referencia_contorno):
    """Ley 4146, art. 12 (D48, D50): con la calle de borde en todo el contorno, son avenidas las calles
    de borde a las que abren los accesos, la del sur (A1) y la del este (A2): 718 m de 3.590 (20,0 %).
    Las longitudinales y las transversales son locales, y sin cualquiera de las dos no se llega. Por
    lado, en test_calle_borde.py (D86)."""
    referencia, resultado_referencia = referencia_contorno, resultado_referencia_contorno
    red = resultado_referencia.red
    avenidas = [t for t in red.tramos() if t.jerarquia == COLECTORA]
    terreno = referencia.terreno.exterior
    assert all(
        abs(terreno.distance(t.eje.interpolate(0.5, normalized=True)) - COLECTORA.ancho_total / 2) <= TOLERANCIA
        for t in avenidas
    ), "una avenida no es de la calle de borde"
    total = red.longitud_total()
    largo = math.fsum(t.longitud for t in avenidas)
    assert total == pytest.approx(3590) and largo == pytest.approx(718)
    assert resultado_referencia.indicadores.porcentaje_avenidas == pytest.approx(100 * largo / total)
    for lado in (464, 254):
        assert largo - lado < 0.2 * total, "sobra una avenida"


def test_hay_ochavas_en_todas_las_esquinas_de_las_manzanas(referencia_contorno, resultado_referencia_contorno):
    """Con la calle de borde en todo el contorno (D50), toda esquina de manzana da a dos calles: 16
    manzanas con 4 ochavas cada una, en diagonal respecto de la grilla. Miden 6 m donde llega una
    avenida (la mayor de las calles de la esquina) y 4 m entre dos locales. Por lado, en
    test_calle_borde.py (D86)."""
    referencia, resultado_referencia = referencia_contorno, resultado_referencia_contorno
    orientacion = math.radians(referencia.estrategia.orientacion)
    circulacion = union_cobertura(resultado_referencia.corredores)
    ochavas = []
    for manzana in resultado_referencia.manzanas:
        for lado in lados(manzana, circulacion):
            perpendicular = orientacion + math.pi / 2
            en_grilla = paralelos(lado.direccion, orientacion) or paralelos(lado.direccion, perpendicular)
            if lado.toca and not en_grilla:
                ochavas.append(lado.largo)
    assert len(ochavas) == 16 * 4
    radios = {COLECTORA.radio_ochava, LOCAL.radio_ochava}
    assert all(any(abs(largo - r) <= 0.01 for r in radios) for largo in ochavas), ochavas
    # Las esquinas sobre las avenidas del sur y del este: 4 manzanas × 2 en cada una, menos la
    # esquina sudeste, que es de las dos.
    assert sum(1 for largo in ochavas if abs(largo - COLECTORA.radio_ochava) <= 0.01) == 4 * 2 + 4 * 2 - 1


def test_los_accesos_abren_directo_a_la_calle_de_borde(referencia, resultado_referencia):
    """Los dos accesos están sobre el límite, a medio ancho del eje de la calle de borde: abren a
    ella sin conector (D50). Ningún tramo termina en un acceso."""
    red = resultado_referencia.red
    terreno = referencia.terreno.exterior
    for acceso in referencia.accesos:
        tramos = [t for t in red.tramos() if t.eje.distance(acceso) <= t.jerarquia.ancho_total / 2 + TOLERANCIA]
        assert tramos and red.servido(acceso)
        for tramo in tramos:
            medio = tramo.eje.interpolate(0.5, normalized=True)
            assert abs(terreno.distance(medio) - tramo.jerarquia.ancho_total / 2) <= TOLERANCIA
        assert all(math.dist(nodo, (acceso.x, acceso.y)) > TOLERANCIA for nodo in red.nodos())


def test_los_indicadores_son_coherentes(resultado_referencia):
    """Lotes útiles, calles, verde y libre son el terreno entero (es una partición)."""
    i = resultado_referencia.indicadores
    libre = 100 * i.superficie_espacio_libre / i.superficie_terreno
    total = i.porcentaje_aprovechamiento + i.porcentaje_circulacion + i.porcentaje_espacio_verde + libre
    assert total == pytest.approx(100, abs=0.01)
    assert i.longitud_red == pytest.approx(resultado_referencia.red.longitud_total())
    assert 0 < i.distancia_media_acceso < 480


# --- Otros terrenos --------------------------------------------------------------------------


def test_con_la_grilla_oblicua_las_fracciones_del_borde_quedan_como_remanentes():
    """Las fracciones del borde donde no entra un lote válido no se descartan ni se marcan como
    lotes: son remanentes (D41). Un remanente nunca es un lote válido: incumple algo o pasa la
    superficie máxima, como una plaza que el asignador armó con lotes (D44, D47). La excepción es una
    punta, una manzana entera que no alcanza el lado menor del art. 48: nunca se vuelve lote, aunque
    sirviera de uno (D50); con la calle de borde por lado, en una esquina sin calle puede pasar (D86)."""
    terreno = box(0, 0, 480, 270)
    s = solicitud(terreno, (Point(180, 0), Point(480, 135)), orientacion=35)
    resultado = MotorGeneracion().generar(s)
    assert_particion(s, resultado)
    remanentes = [c for c in resultado.celdas if c.tipo is not TipoCelda.LOTE]
    assert remanentes
    circulacion = union_cobertura(resultado.corredores)
    ejes = IndiceEjes([t.eje for t in resultado.red.tramos()])
    puntas = {k for k, m in enumerate(resultado.manzanas, 1) if not alcanza_lado_menor(m, P)}
    for remanente in remanentes:
        g = remanente.geometria
        if remanente.indice_manzana in puntas:
            continue
        assert incumplimientos_de_lote(g, medir(g, circulacion, ejes), P) or es_lote_grande(g, P)
    no_conformes = resultado.celdas_no_conformes()
    assert all(c.tipo is TipoCelda.LOTE for c in no_conformes)
    assert resultado.indicadores.cantidad_fracciones_no_conformes == len(no_conformes)


def test_sin_red_conexa_con_los_accesos_no_hay_alternativa():
    """La alternativa de la secuencia de la p. 43: si la red queda partida o un acceso no abre a
    ninguna calle, `ErrorConectividad`, con causa, sugerencia y la geometría de lo que falla (422
    en la API). Con la calle de borde (D50), todo acceso abre a ella y la grilla se une al anillo:
    la regla se prueba con una red armada a mano."""
    red = RedCirculacion()
    red.agregar_tramo((0, 0), (100, 0), None, LOCAL)
    red.agregar_tramo((0, 50), (100, 50), None, LOCAL)
    marco = MarcoLocal((0.0, 0.0), 0.0)
    with pytest.raises(ErrorConectividad) as error:
        MotorGeneracion()._exigir_red_conexa(red, [Point(0, 0)], marco)
    assert "partida" in error.value.causa and "orientación" in error.value.sugerencia
    assert error.value.geometria is not None and not error.value.geometria.is_empty
    with pytest.raises(ErrorConectividad) as error:
        MotorGeneracion()._exigir_red_conexa(red, [Point(50, 25)], marco)
    assert "A1" in error.value.causa


def test_con_la_calle_de_borde_un_acceso_en_la_esquina_ya_no_parte_la_red():
    """Hasta el motor 0.6.0, con la grilla a 40°, el acceso a 2 m de la esquina sudoeste se unía
    a un pedazo de calle de la esquina que no cruzaba ninguna transversal, y la red quedaba en dos
    partes (ErrorConectividad). Con la calle de borde, los dos accesos abren a ella (D50)."""
    s = solicitud(box(0, 0, 480, 270), (Point(2, 0), Point(478, 0)), orientacion=40)
    resultado = MotorGeneracion().generar(s)
    assert resultado.red.es_conexa(s.accesos)
    assert_particion(s, resultado)


@pytest.mark.parametrize(
    ("orientacion", "corredor"), [(2, "partido"), (77, "vacío"), (140, "partido"), (164, "vacío")]
)
def test_un_corredor_vacio_o_partido_no_corta_la_calle(referencia_contorno, orientacion, corredor):
    """Con la grilla oblicua, el corredor de un tramo puede quedar vacío (entero dentro de un
    cruce) o partido. Lo que le falta es calle del tramo de mayor jerarquía que lo cruza: el
    grafo y la superficie de calle dicen lo mismo, y no hay incumplimiento de conectividad
    (D34). Las orientaciones salen de un barrido de 0° a 179°: con la red del art. 12, la de 147°
    pasó a 140° (D48), y con la calle de borde en todo el contorno, la de 7° a 2° y la de 161° a 164°
    (D50). Se prueban con ella (D86)."""
    s = replace(referencia_contorno, estrategia=replace(referencia_contorno.estrategia, orientacion=float(orientacion)))
    resultado = MotorGeneracion().generar(s)
    partes = [len(poligonos(c)) for c in resultado.corredores]
    assert (0 in partes) if corredor == "vacío" else any(n > 1 for n in partes)

    circulacion = union_cobertura(resultado.corredores)
    assert len(resultado.red.componentes()) == 1 and len(poligonos(circulacion)) == 1
    cubierta = circulacion.buffer(TOLERANCIA)
    for tramo, n in zip(resultado.red.tramos(), partes, strict=True):
        if n != 1:
            franja = interseccion(tramo.eje.buffer(tramo.jerarquia.ancho_total / 2, cap_style="flat"), s.terreno)
            assert cubierta.covers(tramo.eje)
            assert franja.difference(cubierta).area < TOLERANCIA_AREA
    assert TipoIncumplimiento.CONECTIVIDAD not in {i.tipo for i in resultado.incumplimientos}


def test_un_terreno_rotado_90_grados_da_el_mismo_loteo():
    """Rotar terreno, accesos y orientación juntos no cambia la cantidad de lotes ni de calles."""
    base = solicitud(box(0, 0, 480, 270), (Point(180, 0), Point(480, 168.75)), orientacion=0)
    girada = solicitud(
        rotate(base.terreno, 90, origin=(0, 0)),
        tuple(rotate(a, 90, origin=(0, 0)) for a in base.accesos),
        orientacion=90,
    )
    r1, r2 = MotorGeneracion().generar(base), MotorGeneracion().generar(girada)
    assert len(r1.celdas) == len(r2.celdas)
    assert len(r1.red.tramos()) == len(r2.red.tramos())
    assert r1.indicadores.superficie_aprovechable == pytest.approx(r2.indicadores.superficie_aprovechable, abs=0.01)
