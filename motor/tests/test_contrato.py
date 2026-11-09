"""El contrato del motor (D22): tipos, validación por campo, qué terrenos acepta y lo que
todavía no se implementa."""

from dataclasses import fields, replace

import pytest
from shapely import Point, Polygon, box
from shapely.affinity import rotate

from motor_trazados import (
    CriterioEspacioVerde,
    ElementosFijados,
    JerarquiaCorredor,
    MotorGeneracion,
    NoImplementado,
    ParametrosEstacionamiento,
    ParametrosLoteo,
    PatronRed,
    SentidoCirculacion,
    SolicitudGeneracion,
    SolicitudInvalida,
    TerrenoSinLotes,
    TipoCelda,
    TipoProyecto,
    coherencia_de_loteo,
    exige_avenidas,
    jerarquias_en_uso,
    reglas_de_coherencia,
)
from motor_trazados.generador_red import GeneradorRed
from motor_trazados.referencia import ROTACION, solicitud_caso
from motor_trazados.semillas import SEMILLA_SUGERIDA
from motor_trazados.valores_referencia import (
    A_VALIDAR,
    CRITERIO_DISENO,
    FUENTES,
    JERARQUIAS_REFERENCIA,
    PARAMETROS_LOTEO_REFERENCIA,
)

PLAYA = ParametrosEstacionamiento(2.5, 5.0, 90, SentidoCirculacion.DOBLE, 2.0)


def campos(solicitud: SolicitudGeneracion) -> list[str]:
    return [problema.campo for problema in solicitud.validar()]


# --- Lo que todavía no se implementa: error claro, no una falla rara --------------------------


def test_pedir_una_playa_de_estacionamiento_dice_que_no_esta_implementado(referencia):
    playa = replace(referencia, tipo=TipoProyecto.ESTACIONAMIENTO, parametros=PLAYA)
    with pytest.raises(NoImplementado, match="playas de estacionamiento todavía no está implementada"):
        MotorGeneracion().generar(playa)


def test_la_playa_se_rechaza_antes_de_validar_sus_parametros(referencia):
    # Aunque los parámetros de la playa sean incoherentes, lo primero que se informa es que
    # el tipo no está implementado.
    playa = replace(referencia, tipo=TipoProyecto.ESTACIONAMIENTO, parametros=replace(PLAYA, ancho_plaza=-1))
    with pytest.raises(NoImplementado):
        MotorGeneracion().generar(playa)


def test_fijar_sin_manzanas_o_con_una_que_no_existe_da_el_problema_en_el_campo(referencia):
    """El recálculo (CU09) ya existe (D56): lo que se fija sale de `MotorGeneracion.fijar`, que rechaza
    una selección vacía o una manzana que la versión no tiene, con el campo."""
    motor = MotorGeneracion()
    origen = motor.generar(referencia)
    for manzanas, mensaje in (([], "al menos una manzana"), (["M2", "M99"], "«M99»")):
        with pytest.raises(SolicitudInvalida) as error:
            motor.fijar(origen, manzanas, referencia.estrategia.orientacion)
        (problema,) = error.value.problemas
        assert problema.campo == "manzanas" and mensaje in problema.mensaje


def test_los_elementos_fijados_aceptan_listas():
    fijados = ElementosFijados(sector=None, celdas=[], tramos=[], anclajes=[], manzanas=[])
    assert (fijados.celdas, fijados.tramos, fijados.anclajes, fijados.manzanas) == ((), (), (), ())


def test_no_implementado_es_tambien_un_not_implemented_error():
    assert issubclass(NoImplementado, NotImplementedError)


# --- Terrenos (D40): cualquier polígono válido ----------------------------------------------


def con_terreno(referencia, terreno, accesos):
    return replace(referencia, terreno=terreno, accesos=accesos)


