"""CU07: el verificador, probado aparte con trazados armados a mano (trazados.py).

Cada prueba arma un trazado que incumple UNA restricción a propósito y exige exactamente ese
incumplimiento. Un trazado correcto no da ninguno: un verificador que siempre aprueba, o que
siempre rechaza, no pasa estas pruebas. Los parámetros son los de referencia, salvo cuando
hay que aislar una restricción de las demás. La calle de los trazados es local, así que no piden
avenidas (`P_TRAZADOS`): el art. 12 de la Ley 4146 tiene sus propios trazados (D48).
"""

from dataclasses import replace

from shapely import Point, Polygon, box

from motor_trazados import JerarquiaCorredor, TipoIncumplimiento as T
from motor_trazados.red import RedCirculacion
from motor_trazados.geometria import IndiceEjes, medir, union
from trazados import libre
from motor_trazados.verificador import VerificadorRestricciones
from trazados import ACCESO, COLECTORA, LOCAL, P_TRAZADOS as P, lote, lote_frente_a_la_calle, red_simple, trazado


def verificar(resultado, parametros=P, accesos=(ACCESO,)):
    return [(i.tipo, i.elemento) for i in VerificadorRestricciones().verificar(resultado, parametros, accesos)]


def test_un_trazado_correcto_no_tiene_incumplimientos():
    # Diez lotes de 12 × 30 m: 360 m², relación 2,5, con el verde de la cesión.
    lotes = [lote_frente_a_la_calle(12 * k, 12, 30, k + 1) for k in range(10)]
    assert verificar(trazado(lotes)) == []


def test_red_partida_en_dos():
    red = red_simple()
    red.agregar_tramo((0, 100), (50, 100), None, LOCAL)
    assert verificar(trazado([lote_frente_a_la_calle(0, 12, 30)], red=red)) == [(T.CONECTIVIDAD, "red")]


def test_acceso_que_no_abre_a_ninguna_calle():
    accesos = (ACCESO, Point(60, 80))
    assert verificar(trazado([lote_frente_a_la_calle(0, 12, 30)]), accesos=accesos) == [(T.CONECTIVIDAD, "A2")]


def test_grafo_conexo_con_la_calle_cortada():
    """El grafo es un solo tramo, pero su calle tiene un corte de 20 m: la red no es conexa
    en el terreno (D34)."""
    cortada = (box(0, -6, 50, 6), box(70, -6, 120, 6))
    assert verificar(trazado([lote_frente_a_la_calle(0, 12, 30)], corredores=cortada)) == [(T.CONECTIVIDAD, "red")]


def test_acceso_sobre_el_eje_pero_fuera_de_la_calle():
    # El eje llega hasta el acceso, en (0, 0), pero la calle empieza 10 m más allá.
    corredor = (box(10, -6, 120, 6),)
    assert verificar(trazado([lote_frente_a_la_calle(12, 12, 30)], corredores=corredor)) == [(T.CONECTIVIDAD, "A1")]


def test_lote_sin_frente():
    lejos = lote(box(0, 50, 12, 80))
    assert verificar(trazado([lejos])) == [(T.SIN_FRENTE, "M1-L01")]


# Para aislar el frente, se relajan la relación fondo/frente y el ancho útil (un lote de 8 m de
# frente tiene 8 m de ancho útil).
SOLO_FRENTE = replace(P, relacion_fondo_frente_max=10, ancho_minimo_lote=1)


def test_frente_menor_al_minimo():
    # 8 × 32 m = 256 m²: solo falla el frente.
    parametros = SOLO_FRENTE
    assert verificar(trazado([lote_frente_a_la_calle(0, 8, 32)]), parametros) == [(T.FRENTE_MINIMO, "M1-L01")]


def test_fondo_menor_al_minimo():
    assert verificar(trazado([lote_frente_a_la_calle(0, 20, 20)])) == [(T.FONDO_MINIMO, "M1-L01")]


def test_superficie_menor_a_la_minima():
    parametros = replace(P, superficie_minima=400)
    assert verificar(trazado([lote_frente_a_la_calle(0, 12, 30)]), parametros) == [(T.SUPERFICIE_MINIMA, "M1-L01")]


