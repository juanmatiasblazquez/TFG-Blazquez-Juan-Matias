"""Asignador de espacios verdes (D44, D46, D51): completa la cesión del 10 % con el menor exceso posible.

Con los dos criterios («más cercanía», el de referencia, y «menos lotes perdidos»), sobre los
cinco casos de referencia (rectangular, irregular, L, U y triángulo):
- todos llegan al 10 %;
- «menos lotes perdidos» nunca pierde más lotes que «más cercanía», y «más cercanía» nunca deja
  los lotes más lejos del verde que «menos lotes perdidos»;
- con «menos lotes», los lotes grandes se convierten primero (D47);
- cada pieza que convierte es necesaria: sin ella, o sin su última parcela, no se llega;
- toda pieza verde cumple los criterios del verde;
- la distancia que optimiza el asignador es la del indicador.

Además: un terreno donde es imposible deja la cesión incumplida, con causa y sugerencia, y no
pierde ningún lote; el verde de la L no puede crecer porque ocupa sola su manzana; y la regla de
selección (`elegir`, `piezas_minimas`) y la cuenta de la circularidad, aparte.
"""

import math
import time
from dataclasses import replace
from functools import lru_cache

import pytest
from shapely import box

from contorno import con_contorno
from motor_trazados import CriterioEspacioVerde, MotorGeneracion, TipoCelda, TipoIncumplimiento
from motor_trazados.asignador import AsignadorEspaciosVerdes, Candidata, elegir, piezas_minimas
from motor_trazados.geometria import IndiceEjes, union_cobertura
from motor_trazados.referencia import CASOS, solicitud_caso
from motor_trazados.remanentes import es_espacio_verde
from motor_trazados.valores_referencia import PARAMETROS_LOTEO_REFERENCIA as P
from motor_trazados.verificador import es_lote_grande, exigido_cesion, faltante_cesion, verde_computable
from particion import assert_particion

CRITERIOS = tuple(CriterioEspacioVerde)


def con_criterio(solicitud, criterio):
    return replace(solicitud, parametros=replace(solicitud.parametros, criterio_espacio_verde=criterio))


def asignar(solicitud):
    """El resultado sin asignador, el del motor con asignador y la asignación sobre el primero."""
    sin = MotorGeneracion(asignar_espacios_verdes=False).generar(solicitud)
    con = MotorGeneracion().generar(solicitud)
    circulacion = union_cobertura(sin.corredores)
    ejes = IndiceEjes([tramo.eje for tramo in sin.red.tramos()])
    asignacion = AsignadorEspaciosVerdes().asignar(
        sin.celdas, sin.manzanas, circulacion, sin.red, ejes, solicitud.parametros
    )
    return sin, con, asignacion, circulacion


@lru_cache(maxsize=None)
def asignado(nombre: str, criterio: CriterioEspacioVerde, contorno: bool = False):
    """Un caso de referencia con un criterio, generado una sola vez por corrida. Con `contorno`, con la
    calle de borde en todo el contorno (D50, D86)."""
    s = con_criterio(solicitud_caso(nombre), criterio)
    if contorno:
        s = con_contorno(s)
    return (f"{nombre}/{criterio}", s, *asignar(s))


@pytest.fixture(scope="module", params=[(n, c) for n in sorted(CASOS) for c in CRITERIOS], ids=lambda p: f"{p[0]}-{p[1]}")
def caso(request):
    return asignado(*request.param)


def superficies(resultado, p) -> tuple[float, float]:
    """El verde que computa para la cesión con los parámetros `p` (con «cercanía», sin las puntas;
    D55, D58) y la superficie de los lotes."""
    return verde_computable(resultado.celdas, resultado.manzanas, p), math.fsum(c.geometria.area for c in resultado.lotes)


# --- Los casos de referencia -------------------------------------------------------------------


def test_los_casos_de_referencia_llegan_a_la_cesion(caso):
    nombre, s, sin, con, asignacion, _ = caso
    assert asignacion.motivo is None, nombre
    assert TipoIncumplimiento.CESION_ESPACIO_VERDE not in {i.tipo for i in con.incumplimientos}, nombre
    assert con.indicadores.porcentaje_cesion >= s.parametros.porcentaje_espacio_verde - 1e-6, nombre
    # El motor usa exactamente lo que da el asignador.
    assert [(c.designacion, c.tipo) for c in con.celdas] == [(c.designacion, c.tipo) for c in asignacion.celdas]
    assert_particion(s, con)