def test_un_terreno_irregular_ahora_genera(referencia):
    """El pentágono de la pantalla de delimitación (p. 48), a escala, que hasta el motor 0.3.1
    se rechazaba por no ser rectangular (D33)."""
    pentagono = Polygon([(0, 0), (360, -20), (380, 250), (170, 320), (-10, 250)])
    resultado = MotorGeneracion().generar(con_terreno(referencia, pentagono, (Point(180, -10),)))
    assert resultado.lotes
    assert {celda.tipo for celda in resultado.celdas} <= {
        TipoCelda.LOTE,
        TipoCelda.ESPACIO_VERDE,
        TipoCelda.ESPACIO_LIBRE,
    }


def test_un_terreno_invalido_es_una_solicitud_invalida(referencia):
    # Un moño se cruza a sí mismo.
    mono = Polygon([(0, 0), (480, 270), (480, 0), (0, 270)])
    with pytest.raises(SolicitudInvalida) as error:
        MotorGeneracion().generar(con_terreno(referencia, mono, (Point(0, 135),)))
    assert [p.campo for p in error.value.problemas] == ["terreno"]


def test_un_terreno_donde_no_entra_un_lote_se_rechaza_con_causa_y_sugerencia(referencia):
    """Una franja de 300 × 30 m con la grilla a lo largo: entra la calle, pero a cada lado
    quedan 9 m de fondo."""
    franja = replace(
        con_terreno(referencia, box(0, 0, 300, 30), (Point(0, 15),)),
        estrategia=replace(referencia.estrategia, orientacion=0.0),
    )
    with pytest.raises(TerrenoSinLotes) as error:
        MotorGeneracion().generar(franja)
    assert "no entra ningún lote" in error.value.causa
    assert "fondo 25 m" in error.value.causa
    assert "orientación" in error.value.sugerencia


# --- Estrategia sugerida (D42) --------------------------------------------------------------


def test_la_estrategia_sugerida_es_la_grilla_paralela_al_lado_mayor(referencia):
    estrategia = MotorGeneracion().sugerir_estrategia(referencia.terreno)
    assert estrategia.patron_red is PatronRed.GRILLA
    # El rectángulo mínimo de GEOS sobre coordenadas de 10⁶ m trae ruido de coma flotante; la API
    # la redondea a las 2 decimales de su columna.
    assert estrategia.orientacion == pytest.approx(ROTACION, abs=1e-3)
    assert estrategia.semilla == SEMILLA_SUGERIDA == 1042


def test_en_un_poligono_irregular_se_usa_su_rectangulo_minimo():
    # La L del caso «l» está rotada 20°: su rectángulo mínimo también.
    assert GeneradorRed.orientacion_sugerida(solicitud_caso("l").terreno) == pytest.approx(20, abs=1e-3)


@pytest.mark.parametrize("giro", [0, 30, 135])
def test_en_un_cuadrado_se_toma_el_menor_angulo(giro):
    """Los cuatro lados miden lo mismo: entre 30° y 120° se toma 30° (en [0, 180))."""
    cuadrado = rotate(box(0, 0, 100, 100), giro, origin=(0, 0))
    assert GeneradorRed.orientacion_sugerida(cuadrado) == pytest.approx(giro % 90, abs=1e-6)


def test_la_orientacion_sugerida_esta_entre_0_y_180():
    rectangulo = rotate(box(0, 0, 300, 100), 160, origin=(0, 0))
    assert GeneradorRed.orientacion_sugerida(rectangulo) == pytest.approx(160, abs=1e-6)
    rectangulo = rotate(box(0, 0, 300, 100), 200, origin=(0, 0))
    assert GeneradorRed.orientacion_sugerida(rectangulo) == pytest.approx(20, abs=1e-6)


# --- Validación por campo (RNF01) -------------------------------------------------------------


def test_la_solicitud_de_referencia_es_valida(referencia):
    assert referencia.validar() == []


def test_construir_nunca_falla_y_validar_informa_el_campo(referencia):
    incoherentes = replace(PARAMETROS_LOTEO_REFERENCIA, superficie_minima=700, frente_objetivo=8)
    solicitud = replace(referencia, parametros=incoherentes)
    # En el orden de la «Validación de coherencia» de la p. 49 (`reglas_de_coherencia`, D78).
    assert campos(solicitud) == ["parametros.superficie_minima", "parametros.frente_objetivo"]
    with pytest.raises(SolicitudInvalida) as error:
        MotorGeneracion().generar(solicitud)
    assert [p.campo for p in error.value.problemas] == campos(solicitud)


