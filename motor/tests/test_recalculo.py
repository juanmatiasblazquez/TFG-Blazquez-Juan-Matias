"""CU09: fijar sectores y recalcular (secuencia de la p. 44; D56).

Sobre una versión generada se fijan manzanas enteras, con sus celdas y las calles que las rodean, y
se recalcula el resto con la misma orientación o con otra. Sobre el trazado completo:
- lo fijado no cambia: celdas y manzanas al bit, y las calles con su eje y su superficie;
- la partición cierra (D39), la red es una sola pieza y llega a los accesos, y valen las reglas
  globales (cesión, 20 % de avenidas) y las de lotes y manzanas (forma, art. 48, art. 54);
- el dominio restante puede tener un agujero o estar en varias piezas;
- los cursos alternativos: 3.a (lo fijado abarca todo) y 5.a (lo nuevo no se conecta);
- con la misma orientación, la grilla nueva continúa las calles fijadas; con otra, las calles nuevas
  se empalman en las fijadas, que se parten sin cambiar su superficie.

El barrido de recálculo (`pytest -m barrido`) repite lo esencial sobre los 96 terrenos.
"""

import math
import os
import subprocess
import sys
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest
import shapely
from shapely import MultiPolygon, Point, box
from shapely.affinity import translate

from motor_trazados import (
    CalleBorde,
    CeldaGenerada,
    ElementosFijados,
    ErrorConectividad,
    Estrategia,
    ManzanaFijada,
    MotorGeneracion,
    PatronRed,
    SinDominioRestante,
    SolicitudGeneracion,
    TipoCelda,
    TipoIncumplimiento,
    TipoProyecto,
)
from motor_trazados.geometria import IndiceEjes, MarcoLocal, medir, poligonos, union_cobertura
from motor_trazados.referencia import solicitud_caso
from motor_trazados.valores_referencia import JERARQUIAS_REFERENCIA, PARAMETROS_LOTEO_REFERENCIA
from motor_trazados.verificador import (
    alcanza_lado_menor,
    es_lote,
    faltante_cesion,
    lado_mayor_manzana,
    porcentaje_avenidas,
    verde_computable,
)
from particion import assert_particion, assert_particion_recalculo, defectos_de_particion

# (caso, manzanas fijadas, giro de la orientación): con la misma orientación, a 90° y a 45°; fijado
# contra el borde y en el medio.
CASOS = [
    ("referencia", ("M2", "M3"), 0),
    ("referencia", ("M2", "M3"), 90),
    ("referencia", ("M6", "M7"), 0),
    ("referencia", ("M8", "M9"), 45),
    ("irregular", ("M4", "M5"), 0),
    ("l", ("M3", "M6"), 90),
    ("u", ("M6",), 0),
    ("triangulo", ("M4", "M5"), 45),
]


@lru_cache(maxsize=None)
def origen(caso: str):
    s = solicitud_caso(caso)
    return s, MotorGeneracion().generar(s)


@lru_cache(maxsize=None)
def recalculado(caso: str, manzanas: tuple[str, ...], giro: float):
    s, o = origen(caso)
    motor = MotorGeneracion()
    fijados = motor.fijar(o, manzanas, s.estrategia.orientacion)
    nueva = replace(s, estrategia=replace(s.estrategia, orientacion=(s.estrategia.orientacion + giro) % 180))
    return nueva, o, fijados, motor.recalcular(nueva, fijados)


@pytest.fixture(scope="module", params=CASOS, ids=lambda c: f"{c[0]}-{'-'.join(c[1])}-{c[2]}")
def caso(request):
    return recalculado(*request.param)


def vertices(geometria) -> list:
    return [c for parte in shapely.get_parts(geometria) for c in parte.exterior.coords]


# --- Lo fijado no cambia ----------------------------------------------------------------------


def test_las_celdas_y_las_manzanas_fijadas_quedan_identicas(caso):
    """Al bit: misma designación, mismo tipo, mismas coordenadas en el mismo orden."""
    s, o, fijados, r = caso
    de_origen = {c.designacion: c for c in o.celdas}
    resultado = {c.designacion: c for c in r.celdas}
    for celda in fijados.celdas:
        assert celda.designacion in resultado
        nueva, vieja = resultado[celda.designacion], de_origen[celda.designacion]
        assert nueva.tipo is vieja.tipo
        assert nueva.geometria.equals_exact(vieja.geometria, 0), celda.designacion
    for manzana in fijados.manzanas:
        k = [r.designacion_manzana(i) for i in range(1, len(r.manzanas) + 1)].index(manzana.designacion)
        assert r.manzanas[k].equals_exact(manzana.geometria, 0), manzana.designacion