def test_toda_pieza_verde_cumple_los_criterios_del_verde(caso):
    nombre, s, sin, con, asignacion, circulacion = caso
    for celda in con.celdas:
        if celda.tipo is TipoCelda.ESPACIO_VERDE:
            assert es_espacio_verde(celda.geometria, circulacion, s.parametros), (nombre, celda.designacion)


def test_cada_pieza_convertida_es_necesaria(caso):
    """Minimalidad (D44): sin cualquiera de las piezas, la cesión no llega. Sin la última parcela
    de la última pieza, tampoco, o lo que queda deja de ser verde."""
    nombre, s, sin, con, asignacion, circulacion = caso
    if not asignacion.piezas:
        # Si el verde de los remanentes ya cubre la cesión, no hace falta convertir nada: con «menos
        # lotes» las puntas computan y en la L y el triángulo la cubren solas (D58).
        assert not faltante_cesion(*superficies(sin, s.parametros), s.parametros), nombre
        return
    entrada = {c.designacion: c for c in sin.celdas}
    verde, lotes = superficies(con, s.parametros)

    def sin_parcelas(designaciones):
        de_lotes = math.fsum(entrada[d].geometria.area for d in designaciones if entrada[d].tipo is TipoCelda.LOTE)
        otras = math.fsum(entrada[d].geometria.area for d in designaciones if entrada[d].tipo is not TipoCelda.LOTE)
        return faltante_cesion(verde - de_lotes - otras, lotes + de_lotes, s.parametros)

    for pieza in asignacion.piezas:
        assert sin_parcelas(pieza.parcelas) > 0, (nombre, pieza)
    ultima = asignacion.piezas[-1]
    quedan = ([ultima.base] if ultima.base else []) + list(ultima.parcelas[:-1])
    geometria = union_cobertura([entrada[d].geometria for d in quedan]) if quedan else None
    deja_de_ser_verde = geometria is None or not es_espacio_verde(geometria, circulacion, s.parametros)
    assert sin_parcelas(ultima.parcelas[-1:]) > 0 or deja_de_ser_verde, (nombre, ultima)


def test_solo_se_convierten_parcelas_enteras(caso):
    """Cada pieza verde es una unión de parcelas de la clasificación: ningún lote se corta, y
    los lotes que quedan son los mismos de antes."""
    nombre, s, sin, con, asignacion, _ = caso
    antes = sorted(round(c.geometria.area, 6) for c in sin.lotes)
    despues = sorted(round(c.geometria.area, 6) for c in con.lotes)
    convertidos = [c for c in sin.lotes if c.designacion in {d for p in asignacion.piezas for d in p.parcelas}]
    assert len(despues) == len(antes) - len(convertidos)
    for area in despues:
        assert area in antes


@pytest.mark.parametrize("nombre", sorted(CASOS))
def test_menos_lotes_perdidos_nunca_pierde_mas_que_mas_cercania(nombre):
    """«Menos lotes» arma también el plan de «cercanía» y se queda con el que convierte menos lotes
    (D46): una heurística, no el mínimo posible."""
    perdidos = {}
    for criterio in CRITERIOS:
        _, _, sin, con, _, _ = asignado(nombre, criterio)
        perdidos[criterio] = len(sin.lotes) - len(con.lotes)
    assert perdidos[CriterioEspacioVerde.MENOS_LOTES] <= perdidos[CriterioEspacioVerde.CERCANIA], perdidos


def test_en_la_u_a_90_grados_menos_lotes_no_pierde_mas_que_cercania():
    """El contraejemplo que encontró el barrido (sesión 7): con k* = 2, elegir la manzana entera
    que menos lotes cuesta (9 lotes, 2.952 m² de aporte) dejaba casi todo por cubrir, y la pieza
    siguiente costaba 17. Ahora esa manzana se elige por lotes por m² de aporte, y además
    «menos lotes» se queda con el plan de «más cercanía» si pierde menos (D46)."""
    from test_particion import FORMAS_BARRIDO, solicitud

    s = solicitud(FORMAS_BARRIDO["U"], 90)
    perdidos = {}
    for criterio in CRITERIOS:
        sin, con, _, _ = asignar(con_criterio(s, criterio))
        perdidos[criterio] = len(sin.lotes) - len(con.lotes)
    assert perdidos[CriterioEspacioVerde.MENOS_LOTES] <= perdidos[CriterioEspacioVerde.CERCANIA], perdidos