@pytest.mark.parametrize(
    ("cambio", "campo"),
    [
        ({"porcentaje_espacio_verde": 120}, "parametros.porcentaje_espacio_verde"),
        ({"frente_minimo": 0}, "parametros.frente_minimo"),
        ({"fondo_minimo": float("nan")}, "parametros.fondo_minimo"),
        ({"porcentaje_espacio_verde": 60, "porcentaje_equipamiento": 50}, "parametros.porcentaje_espacio_verde"),
        ({"superficie_minima_verde": 0}, "parametros.superficie_minima_verde"),
        ({"ancho_minimo_verde": -5}, "parametros.ancho_minimo_verde"),
        ({"ancho_minimo_lote": 0}, "parametros.ancho_minimo_lote"),
        # El ancho útil no puede pasar el frente mínimo, y el tope de unión es al menos 1 (D43).
        ({"ancho_minimo_lote": 12}, "parametros.ancho_minimo_lote"),
        ({"factor_union_maximo": 0.8}, "parametros.factor_union_maximo"),
        # El criterio del asignador es uno de los dos (D46).
        ({"criterio_espacio_verde": "belleza"}, "parametros.criterio_espacio_verde"),
        # Ord. 8060, art. 48 (D50): la grilla corta las manzanas en la longitud máxima, que tiene
        # que admitir el lado menor y no pedir un pasaje peatonal, que el motor no traza.
        ({"lado_minimo_manzana": 0}, "parametros.lado_minimo_manzana"),
        ({"lado_minimo_manzana": 150}, "parametros.lado_minimo_manzana"),
        ({"longitud_maxima_manzana": 210}, "parametros.longitud_maxima_manzana"),
        ({"lado_maximo_sin_pasaje": 260}, "parametros.lado_maximo_sin_pasaje"),
    ],
)
def test_parametros_de_loteo_invalidos(referencia, cambio, campo):
    solicitud = replace(referencia, parametros=replace(PARAMETROS_LOTEO_REFERENCIA, **cambio))
    assert campos(solicitud) == [campo]


def test_las_reglas_de_coherencia_de_la_p_49_con_los_valores_de_referencia():
    """Las cuatro de la p. 49 primero, todas cumplidas, con sus valores (D78)."""
    reglas = reglas_de_coherencia(PARAMETROS_LOTEO_REFERENCIA, JERARQUIAS_REFERENCIA)
    assert [r.clave for r in reglas[:4]] == ["superficie", "frente_objetivo", "cesiones", "lote_minimo"]
    assert all(r.cumple and r.problemas == () for r in reglas)
    por_clave = {r.clave: r for r in reglas}
    assert por_clave["lote_minimo"].detalle == "10,00 m × 25,00 m = 250,00 m² ≤ 600,00 m²"
    assert por_clave["cesiones"].detalle == "Espacio verde y equipamiento: 15,00 %"
    assert por_clave["calzada_jerarquias"].detalle == (
        "Colectora (perfil 6): 12,00 m; Local (perfil 9): 7,00 m (mínima 6,00 m)"
    )


def test_un_lote_de_frente_y_fondo_minimos_no_puede_pasar_la_superficie_maxima(referencia):
    """La cuarta regla de la p. 49 (D78): 10 m × 70 m = 700 m², más que los 600 m² de la máxima."""
    solicitud = replace(referencia, parametros=replace(PARAMETROS_LOTEO_REFERENCIA, fondo_minimo=70))
    assert campos(solicitud) == ["parametros.fondo_minimo"]
    regla = next(r for r in reglas_de_coherencia(solicitud.parametros) if r.clave == "lote_minimo")
    assert not regla.cumple and "700,00 m²" in regla.problemas[0].mensaje