def test_un_lote_que_pasa_la_superficie_maxima_no_incumple():
    """24 × 30 m = 720 m² > 600: es un lote grande, que se informa en los indicadores, no un
    incumplimiento (D47). La máxima es un criterio de diseño, no una norma."""
    assert verificar(trazado([lote_frente_a_la_calle(0, 24, 30)])) == []
    assert "superficie_maxima" not in {t.value for t in T}


def test_relacion_fondo_frente_mayor_a_la_maxima():
    # 10 × 40 m: fondo/frente = 4 > 3.
    assert verificar(trazado([lote_frente_a_la_calle(0, 10, 40)])) == [(T.RELACION_FONDO_FRENTE, "M1-L01")]


def test_ancho_util_menor_al_minimo():
    """Una L de brazos de 6 m sobre la calle (D43): 30 m de frente, 30 de fondo y 324 m², con la
    relación 1. Cumple todo, salvo que en ningún lugar entra un círculo de 10 m."""
    en_l = lote(box(0, 6, 30, 12).union(box(0, 6, 6, 36)))
    assert verificar(trazado([en_l])) == [(T.ANCHO_UTIL, "M1-L01")]


def test_cesion_de_espacio_verde_insuficiente():
    lotes = [lote_frente_a_la_calle(12 * k, 12, 30, k + 1) for k in range(10)]
    # 10 % de 3.600 m² de lotes = 360 m²; con 300 m² de verde no alcanza.
    assert verificar(trazado(lotes, verdes=[box(0, -16, 20, -6)])) == [(T.CESION_ESPACIO_VERDE, "terreno")]
    assert verificar(trazado(lotes, verdes=[box(0, -18, 30, -6)])) == []


def test_la_cesion_cuenta_el_verde_y_no_el_libre():
    """El espacio libre no computa para la cesión (D41): 300 m² de verde más 600 de libre no
    alcanzan los 360 m² exigidos."""
    lotes = [lote_frente_a_la_calle(12 * k, 12, 30, k + 1) for k in range(10)]
    con_libre = trazado([*lotes, libre(box(30, -36, 50, -6))], verdes=[box(0, -16, 20, -6)])
    assert verificar(con_libre) == [(T.CESION_ESPACIO_VERDE, "terreno")]


def test_el_contorno_de_la_cesion_es_solo_el_borde_exterior():
    """Aunque las piezas dejen un hueco, el incumplimiento de la cesión se dibuja con el borde
    exterior: los anillos interiores eran las líneas rojas sueltas del portal (D39)."""
    lotes = [lote_frente_a_la_calle(12 * k, 12, 30, k + 1) for k in range(10)]
    con_hueco = replace(trazado(lotes, verdes=[]), manzanas=(box(0, 6, 120, 36).difference(box(50, 20, 51, 21)),))
    (cesion,) = VerificadorRestricciones().verificar(con_hueco, P, (ACCESO,))
    assert cesion.tipo is T.CESION_ESPACIO_VERDE
    assert cesion.geometria.geom_type == "MultiLineString" and len(cesion.geometria.geoms) == 1


def test_un_remanente_no_se_verifica_como_lote():
    """Un espacio libre de 6 × 10 m no incumple el frente ni la superficie: no es un lote."""
    lotes = [lote_frente_a_la_calle(12 * k, 12, 30, k + 1) for k in range(10)]
    assert verificar(trazado([*lotes, libre(box(0, 40, 6, 50))])) == []


def test_mide_la_geometria_y_no_confia_en_lo_que_declara_la_celda():
    # La celda dice tener 12 m de frente, pero su geometría tiene 8.
    mentirosa = lote(box(0, 6, 8, 38), frente=12.0, fondo=32.0)
    parametros = SOLO_FRENTE
    assert verificar(trazado([mentirosa]), parametros) == [(T.FRENTE_MINIMO, "M1-L01")]


