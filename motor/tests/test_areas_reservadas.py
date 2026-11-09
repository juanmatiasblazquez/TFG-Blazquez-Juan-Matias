"""Áreas reservadas (CU04, pasos 5 y 6; CU06, paso 4; D59).

El motor descuenta las áreas del dominio, las rodea con una calle de borde y las cierra como piezas
fijas de la partición. Sobre cinco casos (un área en el medio, alineada con la grilla; una en la
esquina, contra el borde; una franja contra un lado oblicuo; dos separadas, y dos que se tocan):

- la partición cierra con las áreas como piezas, y cada área queda como se pidió;
- la red es conexa y llega a los accesos;
- una calle rodea cada área: ninguna celda la toca, salvo contra el límite o contra otra área;
- toda manzana con lotes alcanza el lado menor del art. 48, también las que lindan con el área;
- valen la cesión y el 20 % de avenidas, y los indicadores suman el terreno.

Además: la validación (los 422 del CU04, 6.a), la alineación de la grilla con el área, el recálculo
con áreas (CU09) y el barrido (`pytest -m barrido`).
"""

import math
from dataclasses import replace
from functools import lru_cache

import pytest
import shapely
from contorno import con_contorno
from shapely import LineString, Point, Polygon, box
from shapely.affinity import rotate, translate

from motor_trazados import (
    ErrorConectividad,
    MotorGeneracion,
    SolicitudInvalida,
    TerrenoSinLotes,
    TipoCelda,
    TipoIncumplimiento,
)
from motor_trazados.contrato import validar_reservadas
from motor_trazados.coordenadas import a_metros
from motor_trazados.geometria import DESVIO_ALINEACION, TOLERANCIA, IndiceEjes, medir, union_cobertura
from motor_trazados.referencia import CENTRO, ROTACION, solicitud_caso, srid_referencia
from motor_trazados.verificador import alcanza_lado_menor, es_lote
from particion import assert_particion, assert_particion_recalculo

_CENTRO_M = a_metros(Point(CENTRO), srid_referencia())


def ubicar(geometria):
    """De las coordenadas de un caso de referencia (alrededor de 0, 0) al sistema de cálculo."""
    return translate(rotate(geometria, ROTACION, origin=(0, 0)), _CENTRO_M.x, _CENTRO_M.y)


# Nombre → (caso de referencia, áreas en las coordenadas del caso; None: las del caso).
CASOS = {
    "centro": ("reservada_centro", None),
    "esquina": ("referencia", (box(150, -135, 240, -40),)),
    "franja": ("reservada_borde", None),
    "varias": ("referencia", (box(-200, 9, -110, 59), box(60, -51, 160, -1))),
    "se_tocan": ("referencia", (box(-60, -51, 0, -1), box(0, -51, 60, -1))),
}


@lru_cache(maxsize=None)
def generado(nombre: str, asignar: bool = True):
    caso, areas = CASOS[nombre]
    s = solicitud_caso(caso)
    if areas is not None:
        s = replace(s, reservadas=tuple(ubicar(a) for a in areas))
    return s, MotorGeneracion(asignar_espacios_verdes=asignar).generar(s)


@pytest.fixture(scope="module", params=sorted(CASOS))
def caso(request):
    return (request.param, *generado(request.param))


# --- La partición y el área ---------------------------------------------------------------------


def test_la_particion_cierra_con_las_areas_como_piezas(caso):
    nombre, s, r = caso
    assert len(r.reservadas) == len(s.reservadas), nombre
    assert_particion(s, r)


def test_cada_area_queda_como_se_pidio(caso):
    """La pieza de cada área es la pedida: solo suma puntos sobre sus lados, donde la tocan las
    calles, y se aparta a lo sumo la grilla de 1 mm del marco local."""
    nombre, s, r = caso
    for pedida, pieza in zip(s.reservadas, r.reservadas, strict=True):
        assert shapely.symmetric_difference(pedida, pieza).area <= pedida.length * 1e-3, nombre
        assert shapely.hausdorff_distance(pedida.exterior, pieza.exterior) <= 2e-3, nombre
    assert r.indicadores.superficie_reservada == pytest.approx(math.fsum(a.area for a in r.reservadas))