def test_la_calzada_de_cada_jerarquia_alcanza_la_minima_del_art_12(referencia):
    """Una local de 5 m de calzada se rechaza antes de generar, en su campo (D78). Ley 4146, art. 12."""
    angosta = JerarquiaCorredor("Angosta", 2, ancho_calzada=5.0, ancho_vereda=3.5, radio_ochava=4.0)
    solicitud = replace(referencia, jerarquias=(JERARQUIAS_REFERENCIA[0], angosta))
    assert campos(solicitud) == ["jerarquias[1].ancho_calzada"]
    with pytest.raises(SolicitudInvalida):
        MotorGeneracion().generar(solicitud)


SIN_AVENIDAS = replace(PARAMETROS_LOTEO_REFERENCIA, porcentaje_minimo_avenidas=0.0)


def test_sin_avenidas_solo_se_usa_la_jerarquia_menor():
    """La casilla «Exigir avenidas» (D85): con 0 %, todas las calles son de la jerarquía menor (D48)."""
    assert jerarquias_en_uso(JERARQUIAS_REFERENCIA, 20.0) == (True, True)
    assert jerarquias_en_uso(JERARQUIAS_REFERENCIA, 0.0) == (False, True)
    # El orden de la lista no importa: manda `orden`. Una intermedia no se usa nunca (C6).
    intermedia = JerarquiaCorredor("Intermedia", 3, ancho_calzada=9.0, ancho_vereda=3.0, radio_ochava=4.0)
    local = replace(JERARQUIAS_REFERENCIA[1], orden=5)
    assert jerarquias_en_uso((local, intermedia, JERARQUIAS_REFERENCIA[0]), 20.0) == (True, False, True)
    assert jerarquias_en_uso((local, intermedia, JERARQUIAS_REFERENCIA[0]), 0.0) == (True, False, False)
    assert jerarquias_en_uso((), 20.0) == ()
    # Un valor que no es un número cuenta como que se exigen: lo que está mal lo dice la validación.
    assert exige_avenidas(None) and exige_avenidas(float("nan")) and not exige_avenidas(0)


def test_sin_avenidas_no_van_las_reglas_de_la_avenida(referencia):
    """Con 0 % el ancho de avenida y la colectora no se usan (D85): sus reglas no se muestran ni rechazan."""
    con = [r.clave for r in reglas_de_coherencia(PARAMETROS_LOTEO_REFERENCIA, JERARQUIAS_REFERENCIA)]
    sin = reglas_de_coherencia(SIN_AVENIDAS, JERARQUIAS_REFERENCIA)
    assert [r.clave for r in sin] == [c for c in con if c != "avenida_calle"]
    calzada = next(r for r in sin if r.clave == "calzada_jerarquias")
    assert calzada.detalle == "Local (perfil 9): 7,00 m (mínima 6,00 m)"
    # Una colectora que no se usa no rompe la calzada mínima, ni un ancho de avenida menor que el de calle.
    angosta = replace(JERARQUIAS_REFERENCIA[0], ancho_calzada=5.0)
    parametros = replace(SIN_AVENIDAS, ancho_minimo_avenida=10.0)
    solicitud = replace(referencia, parametros=parametros, jerarquias=(angosta, JERARQUIAS_REFERENCIA[1]))
    assert campos(solicitud) == []
    # Con avenidas, las dos vuelven a valer, con el índice de la jerarquía en la lista.
    con_avenidas = replace(solicitud, parametros=replace(parametros, porcentaje_minimo_avenidas=20.0))
    assert campos(con_avenidas) == ["parametros.ancho_minimo_avenida", "jerarquias[0].ancho_calzada"]


def test_la_coherencia_en_vivo_da_los_mismos_problemas_que_validar(referencia):
    """`coherencia_de_loteo` es lo que valida la API mientras se editan los parámetros (D78)."""
    incoherentes = replace(PARAMETROS_LOTEO_REFERENCIA, superficie_minima=700)
    problemas, reglas = coherencia_de_loteo(incoherentes, JERARQUIAS_REFERENCIA)
    assert [p.campo for p in problemas] == campos(replace(referencia, parametros=incoherentes))
    assert [r.clave for r in reglas if not r.cumple] == ["superficie"]
    # Con un valor que no es un número, todavía no hay reglas: solo el problema del campo.
    sin_frente = replace(PARAMETROS_LOTEO_REFERENCIA, frente_minimo=0)
    problemas, reglas = coherencia_de_loteo(sin_frente, JERARQUIAS_REFERENCIA)
    assert ([p.campo for p in problemas], reglas) == (["parametros.frente_minimo"], [])