def test_las_calles_fijadas_conservan_su_eje_y_su_superficie(caso):
    """Cada calle fijada sigue con el mismo eje (o partida en un empalme, con la misma unión) y su
    superficie: los vértices originales, en orden, más los que suman las piezas nuevas sobre sus
    lados, y la misma área."""
    s, o, fijados, r = caso
    fijos = [(t, c) for t, c in zip(r.red.tramos(), r.corredores) if t.fijado]
    # Los ejes salen de las claves de sus nodos (redondeadas al milímetro en el marco de la grilla):
    # con otra orientación, cada punta se corre menos de 1 mm.
    longitud_fija = math.fsum(t.eje.length for t in fijados.tramos)
    assert math.fsum(t.longitud for t, _ in fijos) == pytest.approx(longitud_fija, abs=len(fijos) * 1e-3)
    corredores = [c for _, c in fijos if not c.is_empty]
    for tramo in fijados.tramos:
        if tramo.corredor.is_empty:
            continue
        (corredor,) = [c for c in corredores if shapely.hausdorff_distance(c, tramo.corredor) <= 1e-6]
        assert corredor.area == pytest.approx(tramo.corredor.area, abs=1e-6)
        nuevos = vertices(corredor)
        originales = vertices(tramo.corredor)
        posicion = 0
        for v in originales[:-1]:
            # Cada vértice original aparece, al bit y en el mismo orden.
            posicion = nuevos.index(v, posicion)
        assert all(tramo.corredor.exterior.distance(Point(v)) <= 1e-6 for v in nuevos if v not in set(originales))


# --- El trazado completo ----------------------------------------------------------------------


def test_la_particion_cierra_sobre_el_terreno_entero(caso):
    s, _, _, r = caso
    assert_particion(s, r)


def test_la_red_es_una_sola_pieza_y_llega_a_los_accesos(caso):
    s, _, _, r = caso
    assert r.red.es_conexa(s.accesos)
    assert TipoIncumplimiento.CONECTIVIDAD not in {i.tipo for i in r.incumplimientos}


def test_las_reglas_globales_se_cumplen_sobre_el_trazado_completo(caso):
    """La cesión cuenta el verde computable de las dos partes y el 20 % de avenidas cuenta las
    fijadas (D56)."""
    s, _, _, r = caso
    p = s.parametros
    lotes = math.fsum(l.geometria.area for l in r.lotes)
    assert not faltante_cesion(verde_computable(r.celdas, r.manzanas, p), lotes, p)
    assert porcentaje_avenidas(r.red, p) + 1e-6 >= p.porcentaje_minimo_avenidas
    assert not r.incumplimientos, [(i.tipo.value, i.elemento) for i in r.incumplimientos]


def test_los_lotes_y_las_manzanas_cumplen_forma_art_48_y_art_54(caso):
    s, _, _, r = caso
    p = s.parametros
    circulacion = union_cobertura(r.corredores)
    ejes = IndiceEjes([t.eje for t in r.red.tramos()])
    for lote in r.lotes:
        assert es_lote(lote.geometria, medir(lote.geometria, circulacion, ejes), p), lote.designacion
    for indice in sorted({lote.indice_manzana for lote in r.lotes}):
        manzana = r.manzanas[indice - 1]
        assert alcanza_lado_menor(manzana, p), r.designacion_manzana(indice)
        assert lado_mayor_manzana(manzana) <= p.lado_maximo_sin_pasaje, r.designacion_manzana(indice)


def test_las_manzanas_nuevas_toman_los_numeros_libres(caso):
    _, _, fijados, r = caso
    nombres = [r.designacion_manzana(k) for k in range(1, len(r.manzanas) + 1)]
    numeros = [int(n[1:]) for n in nombres]
    assert numeros == sorted(numeros) and len(set(numeros)) == len(numeros)
    assert {m.designacion for m in fijados.manzanas} <= set(nombres)
    libres = [n for n in range(1, max(numeros) + 1) if f"M{n}" not in {m.designacion for m in fijados.manzanas}]
    assert sorted(set(numeros) - {int(m.designacion[1:]) for m in fijados.manzanas}) == libres[: len(numeros) - len(fijados.manzanas)]


