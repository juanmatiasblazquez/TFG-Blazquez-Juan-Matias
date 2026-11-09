"""La partición cierra exacta (D39): calles, lotes y remanentes cubren el terreno completo, sin
huecos ni superposiciones, sobre un barrido de formas y orientaciones.

Hasta el motor 0.3.1 esto fallaba de dos maneras:
- el contorno de la cesión se armaba volviendo a ajustar a la grilla de 1 mm las piezas ya
  pasadas al sistema de cálculo, y abría microhuecos (las líneas rojas sueltas del portal);
- con la grilla oblicua, el subdivisor cortaba en el marco de cada manzana y dejaba astillas
  de hasta 0,2 mm entre lotes y calles.

Las formas están en metros alrededor de un punto con coordenadas del orden de las de la faja 4,
como las del sistema de cálculo.
"""

import math
from dataclasses import replace

import pytest
from shapely import Point, Polygon, box
from shapely.affinity import rotate, translate

from motor_trazados import CalleBorde, Estrategia, MotorGeneracion, PatronRed, SolicitudGeneracion, TipoProyecto
from motor_trazados.valores_referencia import JERARQUIAS_REFERENCIA, PARAMETROS_LOTEO_REFERENCIA
from particion import assert_particion

ORIGEN = (4_400_000.0, 6_510_000.0)
ORIENTACIONES = (0, 20, 45, 110, 160)


def _muchos_vertices(n: int = 48) -> Polygon:
    """Un óvalo ondulado de 48 vértices, de unos 520 × 400 m."""
    puntos = []
    for k in range(n):
        t = 2 * math.pi * k / n
        onda = 1 + 0.12 * math.sin(5 * t)
        puntos.append((260 * math.cos(t) * onda, 200 * math.sin(t) * onda))
    return Polygon(puntos)


FORMAS = {
    "convexo": Polygon([(0, 0), (380, -40), (520, 150), (300, 330), (40, 260)]),
    "L": box(0, 0, 400, 150).union(box(0, 0, 150, 350)),
    "U": box(0, 0, 450, 350).difference(box(150, 120, 300, 400)),
    "U con ranura angosta": box(0, 0, 450, 350).difference(box(200, 100, 230, 400)),
    "triangulo de 24°": Polygon([(0, 0), (600, 0), (100, 220)]),
    "48 vertices": _muchos_vertices(),
}


def acceso_en_el_lado_mayor(terreno: Polygon) -> Point:
    """El punto medio del lado más largo: un acceso en una esquina con la grilla oblicua puede
    dar un error de conectividad, que es otra prueba (test_generacion_loteo)."""
    coordenadas = list(terreno.exterior.coords)
    a, b = max(zip(coordenadas, coordenadas[1:]), key=lambda lado: (round(math.dist(*lado), 6), lado))
    return Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def solicitud(terreno: Polygon, orientacion: float) -> SolicitudGeneracion:
    """El terreno llevado al origen, con un acceso en el medio de su lado mayor."""
    terreno = translate(terreno, *ORIGEN)
    return SolicitudGeneracion(
        TipoProyecto.LOTEO,
        terreno,
        (acceso_en_el_lado_mayor(terreno),),
        PARAMETROS_LOTEO_REFERENCIA,
        JERARQUIAS_REFERENCIA,
        Estrategia(PatronRed.GRILLA, float(orientacion), 7),
    )


@pytest.mark.parametrize("orientacion", ORIENTACIONES)
@pytest.mark.parametrize("forma", sorted(FORMAS))
def test_la_particion_cierra_en_formas_irregulares(forma, orientacion):
    s = solicitud(FORMAS[forma], orientacion)
    assert_particion(s, MotorGeneracion().generar(s))


@pytest.mark.parametrize("giro", [15, 60, 110])
@pytest.mark.parametrize("oblicua", [False, True])
def test_la_particion_cierra_en_rectangulos_rotados(giro, oblicua):
    """La grilla paralela al rectángulo, o 35° oblicua, que es donde el subdivisor dejaba
    astillas."""
    s = solicitud(rotate(box(0, 0, 480, 270), giro, origin=(0, 0)), giro + (35 if oblicua else 0))
    assert_particion(s, MotorGeneracion().generar(s))


def test_una_manzana_astilla_que_se_queda_sin_caras_desaparece():
    """En el triángulo de 24° con la grilla a 75°, el cierre le da a sus vecinas todas las caras
    de una manzana astilla. Hasta el motor 0.4.0 quedaba como una manzana vacía, sin celdas (lo
    encontró el barrido largo; D44)."""
    s = solicitud(FORMAS["triangulo de 24°"], 75)
    resultado = MotorGeneracion().generar(s)
    assert all(not manzana.is_empty for manzana in resultado.manzanas)
    assert_particion(s, resultado)