def test_una_calzada_invalida_la_informa_la_jerarquia_y_no_la_coherencia(referencia):
    rota = JerarquiaCorredor("Rota", 2, ancho_calzada=0, ancho_vereda=2.5, radio_ochava=4.0)
    assert campos(replace(referencia, jerarquias=(JERARQUIAS_REFERENCIA[0], rota))) == ["jerarquias[1].ancho_calzada"]


def test_el_tipo_tiene_que_coincidir_con_los_parametros(referencia):
    assert campos(replace(referencia, parametros=PLAYA)) == ["parametros"]


def test_un_acceso_fuera_del_perimetro(referencia):
    adentro = referencia.terreno.centroid
    assert campos(replace(referencia, accesos=(referencia.accesos[0], adentro))) == ["accesos[1]"]


def test_hace_falta_al_menos_un_acceso(referencia):
    assert campos(replace(referencia, accesos=())) == ["accesos"]


def test_el_terreno_no_puede_tener_huecos(referencia):
    hueco = referencia.terreno.centroid.buffer(5).exterior.coords
    con_hueco = Polygon(referencia.terreno.exterior.coords, [hueco])
    assert "terreno" in campos(replace(referencia, terreno=con_hueco))


def test_la_semilla_se_valida_con_la_regla_de_semillas(referencia):
    estrategia = replace(referencia.estrategia, semilla=-3)
    assert campos(replace(referencia, estrategia=estrategia)) == ["estrategia.semilla"]


def test_dos_jerarquias_no_pueden_tener_el_mismo_orden(referencia):
    duplicada = replace(referencia.jerarquias[1], orden=1)
    assert campos(replace(referencia, jerarquias=(referencia.jerarquias[0], duplicada))) == ["jerarquias"]


def test_las_listas_se_guardan_como_tuplas():
    solicitud = SolicitudGeneracion(
        TipoProyecto.LOTEO, box(0, 0, 10, 10), [Point(0, 5)], PARAMETROS_LOTEO_REFERENCIA, [], None
    )
    assert isinstance(solicitud.accesos, tuple) and isinstance(solicitud.jerarquias, tuple)


# --- Valores de referencia (D23) --------------------------------------------------------------


def test_cada_valor_de_referencia_tiene_su_fuente():
    sin_fuente = [c.name for c in fields(ParametrosLoteo) if c.name not in FUENTES]
    assert not sin_fuente, f"Valores de referencia sin fuente normativa ni marca «{A_VALIDAR}»: {sin_fuente}"
    assert {"jerarquias.anchos", "jerarquias.radio_ochava"} <= FUENTES.keys()


def test_los_valores_sin_verificar_estan_marcados():
    """Si se verifica uno en la norma, se actualiza su fuente y esta lista (y D23)."""
    marcados = sorted(campo for campo, fuente in FUENTES.items() if fuente.startswith(A_VALIDAR))
    assert marcados == [
        "ancho_minimo_lote",
        "ancho_minimo_verde",
        "factor_union_maximo",
        "fondo_minimo",
        "jerarquias.radio_ochava",
        "relacion_fondo_frente_max",
        "superficie_minima_verde",
    ]


def test_el_criterio_del_asignador_es_un_criterio_de_diseno_y_no_una_norma():
    """El autor lo pidió así (D46): el portal lo marca como criterio de diseño. Desde el motor 0.7.0
    el de referencia es «más cercanía» (D51)."""
    assert PARAMETROS_LOTEO_REFERENCIA.criterio_espacio_verde is CriterioEspacioVerde.CERCANIA
    assert FUENTES["criterio_espacio_verde"].startswith(f"{CRITERIO_DISENO}, no una norma")
    assert {c.value for c in CriterioEspacioVerde} == {"menos_lotes", "cercania"}