def test_una_diferencia_menor_a_un_centimetro_no_es_incumplimiento():
    parametros = SOLO_FRENTE
    assert verificar(trazado([lote_frente_a_la_calle(0, 9.995, 32)]), parametros) == []
    assert verificar(trazado([lote_frente_a_la_calle(0, 9.98, 32)]), parametros) == [(T.FRENTE_MINIMO, "M1-L01")]


# --- Ley 4146, art. 12 (D48) -------------------------------------------------------------------

DIEZ_LOTES = [lote_frente_a_la_calle(12 * k, 12, 30, k + 1) for k in range(10)]
CON_AVENIDAS = replace(P, porcentaje_minimo_avenidas=20.0)


def red_con_avenida(largo_avenida: float):
    """La local de 120 m y, a continuación, una colectora de 20 m (una avenida)."""
    red = red_simple()
    red.agregar_tramo((120, 0), (120 + largo_avenida, 0), None, COLECTORA)
    return red


def test_sin_avenidas_no_se_cumple_la_proporcion_del_art_12():
    """La única calle es una local de 12 m: 0 % de avenidas, y se piden 20 %."""
    assert verificar(trazado(DIEZ_LOTES), CON_AVENIDAS) == [(T.PROPORCION_AVENIDAS, "red")]


def test_la_proporcion_de_avenidas_se_cumple_justo_en_el_20_por_ciento():
    """120 m de local más 30 m de avenida: 30 / 150 = 20 %. Con 29 m, 29 / 149 = 19,5 %."""
    assert verificar(trazado(DIEZ_LOTES, red=red_con_avenida(30)), CON_AVENIDAS) == []
    assert verificar(trazado(DIEZ_LOTES, red=red_con_avenida(29)), CON_AVENIDAS) == [(T.PROPORCION_AVENIDAS, "red")]


def test_el_incumplimiento_del_art_12_lleva_la_causa_y_la_sugerencia_del_generador():
    motivo = ("Las calles que pueden ser avenidas llegan al 0 %.", "Probá otra orientación.")
    (avenidas,) = VerificadorRestricciones().verificar(trazado(DIEZ_LOTES), CON_AVENIDAS, (ACCESO,), None, motivo)
    assert avenidas.tipo is T.PROPORCION_AVENIDAS
    assert "Causa: Las calles que pueden ser avenidas" in avenidas.detalle
    assert "Sugerencia: Probá otra orientación." in avenidas.detalle


def test_una_calle_de_menos_de_12_m_o_con_menos_de_6_m_de_calzada_incumple():
    """Una jerarquía de 5 m de calzada y 10 m en total: incumple los dos mínimos del art. 12, y se
    informa una vez, con sus ejes."""
    angosta = JerarquiaCorredor("Angosta", 2, ancho_calzada=5.0, ancho_vereda=2.5, radio_ochava=4.0)
    red = RedCirculacion()
    red.agregar_tramo((0, 0), (120, 0), None, angosta)
    (incumplimiento,) = VerificadorRestricciones().verificar(trazado(DIEZ_LOTES, red=red), P, (ACCESO,))
    assert (incumplimiento.tipo, incumplimiento.elemento) == (T.ANCHO_CALLE, "red")
    assert "10,00 m de ancho < 12,00 m" in incumplimiento.detalle and "calzada de 5,00 m < 6,00 m" in incumplimiento.detalle
    # La local de referencia (7 m de calzada y 12 m) los cumple.
    assert verificar(trazado(DIEZ_LOTES)) == []


def esquina_con_ochava(ancho: float):
    """Un lote de `ancho` × 30 m en la esquina de la local (eje x) y una colectora (eje y,
    x = −10), con la ochava de 6 m: el trazado, y el mismo lote a mitad de cuadra."""
    red = red_simple()
    red.agregar_tramo((-10, -50), (-10, 0), None, COLECTORA)
    red.agregar_tramo((-10, 0), (-10, 50), None, COLECTORA)
    red.agregar_tramo((-10, 0), (0, 0), None, LOCAL)
    cateto = 6 / 2**0.5
    esquina = Polygon([(0, 6 + cateto), (cateto, 6), (ancho, 6), (ancho, 36), (0, 36)])
    corredores = (box(0, -6, 120, 6), box(-20, -50, 0, 50), Polygon([(0, 6), (cateto, 6), (0, 6 + cateto)]))
    return trazado([lote(esquina)], red=red, corredores=corredores), trazado([lote_frente_a_la_calle(40, ancho, 30)])