def test_la_red_es_conexa_y_llega_a_los_accesos(caso):
    nombre, s, r = caso
    assert r.red.es_conexa(s.accesos), nombre
    assert TipoIncumplimiento.CONECTIVIDAD not in {i.tipo for i in r.incumplimientos}, nombre


def test_una_calle_rodea_cada_area(caso):
    """Ninguna celda comparte un lado con un área, y todo el borde del área que no está sobre el
    límite del terreno ni contra otra área toca una calle (D59)."""
    nombre, s, r = caso
    circulacion = union_cobertura(r.corredores)
    for k, area in enumerate(r.reservadas):
        for celda in r.celdas:
            assert celda.geometria.boundary.intersection(area.boundary).length <= TOLERANCIA, (nombre, celda.designacion)
        otras = [s.terreno.exterior, *(a.exterior for j, a in enumerate(r.reservadas) if j != k)]
        libre = area.exterior.difference(shapely.union_all(otras).buffer(TOLERANCIA))
        assert circulacion.buffer(TOLERANCIA).covers(libre), (nombre, f"R{k + 1}")


def test_toda_manzana_con_lotes_alcanza_el_lado_menor_tambien_junto_al_area(caso):
    nombre, s, r = caso
    p = s.parametros
    circulacion = union_cobertura(r.corredores)
    ejes = IndiceEjes([t.eje for t in r.red.tramos()])
    for lote in r.lotes:
        assert es_lote(lote.geometria, medir(lote.geometria, circulacion, ejes), p), (nombre, lote.designacion)
    con_lotes = sorted({lote.indice_manzana for lote in r.lotes})
    for indice in con_lotes:
        assert alcanza_lado_menor(r.manzanas[indice - 1], p), (nombre, f"M{indice}")
    # Las que lindan con un área (a una calle de distancia) tienen lotes: la calle de borde les da dos
    # fondos. En la franja, con la calle de borde por lado, la calle de la muesca del irregular se alinea
    # con la grilla (D86), la grilla se corre y junto al área quedan solo las puntas del lado oblicuo; con
    # la calle de borde en todo el contorno también tiene (la prueba siguiente).
    assert lindantes_con_lotes(s, r) or nombre == "franja", nombre


def lindantes_con_lotes(s, r) -> list[int]:
    """Las manzanas con lotes a una calle de distancia de un área (con el desvío de la alineación)."""
    ancho = max(j.ancho_total for j in s.jerarquias) + DESVIO_ALINEACION + TOLERANCIA
    lindantes = [k for k, m in enumerate(r.manzanas, 1) if any(m.distance(a) <= ancho for a in r.reservadas)]
    assert lindantes
    return sorted(set(lindantes) & {lote.indice_manzana for lote in r.lotes})


def test_en_la_franja_con_la_calle_de_borde_en_todo_el_contorno_lindan_manzanas_con_lotes():
    s = con_contorno(generado("franja")[0])
    assert lindantes_con_lotes(s, MotorGeneracion().generar(s))


def test_valen_la_cesion_el_art_12_y_el_art_48(caso):
    nombre, s, r = caso
    assert r.incumplimientos == (), (nombre, [(i.tipo.value, i.elemento, i.detalle) for i in r.incumplimientos])
    assert r.indicadores.porcentaje_cesion >= s.parametros.porcentaje_espacio_verde - 1e-6, nombre
    assert r.indicadores.porcentaje_avenidas >= s.parametros.porcentaje_minimo_avenidas - 1e-6, nombre