@pytest.mark.parametrize("nombre", sorted(CASOS))
def test_mas_cercania_nunca_deja_los_lotes_mas_lejos_que_menos_lotes(nombre):
    """«Más cercanía» arma también el plan de «menos lotes» y se queda con el que deja menor
    distancia media de los lotes al verde (D51): el indicador lo muestra."""
    distancia = {}
    for criterio in CRITERIOS:
        _, _, _, con, _, _ = asignado(nombre, criterio)
        distancia[criterio] = con.indicadores.distancia_media_verde
    assert distancia[CriterioEspacioVerde.CERCANIA] <= distancia[CriterioEspacioVerde.MENOS_LOTES] + 1e-6, distancia


def test_la_distancia_del_asignador_es_la_del_indicador(caso):
    """El asignador mide la distancia de cada lote al verde desde los puntos de acceso de cada
    parcela, y el indicador desde los de la pieza unida: son los mismos, porque la unión de
    cobertura conserva los vértices (D51)."""
    from motor_trazados.asignador import _Plan
    from motor_trazados.geometria import IndiceEjes

    nombre, s, sin, con, asignacion, circulacion = caso
    plan = _Plan(list(asignacion.celdas), con.manzanas, circulacion, con.red, IndiceEjes([t.eje for t in con.red.tramos()]), s.parametros)
    assert plan.distancia_final() == pytest.approx(con.indicadores.distancia_media_verde, abs=1e-6), nombre


def test_con_menos_lotes_los_lotes_grandes_se_convierten_primero(caso):
    """Paso 0 de «menos lotes» (D46, D47): los lotes grandes que solos son un verde válido van
    antes que cualquier otro lote. Si entre todos cubren lo que falta, no se convierte nada más; si
    no, se convierten todos. Con «más cercanía» compiten como cualquier pieza (D51)."""
    nombre, s, sin, con, asignacion, circulacion = caso
    if s.parametros.criterio_espacio_verde is not CriterioEspacioVerde.MENOS_LOTES:
        return
    p = s.parametros
    grandes = [
        c for c in sin.lotes if es_lote_grande(c.geometria, p) and es_espacio_verde(c.geometria, circulacion, p)
    ]
    convertidas = {d for pieza in asignacion.piezas for d in pieza.parcelas}
    if not grandes:
        return
    verde, lotes = superficies(sin, p)
    aporte = math.fsum(c.geometria.area for c in grandes) * (1 + p.porcentaje_espacio_verde / 100)
    if aporte + 0.01 >= faltante_cesion(verde, lotes, p):
        assert convertidas <= {c.designacion for c in grandes}, nombre
    else:
        assert {c.designacion for c in grandes} <= convertidas, nombre


def test_en_la_l_las_puntas_verdes_computan_solo_con_menos_lotes():
    """Las dos puntas de la L con la calle de borde en todo el contorno (D50) no alcanzan el lado menor
    del art. 48 y quedan como verde con los dos criterios (cuentan para la distancia). Para la cesión,
    la regla depende del criterio (D58):

    - con «más cercanía» no computan (D55): la cesión se completa con verde que ubica el asignador;
    - con «menos lotes» computan y la cubren solas, como hasta D52: el asignador no convierte nada.
    La situación de la sesión 6 sigue probada a mano en la prueba siguiente."""
    from motor_trazados.verificador import alcanza_lado_menor

    for criterio in CRITERIOS:
        _, s, sin, con, asignacion, _ = asignado("l", criterio, contorno=True)
        puntas = [
            c
            for c in con.celdas
            if c.tipo is TipoCelda.ESPACIO_VERDE
            and not alcanza_lado_menor(con.manzanas[c.indice_manzana - 1], s.parametros)
        ]
        assert len(puntas) == 2, criterio
        i = con.indicadores
        if criterio is CriterioEspacioVerde.CERCANIA:
            assert faltante_cesion(*superficies(sin, s.parametros), s.parametros) > 0, criterio
            assert asignacion.piezas, criterio
            assert i.superficie_espacio_verde - i.superficie_verde_computable == pytest.approx(
                math.fsum(c.geometria.area for c in puntas)
            )
        else:
            assert not faltante_cesion(*superficies(sin, s.parametros), s.parametros), criterio
            assert asignacion.piezas == (), criterio
            assert i.superficie_verde_computable == pytest.approx(i.superficie_espacio_verde)
        assert i.porcentaje_cesion >= s.parametros.porcentaje_espacio_verde, criterio