# --- Barrido largo: 8 formas × 12 orientaciones (D40, D44, D50) --------------------------------
# No corre por defecto (tarda más de un minuto): `docker compose run --rm motor pytest -m barrido`.

FORMAS_BARRIDO = {
    **FORMAS,
    "esquina cerrada": Polygon([(0, 0), (520, 0), (520, 90), (0, 300)]),
    "hexagono": Polygon([(-320, -120), (240, -120), (240, 150), (120, 150), (120, 60), (20, 60)]),
}
ORIENTACIONES_BARRIDO = tuple(range(0, 180, 15))


@pytest.mark.barrido
@pytest.mark.parametrize("calle_borde", sorted(CalleBorde))
@pytest.mark.parametrize("orientacion", ORIENTACIONES_BARRIDO)
@pytest.mark.parametrize("forma", sorted(FORMAS_BARRIDO))
def test_barrido_con_el_verde_asignado(forma, orientacion, calle_borde):
    """En cada terreno, con la calle de borde en todo el contorno y por lado (D86):
    - la partición cierra con el verde asignado;
    - todo verde cumple sus criterios, y la cesión se cumple o queda incumplida con su causa y su
      sugerencia (D44);
    - todo lote cumple el criterio de forma (D43);
    - toda manzana con lotes cumple el art. 48 de la Ord. 8060: lado menor de 42 m y lado mayor sin
      pasaje peatonal (D50);
    - las avenidas llegan al 20 % de la longitud de calles (Ley 4146, art. 12; D48) en todos: el
      triángulo de 24° a 15°, el único que no llegaba, llega con dos transversales de más (D53)."""
    from motor_trazados import TipoCelda, TipoIncumplimiento
    from motor_trazados.geometria import IndiceEjes, medir, union_cobertura
    from motor_trazados.remanentes import es_espacio_verde
    from motor_trazados.verificador import alcanza_lado_menor, es_lote, lado_mayor_manzana

    s = solicitud(FORMAS_BARRIDO[forma], orientacion)
    s = replace(s, parametros=replace(s.parametros, calle_borde=calle_borde))
    resultado = MotorGeneracion().generar(s)
    assert_particion(s, resultado)
    p = s.parametros
    circulacion = union_cobertura(resultado.corredores)
    ejes = IndiceEjes([tramo.eje for tramo in resultado.red.tramos()])
    for celda in resultado.celdas:
        if celda.tipo is TipoCelda.ESPACIO_VERDE:
            assert es_espacio_verde(celda.geometria, circulacion, p), celda.designacion
        if celda.tipo is TipoCelda.LOTE:
            assert es_lote(celda.geometria, medir(celda.geometria, circulacion, ejes), p), celda.designacion
    for indice in sorted({lote.indice_manzana for lote in resultado.lotes}):
        manzana = resultado.manzanas[indice - 1]
        assert alcanza_lado_menor(manzana, p), f"M{indice}"
        assert lado_mayor_manzana(manzana) <= p.lado_maximo_sin_pasaje, f"M{indice}"
    tipos = {i.tipo for i in resultado.incumplimientos}
    assert not tipos & {TipoIncumplimiento.LADO_MENOR_MANZANA, TipoIncumplimiento.LADO_MAYOR_MANZANA}
    for incumplimiento in resultado.incumplimientos:
        if incumplimiento.tipo in (TipoIncumplimiento.CESION_ESPACIO_VERDE, TipoIncumplimiento.PROPORCION_AVENIDAS):
            assert "Causa:" in incumplimiento.detalle and "Sugerencia:" in incumplimiento.detalle
    assert TipoIncumplimiento.PROPORCION_AVENIDAS not in tipos
    assert resultado.indicadores.porcentaje_avenidas >= 20 - 1e-6


def test_la_particion_del_caso_de_referencia(referencia, resultado_referencia):
    assert_particion(referencia, resultado_referencia)


def test_la_particion_del_caso_irregular(irregular, resultado_irregular):
    assert_particion(irregular, resultado_irregular)


def test_el_contorno_de_la_cesion_no_tiene_lineas_sueltas(resultado_referencia_sin_asignador):
    """El incumplimiento de la cesión se dibuja con el borde exterior del terreno: una sola
    línea, sin los anillos interiores que eran las líneas rojas sueltas del portal. Sin el
    asignador, el rectangular la incumple (D44)."""
    (cesion,) = [i for i in resultado_referencia_sin_asignador.incumplimientos if i.elemento == "terreno"]
    assert cesion.geometria.geom_type == "MultiLineString"
    assert len(cesion.geometria.geoms) == 1