def test_los_indicadores_suman_el_terreno_y_el_area_no_es_verde(caso):
    """Lotes, calles, verde, libre y áreas reservadas suman el terreno (D59), y los porcentajes son
    sobre la superficie disponible, el terreno menos las áreas (D61). El área no es una celda, así
    que no cuenta para la cesión."""
    nombre, s, r = caso
    i = r.indicadores
    lotes = math.fsum(c.geometria.area for c in r.lotes)
    calles = math.fsum(c.area for c in r.corredores)
    total = lotes + calles + i.superficie_espacio_verde + i.superficie_espacio_libre + i.superficie_reservada
    assert total == pytest.approx(s.terreno.area, abs=s.terreno.length * 1e-3), nombre
    assert i.superficie_terreno == pytest.approx(s.terreno.area), nombre
    disponible = s.terreno.area - math.fsum(a.area for a in r.reservadas)
    assert i.superficie_reservada > 0, nombre
    assert i.superficie_disponible == pytest.approx(disponible), nombre
    assert i.porcentaje_circulacion == pytest.approx(100 * calles / disponible), nombre
    assert i.porcentaje_espacio_verde == pytest.approx(100 * i.superficie_espacio_verde / disponible), nombre
    libre = 100 * i.superficie_espacio_libre / disponible
    porcentajes = 100 * lotes / disponible + i.porcentaje_circulacion + i.porcentaje_espacio_verde + libre
    assert porcentajes == pytest.approx(100, abs=0.01), nombre
    assert not any(c.geometria.intersection(a).area > 1e-3 for c in r.celdas for a in r.reservadas), nombre


# --- La alineación con la grilla ------------------------------------------------------------------


def test_en_el_centro_las_manzanas_que_lindan_con_el_area_son_filas_de_lotes():
    """El área del medio ocupa el lugar de una manzana y sus cuatro lados son paralelos a la grilla:
    sus calles siguen como calles de la grilla, y las manzanas de alrededor son filas de dos fondos,
    sin remanentes (sin el asignador, que después puede poner el verde junto al área)."""
    s, r = generado("centro", asignar=False)
    ancho = max(j.ancho_total for j in s.jerarquias) + DESVIO_ALINEACION + TOLERANCIA
    (area,) = r.reservadas
    lindantes = [k for k, m in enumerate(r.manzanas, 1) if m.distance(area) <= ancho]
    assert len(lindantes) >= 4
    for k in lindantes:
        tipos = {c.tipo for c in r.celdas if c.indice_manzana == k}
        assert tipos == {TipoCelda.LOTE}, f"M{k}: {tipos}"
    assert r.indicadores.superficie_espacio_libre == 0


def test_dos_areas_que_se_tocan_no_llevan_calle_entre_ellas():
    s, r = generado("se_tocan")
    a, b = r.reservadas
    compartido = a.boundary.intersection(b.boundary)
    assert compartido.length > 40
    circulacion = union_cobertura(r.corredores)
    assert circulacion.intersection(compartido.buffer(TOLERANCIA)).area <= 1e-3


def test_sin_areas_la_generacion_no_cambia_de_camino():
    """Sin áreas, el resultado no tiene piezas reservadas y la superficie reservada es 0: el motor
    sigue el camino de siempre (el marco sale del terreno, que es el dominio)."""
    s = solicitud_caso("referencia")
    r = MotorGeneracion().generar(s)
    assert r.reservadas == () and r.indicadores.superficie_reservada == 0
    assert r.indicadores.cantidad_celdas == 261


# --- La validación (CU04, 6.a; los 422 de la API) -------------------------------------------------


def _con(areas, base="referencia", accesos=None):
    s = solicitud_caso(base)
    s = replace(s, reservadas=tuple(ubicar(a) for a in areas))
    if accesos is not None:
        s = replace(s, accesos=tuple(ubicar(a) for a in accesos))
    return s


def _problemas(s):
    return [(p.campo, p.mensaje) for p in s.validar()]