def test_un_lote_en_esquina_necesita_un_20_por_ciento_mas_de_frente():
    """Ord. 8060, art. 54 (D49): «Las parcelas esquinas deberán incrementar la medida de su frente
    mínimo en un 20%». Con 10 m de mínimo, la esquina necesita 12: un lote de 11 × 30 m (relación
    2,7, que cumple) incumple en la esquina y cumple a mitad de cuadra."""
    en_esquina, a_mitad = esquina_con_ochava(11)
    (incumplimiento,) = VerificadorRestricciones().verificar(en_esquina, P, (ACCESO,))
    assert (incumplimiento.tipo, incumplimiento.elemento) == (T.FRENTE_MINIMO, "M1-L01")
    assert "mínimo en esquina 12,00 m (Ord. 8060, art. 54)" in incumplimiento.detalle
    assert verificar(a_mitad) == []
    # Con 12 m la esquina cumple, y sin el incremento (loteos rurales, Dec. 737-D-86) también la de 11.
    assert verificar(esquina_con_ochava(12)[0]) == []
    assert verificar(en_esquina, replace(P, porcentaje_incremento_esquina=0)) == []


def test_en_la_esquina_el_frente_se_mide_hasta_el_vertice_y_es_el_lado_angosto():
    """Lote en la esquina de una local (eje x) y una colectora (eje y, x = −10) con ochava.

    El lote mide 12 × 30 m. La ochava (línea de 6 m a 45°, catetos de 4,24 m) le saca la
    esquina, pero el frente se mide hasta el vértice teórico: 12 m. Como tiene dos frentes, se
    toma el que deja el mayor fondo (el lado angosto), así que el fondo es 30 m y cumple.
    """
    red = red_simple()
    red.agregar_tramo((-10, -50), (-10, 0), None, COLECTORA)
    red.agregar_tramo((-10, 0), (-10, 50), None, COLECTORA)
    red.agregar_tramo((-10, 0), (0, 0), None, LOCAL)
    cateto = 6 / 2**0.5
    esquina = Polygon([(0, 6 + cateto), (cateto, 6), (12, 6), (12, 36), (0, 36)])
    corredores = (box(0, -6, 120, 6), box(-20, -50, 0, 50), Polygon([(0, 6), (cateto, 6), (0, 6 + cateto)]))
    assert verificar(trazado([lote(esquina)], red=red, corredores=corredores)) == []
    medida = medir(esquina, union(corredores), IndiceEjes([t.eje for t in red.tramos()]))
    assert abs(medida.frente - 12) < 1e-6
    assert abs(medida.fondo - 30) < 1e-6


# --- Ord. 8060, art. 48 (D50): los lados de la manzana --------------------------------------------

P48 = replace(P, lado_minimo_manzana=42.0)