# --- Dominio restante ------------------------------------------------------------------------


def dominio_restante(s, fijados):
    """El dominio restante en el marco de la alternativa, con la cuenta del recálculo."""
    return MotorGeneracion()._en_su_marco(s.terreno, fijados)[5]


def test_un_sector_en_el_medio_deja_un_dominio_con_agujero():
    s, _, fijados, r = recalculado("referencia", ("M6", "M7"), 0)
    (restante,) = poligonos(dominio_restante(s, fijados))
    assert len(restante.interiors) == 1
    assert_particion(s, r)


@lru_cache(maxsize=None)
def franja():
    """Una columna de manzanas del rectangular, de un borde al otro: la más cercana al centro."""
    s, o = origen("referencia")
    marco = MarcoLocal.para(s.terreno, s.estrategia.orientacion)
    nombres = [o.designacion_manzana(k) for k in range(1, len(o.manzanas) + 1)]
    xs = [marco.a_local(m.centroid).x for m in o.manzanas]
    x = min(xs, key=lambda valor: (round(abs(valor), 3), valor))
    return tuple(n for n, valor in zip(nombres, xs) if abs(valor - x) < 5)


def test_una_franja_que_cruza_el_terreno_deja_el_dominio_en_dos_piezas():
    columna = franja()
    assert len(columna) == 4
    for giro in (0, 90):
        s, _, fijados, r = recalculado("referencia", columna, giro)
        assert len(poligonos(dominio_restante(s, fijados))) == 2
        assert_particion(s, r)
        assert r.red.es_conexa(s.accesos)
        assert not r.incumplimientos


# --- Cursos alternativos ---------------------------------------------------------------------


def test_3a_si_lo_fijado_abarca_todo_el_terreno_no_queda_nada_que_recalcular():
    s, o = origen("referencia")
    motor = MotorGeneracion()
    todas = [o.designacion_manzana(k) for k in range(1, len(o.manzanas) + 1)]
    fijados = motor.fijar(o, todas, s.estrategia.orientacion)
    with pytest.raises(SinDominioRestante) as error:
        motor.recalcular(s, fijados)
    assert "abarca todo el terreno" in error.value.causa and error.value.sugerencia
    with pytest.raises(SinDominioRestante):
        motor.exigir_dominio_restante(s.terreno, fijados)


def test_5a_si_lo_nuevo_no_se_puede_conectar_con_lo_fijado_da_error_de_conectividad():
    """Elementos fijados armados a mano: un anillo de lotes, sin calles, rodea una plaza de 100 ×
    100 m en el medio de un terreno de 300 × 300. Lo que se recalcula adentro no tiene acceso ni
    anclaje, y no toca ninguna calle."""
    origen_ = (4_400_000.0, 6_510_000.0)
    terreno = translate(box(0, 0, 300, 300), *origen_)
    anillo = translate(box(60, 60, 240, 240).difference(box(100, 100, 200, 200)), *origen_)
    s = SolicitudGeneracion(
        TipoProyecto.LOTEO,
        terreno,
        (Point(origen_[0] + 150, origen_[1]),),
        PARAMETROS_LOTEO_REFERENCIA,
        JERARQUIAS_REFERENCIA,
        Estrategia(PatronRed.GRILLA, 0.0, 7),
    )
    fijados = ElementosFijados(
        sector=MultiPolygon([anillo]),
        celdas=(CeldaGenerada(anillo, TipoCelda.LOTE, 0.0, 0.0, 1, "M1-L01"),),
        tramos=(),
        anclajes=(),
        manzanas=(ManzanaFijada("M1", anillo),),
        orientacion_marco=0.0,
    )
    with pytest.raises(ErrorConectividad) as error:
        MotorGeneracion().recalcular(s, fijados)
    assert "no se puede conectar" in error.value.causa
    assert error.value.geometria is not None and not error.value.geometria.is_empty


# --- Continuidad y empalmes ------------------------------------------------------------------