def test_un_area_que_sale_del_terreno_se_rechaza():
    (problema,) = _problemas(_con([box(200, 0, 280, 60)]))
    assert problema[0] == "reservadas[0]" and "sale del terreno" in problema[1]


def test_dos_areas_que_se_superponen_se_rechazan_y_dos_que_se_tocan_no():
    (problema,) = _problemas(_con([box(-60, -50, 20, 0), box(0, -50, 60, 0)]))
    assert problema[0] == "reservadas[1]" and "R1 y R2 se superponen" in problema[1]
    assert _problemas(_con([box(-60, -50, 0, 0), box(0, -50, 60, 0)])) == []


def test_areas_que_cubren_todo_el_terreno_se_rechazan():
    (problema,) = _problemas(_con([box(-240, -135, 0, 135), box(0, -135, 240, 135)]))
    assert problema == ("reservadas", "Las áreas reservadas cubren todo el terreno: no queda dónde lotear.")


def test_un_acceso_sobre_un_tramo_del_borde_tomado_por_un_area_se_rechaza():
    # A1 está sobre el lado sur en x = -60: una franja contra ese lado lo toma.
    (problema,) = _problemas(_con([box(-100, -135, 0, -105)]))
    assert problema[0] == "accesos[0]" and "R1" in problema[1]


def test_un_area_con_un_hueco_se_rechaza():
    con_hueco = Polygon(box(-60, -50, 60, 50).exterior, [box(-20, -20, 20, 20).exterior.coords])
    (problema,) = _problemas(_con([con_hueco]))
    assert problema[0] == "reservadas[0]" and "huecos" in problema[1]


def test_una_parte_del_terreno_sin_acceso_se_rechaza():
    """Una franja que cruza el terreno de norte a sur lo parte en dos, y los dos accesos quedan del
    lado oeste (A1 en el sur, en x = -60) y del este (A2): con la franja entre x = -40 y 0, el oeste
    tiene A1 y el este A2. Con los dos accesos al este, el oeste queda sin acceso."""
    franja = box(-40, -135, 0, 135)
    assert _problemas(_con([franja])) == []
    sin_oeste = _con([franja], accesos=[Point(60, -135), Point(240, 33.75)])
    (problema,) = _problemas(sin_oeste)
    assert problema[0] == "reservadas" and "sin ningún acceso" in problema[1]
    with pytest.raises(SolicitudInvalida):
        MotorGeneracion().generar(sin_oeste)


def test_la_validacion_es_la_misma_regla_que_usa_la_api():
    """`validar_reservadas` es pública: la API la llama al registrar el terreno (copia única)."""
    s = _con([box(200, 0, 280, 60)])
    assert [p.campo for p in validar_reservadas(s.reservadas, s.terreno, s.accesos)] == ["reservadas[0]"]


# --- El recálculo con áreas (CU09) ----------------------------------------------------------------


@pytest.mark.parametrize("giro", [0, 90])
def test_el_recalculo_conserva_las_areas_y_lo_fijado(giro):
    """Se fijan dos manzanas que lindan con el área del medio y se recalcula el resto con la misma
    orientación y a 90°: las áreas quedan iguales, lo fijado no cambia y la partición cierra."""
    s, o = generado("centro")
    (area,) = o.reservadas
    ancho = max(j.ancho_total for j in s.jerarquias) + DESVIO_ALINEACION + TOLERANCIA
    lindantes = sorted(
        {o.designacion_manzana(c.indice_manzana) for c in o.lotes if o.manzanas[c.indice_manzana - 1].distance(area) <= ancho},
        key=lambda d: int(d[1:]),
    )[:2]
    motor = MotorGeneracion()
    fijados = motor.fijar(o, lindantes, s.estrategia.orientacion)
    nueva = replace(s, estrategia=replace(s.estrategia, orientacion=(s.estrategia.orientacion + giro) % 180))
    r = motor.recalcular(nueva, fijados)
    de_origen = {c.designacion: c for c in o.celdas}
    for celda in fijados.celdas:
        assert {c.designacion: c for c in r.celdas}[celda.designacion].geometria.equals_exact(
            de_origen[celda.designacion].geometria, 0
        )
    assert shapely.symmetric_difference(r.reservadas[0], s.reservadas[0]).area <= s.reservadas[0].length * 1e-3
    if giro == 0:
        assert_particion(nueva, r)
    else:
        assert_particion_recalculo(nueva, r)
    assert r.red.es_conexa(nueva.accesos)
    for i in r.incumplimientos:
        assert "Causa:" in i.detalle or i.tipo is TipoIncumplimiento.LADO_MAYOR_MANZANA, (i.tipo, i.detalle)