def test_el_plan_del_otro_criterio_cuenta_la_cesion_con_la_regla_de_la_corrida():
    """Con «más cercanía» el asignador arma también el plan de «menos lotes» (D51), pero ese plan
    cuenta la cesión con la regla de la corrida, sin las puntas (D58). Si la contara con la suya, en
    la L se quedaría con el verde de las puntas y la cesión de «cercanía» no llegaría."""
    _, s, sin, con, asignacion, _ = asignado("l", CriterioEspacioVerde.CERCANIA)
    assert asignacion.motivo is None
    assert not faltante_cesion(*superficies(con, s.parametros), s.parametros)
    assert TipoIncumplimiento.CESION_ESPACIO_VERDE not in {i.tipo for i in con.incumplimientos}


def test_un_verde_solo_en_su_manzana_no_crece_y_la_pieza_nueva_llega_al_verde_minimo():
    """La situación de la L de la sesión 6, armada a mano. Al sur de una calle local, un verde de
    40 × 30 m (1.200 m²) es su manzana entera; al norte, 30 lotes de 12 × 36 m (12.960 m²). Faltan
    96 m², pero el verde no tiene parcelas vecinas en su manzana, y la pieza nueva tiene que llegar
    sola a los 1.000 m² del verde mínimo: 3 lotes (1.296 m²), con un exceso de 1.329,6 m²."""
    from shapely import LineString
    from motor_trazados import CeldaGenerada
    from motor_trazados.red import RedCirculacion
    from trazados import LOCAL

    calle = box(-10, -6, 370, 6)
    red = RedCirculacion()
    red.agregar_tramo((-10, 0), (370, 0), None, LOCAL)
    verde = CeldaGenerada(box(0, -36, 40, -6), TipoCelda.ESPACIO_VERDE, 0.0, 0.0, 1, "M1-EV01")
    lotes = [CeldaGenerada(box(12 * k, 6, 12 * k + 12, 42), TipoCelda.LOTE, 0.0, 0.0, 2, f"M2-L{k + 1:02d}") for k in range(30)]
    manzanas = [verde.geometria, union_cobertura([c.geometria for c in lotes])]
    for criterio in CRITERIOS:
        p = replace(P, criterio_espacio_verde=criterio)
        asignacion = AsignadorEspaciosVerdes().asignar(
            [verde, *lotes], manzanas, calle, red, IndiceEjes([LineString([(-10, 0), (370, 0)])]), p
        )
        (pieza,) = asignacion.piezas
        assert pieza.base is None and pieza.indice_manzana == 2 and len(pieza.parcelas) == 3, criterio


def test_informe_de_los_casos(capsys):
    """Imprime, por caso y criterio, los lotes que cuesta el verde, las piezas y el exceso (D44,
    D46)."""
    filas = []
    for nombre in sorted(CASOS):
        for criterio in CRITERIOS:
            inicio = time.perf_counter()
            _, s, sin, con, asignacion, _ = asignado(nombre, criterio)
            verde, lotes = superficies(con, s.parametros)
            exceso = verde - exigido_cesion(lotes, s.parametros)
            filas.append(
                f"  {nombre:<11} {criterio:<12} lotes {len(sin.lotes):>3} → {len(con.lotes):>3} "
                f"(−{len(sin.lotes) - len(con.lotes)}), piezas {len(asignacion.piezas)}, cesión "
                f"{sin.indicadores.porcentaje_cesion:5.2f} % → {con.indicadores.porcentaje_cesion:5.2f} %, "
                f"exceso {exceso:7.1f} m², lotes grandes {con.indicadores.cantidad_lotes_grandes}"
            )
            assert time.perf_counter() - inicio < 10
    with capsys.disabled():
        print("\n[D44, D46] asignador de espacios verdes:\n" + "\n".join(filas))


# --- Un terreno donde es imposible -----------------------------------------------------------


def test_un_terreno_donde_no_entra_un_verde_deja_la_cesion_incumplida_con_causa_y_sugerencia():
    """Con la calle de borde (D50) toda manzana con lotes mide al menos 42 m de lado, así que admite
    un verde de 1.000 m². Para probar la causa, el rectangular pide un verde de 20.000 m²: ninguna
    manzana lo admite, no se convierte nada y la cesión queda incumplida con su causa."""
    s = solicitud_caso("referencia")
    s = replace(s, parametros=replace(s.parametros, superficie_minima_verde=20_000.0))
    sin, con, asignacion, _ = asignar(s)
    assert sin.lotes and asignacion.piezas == ()
    assert len(con.lotes) == len(sin.lotes)
    (cesion,) = [i for i in con.incumplimientos if i.tipo is TipoIncumplimiento.CESION_ESPACIO_VERDE]
    assert "Causa:" in cesion.detalle and "Sugerencia:" in cesion.detalle
    assert "ninguna manzana admite un verde" in cesion.detalle
    assert_particion(s, con)