def test_con_la_misma_orientacion_la_grilla_nueva_continua_las_calles_fijadas():
    """Ningún tramo fijado se parte: las calles nuevas llegan a los nodos fijados (los anclajes),
    en línea con las fijadas."""
    s, _, fijados, r = recalculado("referencia", ("M2", "M3"), 0)
    fijos = [t for t in r.red.tramos() if t.fijado]
    assert len(fijos) == len(fijados.tramos)
    for anclaje in fijados.anclajes:
        nodo = r.red.nodo(anclaje)
        assert any(not t.fijado for t in r.red.tramos_en(nodo)), nodo


def test_con_otra_orientacion_las_calles_nuevas_se_empalman_en_las_fijadas():
    """Un tramo fijado donde desemboca una calle nueva se parte en dos tramos fijados sobre el mismo
    eje; la superficie entera queda en uno de los dos (D56)."""
    s, _, fijados, r = recalculado("referencia", ("M8", "M9"), 45)
    fijos = [(t, c) for t, c in zip(r.red.tramos(), r.corredores) if t.fijado]
    assert len(fijos) > len(fijados.tramos)
    assert math.fsum(c.area for _, c in fijos) == pytest.approx(math.fsum(t.corredor.area for t in fijados.tramos), abs=1e-6)
    assert any(c.is_empty for _, c in fijos)


def test_el_recalculo_de_un_recalculo_conserva_las_dos_fijaciones():
    """v3 desde v2: se fija una manzana nueva de la v2 junto con las fijadas de la v1, con la
    orientación de la v2 (90° de la v1). Todo vuelve exacto a la grilla del marco de la alternativa
    (el de la v1), que no es el de la estrategia."""
    s2, _, fijados2, v2 = recalculado("referencia", ("M2", "M3"), 90)
    motor = MotorGeneracion()
    nuevas = sorted(
        {v2.designacion_manzana(l.indice_manzana) for l in v2.lotes} - {m.designacion for m in fijados2.manzanas},
        key=lambda d: int(d[1:]),
    )
    fijados3 = motor.fijar(v2, ["M2", "M3", nuevas[0]], fijados2.orientacion_marco)
    s3 = s2
    v3 = motor.recalcular(s3, fijados3)
    assert_particion(s3, v3)
    de_v2 = {c.designacion: c for c in v2.celdas}
    for celda in fijados3.celdas:
        (igual,) = [c for c in v3.celdas if c.designacion == celda.designacion]
        assert igual.geometria.equals_exact(de_v2[celda.designacion].geometria, 0)


# --- Reproducibilidad (RNF05) ----------------------------------------------------------------


def test_el_mismo_recalculo_da_el_mismo_resultado():
    from huella import huella

    s, o = origen("irregular")
    motor = MotorGeneracion()
    fijados = motor.fijar(o, ["M4", "M5"], s.estrategia.orientacion)
    nueva = replace(s, estrategia=replace(s.estrategia, orientacion=s.estrategia.orientacion + 45))
    assert huella(motor.recalcular(nueva, fijados)) == huella(MotorGeneracion().recalcular(nueva, fijados))


def test_el_recalculo_no_depende_del_orden_de_hash_del_proceso():
    from huella import huella

    _, _, _, r = recalculado("referencia", ("M8", "M9"), 45)
    esperada = huella(r)
    carpeta = Path(__file__).parent
    for semilla_hash in ("0", "4242"):
        entorno = {**os.environ, "PYTHONHASHSEED": semilla_hash}
        salida = subprocess.run(
            [sys.executable, str(carpeta / "huella.py"), "recalculo"],
            capture_output=True, text=True, env=entorno, cwd=carpeta, check=True,
        )
        assert salida.stdout.strip() == esperada, f"con PYTHONHASHSEED={semilla_hash} cambia el recálculo"


# --- Barrido de recálculo (`pytest -m barrido`) -----------------------------------------------
# Los 96 terrenos del barrido de la partición: en cada uno se fijan una o dos manzanas con lotes,
# elegidas con una semilla, y se recalcula con la grilla a 45° de la de origen.

GIRO_BARRIDO = 45