# --- Barrido con áreas (`pytest -m barrido`) -------------------------------------------------------
# Los 96 terrenos del barrido de la partición, con áreas elegidas con una semilla: un rectángulo
# adentro alineado con la grilla, uno oblicuo, una franja contra un lado o dos rectángulos que se
# tocan.

TIPOS_BARRIDO = ("alineada", "oblicua", "franja", "se_tocan")


def areas_del_barrido(terreno: Polygon, orientacion: float, acceso: Point, azar, tipo: str) -> list[Polygon] | None:
    """Áreas de entre el 3 y el 8 % del terreno, dentro de él, elegidas con `azar`. `None` si no hay
    lugar."""
    superficie = terreno.area * float(azar.uniform(0.03, 0.08))
    if tipo == "franja":
        # Contra el lado más largo que no tiene el acceso, de 15 a 30 m de ancho.
        lados = sorted(
            (LineString([a, b]) for a, b in zip(terreno.exterior.coords, terreno.exterior.coords[1:])),
            key=lambda l: (-round(l.length, 3), round(l.centroid.x, 3), round(l.centroid.y, 3)),
        )
        lado = next((l for l in lados if l.distance(acceso) > 1 and l.length >= 80), None)
        if lado is None:
            return None
        ancho = float(azar.uniform(15, 30))
        franja = lado.buffer(ancho, single_sided=True, cap_style="flat").intersection(terreno)
        if franja.area < 100 or franja.geom_type != "Polygon":
            franja = lado.buffer(-ancho, single_sided=True, cap_style="flat").intersection(terreno)
        return [franja] if franja.geom_type == "Polygon" and franja.area >= 100 else None
    lado = math.sqrt(superficie)
    proporcion = float(azar.uniform(0.6, 1.6))
    ancho, alto = lado * proporcion, lado / proporcion
    giro = orientacion if tipo != "oblicua" else orientacion + float(azar.uniform(10, 80))
    adentro = terreno.buffer(-30)
    if adentro.is_empty:
        return None
    minx, miny, maxx, maxy = adentro.bounds
    for _ in range(20):
        centro = Point(float(azar.uniform(minx, maxx)), float(azar.uniform(miny, maxy)))
        if tipo == "se_tocan":
            partes = [box(-ancho / 2, -alto / 2, 0, alto / 2), box(0, -alto / 2, ancho / 2, alto / 2)]
        else:
            partes = [box(-ancho / 2, -alto / 2, ancho / 2, alto / 2)]
        areas = [translate(rotate(p, giro, origin=(0, 0)), centro.x, centro.y) for p in partes]
        if all(adentro.covers(a) for a in areas):
            return areas
    return None