def manzana_sobre_una_calle(largo: float, fondo: float, fondo_lotes: float = 30.0):
    """Una manzana de `largo` × `fondo` m al norte de una calle local del mismo largo, con lotes de
    12 m de frente y `fondo_lotes` de fondo a lo largo de la calle, y al sur un verde de 44 m de
    fondo, que es su propia manzana y cubre la cesión: con menos de 42 m sería una punta y no
    computaría (D55)."""
    from motor_trazados import ResultadoGeneracion
    from trazados import verde

    red = RedCirculacion()
    red.agregar_tramo((0, 0), (largo, 0), None, LOCAL)
    lotes = [lote(box(12 * k, 6, 12 * k + 12, 6 + fondo_lotes), k + 1) for k in range(int(largo // 12))]
    manzana = box(0, 6, largo, 6 + fondo)
    plaza = replace(verde(box(0, -50, largo, -6)), indice_manzana=2, designacion="M2-EV01")
    return ResultadoGeneracion(
        red=red, corredores=(box(0, -6, largo, 6),), manzanas=(manzana, plaza.geometria), celdas=(*lotes, plaza)
    )


def test_una_manzana_con_lotes_de_menos_de_42_m_incumple_el_lado_menor():
    """La franja de borde de la grilla hasta el motor 0.6.0: 27,75 m de fondo, con lotes que cumplen
    todo. La manzana no alcanza el lado menor."""
    resultado = manzana_sobre_una_calle(120, 27.75, fondo_lotes=27.75)
    (incumplimiento,) = VerificadorRestricciones().verificar(resultado, P48, (ACCESO,))
    assert (incumplimiento.tipo, incumplimiento.elemento) == (T.LADO_MENOR_MANZANA, "M1")
    assert incumplimiento.detalle == "lado menor 27,75 m < mínimo 42,00 m (Ord. 8060, art. 48)"


def test_una_manzana_de_mas_de_200_m_necesita_un_pasaje_peatonal():
    (incumplimiento,) = VerificadorRestricciones().verificar(manzana_sobre_una_calle(220, 60), P48, (ACCESO,))
    assert (incumplimiento.tipo, incumplimiento.elemento) == (T.LADO_MAYOR_MANZANA, "M1")
    assert "220,00 m > 200,00 m" in incumplimiento.detalle and "pasaje peatonal" in incumplimiento.detalle


def test_una_manzana_de_mas_de_250_m_pasa_el_maximo():
    (incumplimiento,) = VerificadorRestricciones().verificar(manzana_sobre_una_calle(264, 60), P48, (ACCESO,))
    assert (incumplimiento.tipo, incumplimiento.elemento) == (T.LADO_MAYOR_MANZANA, "M1")
    assert "264,00 m > máximo 250,00 m (Ord. 8060, art. 48)" == incumplimiento.detalle.replace("lado mayor ", "")


def test_una_manzana_de_42_por_200_m_cumple():
    assert verificar(manzana_sobre_una_calle(200, 42), P48) == []


def test_una_manzana_sin_lotes_no_se_verifica_y_su_verde_no_computa():
    """Una punta de 27,75 m de fondo que quedó entera como verde (D50): no es una manzana de lotes,
    así que no se verifica el art. 48. Con «más cercanía», su verde no computa para la cesión (D55,
    D58): con esa punta como único verde, la cesión no se cumple."""
    from motor_trazados import ResultadoGeneracion
    from trazados import verde

    lotes = [lote_frente_a_la_calle(12 * k, 12, 30, k + 1) for k in range(10)]
    punta = replace(verde(box(0, -33.75, 120, -6)), indice_manzana=2, designacion="M2-EV01")
    resultado = ResultadoGeneracion(
        red=red_simple(),
        corredores=(box(0, -6, 120, 6),),
        manzanas=(box(0, 6, 120, 56), punta.geometria),
        celdas=(*lotes, punta),
    )
    assert verificar(resultado, P48) == [(T.CESION_ESPACIO_VERDE, "terreno")]
    (cesion,) = VerificadorRestricciones().verificar(resultado, P48, (ACCESO,))
    assert cesion.detalle.startswith("espacio verde computable 0,00 m² < 10,00 %")


def test_con_menos_lotes_el_verde_de_una_punta_computa():
    """La misma punta con el criterio «menos lotes»: computa para la cesión y la cubre (D58). Con
    «más cercanía», el de referencia, no computa (la prueba anterior)."""
    from motor_trazados import CriterioEspacioVerde, ResultadoGeneracion
    from trazados import verde

    lotes = [lote_frente_a_la_calle(12 * k, 12, 30, k + 1) for k in range(10)]
    punta = replace(verde(box(0, -33.75, 120, -6)), indice_manzana=2, designacion="M2-EV01")
    resultado = ResultadoGeneracion(
        red=red_simple(),
        corredores=(box(0, -6, 120, 6),),
        manzanas=(box(0, 6, 120, 56), punta.geometria),
        celdas=(*lotes, punta),
    )
    assert verificar(resultado, replace(P48, criterio_espacio_verde=CriterioEspacioVerde.MENOS_LOTES)) == []