@pytest.mark.barrido
@pytest.mark.parametrize("calle_borde", sorted(CalleBorde))
def test_barrido_de_recalculo(capsys, calle_borde):
    """Con la calle de borde en todo el contorno y por lado (D86). En cada terreno, lo fijado no cambia
    (al bit), la partición cierra (con la tolerancia del ruido numérico; el estricto se informa), la red
    es conexa, todo lote cumple la forma y toda manzana con lotes el lado menor del art. 48. Un recálculo
    puede dar el 5.a (la red nueva no se conecta) con su causa, y un incumplimiento solo puede ser de una
    regla global con su causa (cesión o avenidas) o del lado mayor del art. 48: se cuentan e informan.

    Por lado, además, la superficie de calle partida, que el verificador marca (D34): una calle nueva que
    llega a una calle fijada oblicua la toca solo en un punto, con un remanente entre las dos (lo frágil
    del anclaje, D56). Son dos de los 96 (el triángulo a 15° y a 30°): se informan, y más es una
    regresión (D86)."""
    from motor_trazados.semillas import generador
    from test_particion import FORMAS_BARRIDO, ORIENTACIONES_BARRIDO, solicitud

    motor = MotorGeneracion()
    estrictas, sin_conexion, incumplidos, partidas, total = 0, [], [], [], 0
    for k, forma in enumerate(sorted(FORMAS_BARRIDO)):
        for orientacion in ORIENTACIONES_BARRIDO:
            s = solicitud(FORMAS_BARRIDO[forma], orientacion)
            s = replace(s, parametros=replace(s.parametros, calle_borde=calle_borde))
            o = motor.generar(s)
            con_lotes = sorted({o.designacion_manzana(c.indice_manzana) for c in o.lotes}, key=lambda d: int(d[1:]))
            azar = generador(1000 * k + orientacion)
            cuantas = min(len(con_lotes), int(azar.integers(1, 3)))
            elegidas = [con_lotes[int(i)] for i in sorted(azar.choice(len(con_lotes), size=cuantas, replace=False))]
            fijados = motor.fijar(o, elegidas, orientacion)
            nueva = replace(s, estrategia=replace(s.estrategia, orientacion=(orientacion + GIRO_BARRIDO) % 180))
            nombre = f"{forma} a {orientacion}° + {GIRO_BARRIDO}°, {elegidas}"
            total += 1
            try:
                r = motor.recalcular(nueva, fijados)
            except ErrorConectividad as error:
                assert error.causa and error.sugerencia and error.geometria is not None, nombre
                sin_conexion.append(nombre)
                continue
            de_origen = {c.designacion: c for c in o.celdas}
            resultado = {c.designacion: c for c in r.celdas}
            for celda in fijados.celdas:
                assert resultado[celda.designacion].geometria.equals_exact(de_origen[celda.designacion].geometria, 0), nombre
            assert_particion_recalculo(nueva, r)
            try:
                assert_particion(nueva, r)
                estrictas += 1
            except AssertionError:
                pass
            assert r.red.es_conexa(nueva.accesos), nombre
            p = nueva.parametros
            circulacion = union_cobertura(r.corredores)
            ejes = IndiceEjes([t.eje for t in r.red.tramos()])
            for lote in r.lotes:
                assert es_lote(lote.geometria, medir(lote.geometria, circulacion, ejes), p), (nombre, lote.designacion)
            for indice in sorted({lote.indice_manzana for lote in r.lotes}):
                assert alcanza_lado_menor(r.manzanas[indice - 1], p), (nombre, r.designacion_manzana(indice))
            for i in r.incumplimientos:
                if i.tipo in (TipoIncumplimiento.CESION_ESPACIO_VERDE, TipoIncumplimiento.PROPORCION_AVENIDAS):
                    assert "Causa:" in i.detalle, (nombre, i.detalle)
                elif i.tipo is TipoIncumplimiento.CONECTIVIDAD and calle_borde is CalleBorde.POR_LADO:
                    assert "partida" in i.detalle, (nombre, i.detalle)
                    partidas.append(nombre)
                else:
                    assert i.tipo is TipoIncumplimiento.LADO_MAYOR_MANZANA, (nombre, i.tipo, i.detalle)
                incumplidos.append(f"{nombre}: {i.tipo.value}")
    recalculados = total - len(sin_conexion)
    with capsys.disabled():
        print()
        print(
            f"[D56] barrido de recálculo ({calle_borde}): {total} terrenos, {recalculados} recalculados "
            f"({estrictas} con la partición estricta), {len(sin_conexion)} con el 5.a, "
            f"{len(incumplidos)} incumplimientos"
        )
        for linea in sin_conexion + incumplidos:
            print("  ", linea)
    # El 5.a es la excepción, no la regla.
    assert len(sin_conexion) <= total // 20
    assert len(partidas) <= 2, partidas