@pytest.mark.barrido
def test_barrido_con_areas_reservadas(capsys):
    """En cada terreno, con sus áreas: la partición cierra (el estricto se informa), la red es
    conexa, toda celda está fuera de las áreas, todo lote cumple la forma y toda manzana con lotes el
    lado menor. Una generación puede dar un 422 (sin lugar para el área, una parte sin acceso, la red
    que no conecta o sin lotes) con su causa: se cuentan, y también los lotes contra el mismo terreno
    sin áreas."""
    from motor_trazados.semillas import generador
    from test_particion import FORMAS_BARRIDO, ORIENTACIONES_BARRIDO, solicitud

    motor = MotorGeneracion()
    total, estrictas, sin_lugar, rechazadas, incumplidos = 0, 0, [], [], []
    lotes_con, lotes_sin = 0, 0
    por_tipo: dict[str, list[int]] = {t: [0, 0] for t in TIPOS_BARRIDO}
    for k, forma in enumerate(sorted(FORMAS_BARRIDO)):
        for orientacion in ORIENTACIONES_BARRIDO:
            base = solicitud(FORMAS_BARRIDO[forma], orientacion)
            azar = generador(2000 * k + orientacion)
            tipo = TIPOS_BARRIDO[(k + orientacion // 15) % len(TIPOS_BARRIDO)]
            nombre = f"{forma} a {orientacion}°, {tipo}"
            areas = areas_del_barrido(base.terreno, orientacion, base.accesos[0], azar, tipo)
            if areas is None:
                sin_lugar.append(nombre)
                continue
            s = replace(base, reservadas=tuple(areas))
            total += 1
            problemas = s.validar()
            if problemas:
                rechazadas.append(f"{nombre}: {problemas[0].mensaje}")
                continue
            try:
                r = motor.generar(s)
            except (ErrorConectividad, TerrenoSinLotes) as error:
                assert error.causa and error.sugerencia, nombre
                rechazadas.append(f"{nombre}: {error.causa}")
                continue
            try:
                assert_particion(s, r)
                estrictas += 1
            except AssertionError:
                assert_particion_recalculo(s, r)
            assert r.red.es_conexa(s.accesos), nombre
            p = s.parametros
            circulacion = union_cobertura(r.corredores)
            ejes = IndiceEjes([t.eje for t in r.red.tramos()])
            for celda in r.celdas:
                assert all(celda.geometria.intersection(a).area <= 1e-3 for a in r.reservadas), (nombre, celda.designacion)
            for lote in r.lotes:
                assert es_lote(lote.geometria, medir(lote.geometria, circulacion, ejes), p), (nombre, lote.designacion)
            for indice in sorted({lote.indice_manzana for lote in r.lotes}):
                assert alcanza_lado_menor(r.manzanas[indice - 1], p), (nombre, f"M{indice}")
            for i in r.incumplimientos:
                if i.tipo in (TipoIncumplimiento.CESION_ESPACIO_VERDE, TipoIncumplimiento.PROPORCION_AVENIDAS):
                    assert "Causa:" in i.detalle, (nombre, i.detalle)
                else:
                    assert i.tipo is TipoIncumplimiento.LADO_MAYOR_MANZANA, (nombre, i.tipo, i.detalle)
                incumplidos.append(f"{nombre}: {i.tipo.value}")
            sin = motor.generar(base)
            lotes_con += r.indicadores.cantidad_celdas
            lotes_sin += sin.indicadores.cantidad_celdas
            por_tipo[tipo][0] += 1
            por_tipo[tipo][1] += r.indicadores.cantidad_celdas
    generadas = total - len(rechazadas)
    with capsys.disabled():
        print()
        print(
            f"[D59] barrido con áreas: {total} terrenos con áreas ({len(sin_lugar)} sin lugar para el área), "
            f"{generadas} generados ({estrictas} con la partición estricta), {len(rechazadas)} con 422, "
            f"{len(incumplidos)} incumplimientos; lotes {lotes_con} contra {lotes_sin} sin áreas "
            f"({100 * (lotes_con - lotes_sin) / max(lotes_sin, 1):+.1f} %)"
        )
        print("   por tipo (generados, lotes): " + ", ".join(f"{t} {n} / {l}" for t, (n, l) in por_tipo.items()))
        for linea in rechazadas + incumplidos:
            print("  ", linea)
    # Un 422 es la excepción, no la regla.
    assert len(rechazadas) <= total // 10