# --- La regla de selección y la circularidad ---------------------------------------------------


def candidata(nombre, superficie_lotes=0.0, clave=(0,), lotes=1) -> Candidata:
    return Candidata(
        manzana=1, parcelas=(), base=None, aporte=0.0, superficie_lotes=superficie_lotes, cubre=True,
        clave=(nombre, *clave), lotes=lotes,
    )


DISTANCIAS = {"a": 120.0, "b": 100.0, "c": 100.0, "d": 100.0}
EXCESOS = {"a": 0.0, "b": 50.0, "c": 50.0, "d": 10.0}


def distancia(c):
    return DISTANCIAS[c.clave[0]]


def exceso(c):
    return EXCESOS[c.clave[0]]


def test_con_mas_cercania_manda_la_distancia_y_se_desempata_en_orden():
    cercania = CriterioEspacioVerde.CERCANIA
    a, b, c, d = candidata("a", 300), candidata("b", 400), candidata("c", 300), candidata("d", 300)
    assert elegir([a, b], cercania, distancia, exceso) is b  # la distancia manda
    assert elegir([b, c], cercania, distancia, exceso) is c  # después, menos superficie de lotes
    assert elegir([c, d], cercania, distancia, exceso) is d  # después, menos exceso
    gemela = candidata("d", 300, clave=(1,))
    assert elegir([gemela, d], cercania, distancia, exceso) is d  # por último, la clave estable


def test_con_mas_cercania_desempatan_la_distancia_maxima_y_los_lotes():
    """Con la misma distancia media, la menor distancia máxima; con la misma, los menos lotes (D51)."""
    cercania = CriterioEspacioVerde.CERCANIA
    maximas = {"b": 300.0, "c": 250.0, "d": 250.0}
    b, c, d = candidata("b", 300, lotes=1), candidata("c", 300, lotes=4), candidata("d", 300, lotes=2)
    assert elegir([b, c], cercania, distancia, exceso, maxima=lambda x: maximas[x.clave[0]]) is c
    assert elegir([c, d], cercania, distancia, exceso, maxima=lambda x: maximas[x.clave[0]]) is d


def test_con_menos_lotes_perdidos_manda_la_cantidad_de_lotes():
    """La candidata «a» queda más lejos (120 m), pero convierte un lote y no tres (D46)."""
    menos = CriterioEspacioVerde.MENOS_LOTES
    a, b = candidata("a", 1063, lotes=1), candidata("b", 1100, lotes=3)
    assert elegir([a, b], menos, distancia, exceso) is a
    assert elegir([a, b], CriterioEspacioVerde.CERCANIA, distancia, exceso) is b
    # Con los mismos lotes, la menor superficie de lotes; con la misma distancia, el menor exceso.
    c, d = candidata("c", 900, lotes=3), candidata("d", 900, lotes=3)
    assert elegir([b, c], menos, distancia, exceso) is c
    assert elegir([c, d], menos, distancia, exceso) is d


@pytest.mark.parametrize(
    ("aportes", "faltante", "esperado"),
    [([5, 3, 2], 5, 1), ([5, 3, 2], 7, 2), ([2, 5, 3], 10, 3), ([5, 3, 2], 11, None), ([], 1, None)],
)
def test_piezas_minimas_suma_de_mayor_a_menor(aportes, faltante, esperado):
    assert piezas_minimas(aportes, faltante) == esperado


def test_la_base_que_se_achica_se_resuelve_en_forma_cerrada():
    """Con 1.000 m² de lotes y nada de verde, hacen falta 100 m² de verde si salen de un libre,
    pero solo 100 / 1,1 = 90,9 m² si salen de lotes: la base baja a 909,1 m² (D44)."""
    assert faltante_cesion(0, 1000, P) == pytest.approx(100)
    assert faltante_cesion(100, 1000, P) == 0  # de un libre: la base no cambia
    de_lotes = 100 / 1.1
    assert faltante_cesion(de_lotes, 1000 - de_lotes, P) == 0
    assert faltante_cesion(de_lotes - 0.5, 1000 - de_lotes + 0.5, P) > 0
    assert faltante_cesion(90, 910, P) > 0  # 90 m² de lotes no alcanzan
