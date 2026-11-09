"""El invariante de la partición (D39), para usar en cualquier prueba de punta a punta.

Calles, celdas (lotes, espacios verdes y libres) y áreas reservadas (D59) son una partición del
terreno:

- (a) no se superponen;
- (b) su unión es un solo polígono, sin huecos, que se aparta del borde del terreno a lo sumo
  3 × √2 / 2 mm (2,1 mm): un vértice puesto sobre un lado oblicuo del terreno pasa por tres
  ajustes a la grilla de 1 mm, de hasta √2 / 2 mm cada uno: el del terreno al llevarlo al marco
  local, el del recorte que lo crea y el del cierre, que noda los bordes (D25, D39). Hasta la
  sesión 7 la cota era √2 mm, la de dos ajustes; con la calle de borde, que pone muchos vértices
  sobre el límite, el barrido llegó a 1,58 mm (D50);
- (c) la suma de sus superficies es la del terreno, salvo esa misma banda de 1 mm;
- (d) los bordes de piezas vecinas coinciden exactamente, y no queda ningún hueco angosto entre
  ellas;
- (e) cada manzana es la unión de sus celdas.
"""

import math
from collections import defaultdict

import shapely
from shapely import Polygon, STRtree

from motor_trazados.geometria import AREA_RUIDO, RESOLUCION, TOLERANCIA, union_cobertura

# Lo que puede sumar el área de las intersecciones entre piezas vecinas: ruido de coma flotante
# de la transformación rígida, nada más.
SOLAPE_MAXIMO = 1e-6
# Lo que la unión de las piezas puede apartarse del borde del terreno: tres ajustes a la grilla.
DESVIO_BORDE_MAXIMO = 3 * math.sqrt(2) / 2 * RESOLUCION


def piezas(resultado) -> list:
    return (
        [c for c in resultado.corredores if not c.is_empty]
        + [c.geometria for c in resultado.celdas]
        + list(resultado.reservadas)
    )


def assert_particion(solicitud, resultado) -> None:
    terreno = solicitud.terreno
    todas = piezas(resultado)

    # (a) Ningún par de piezas se superpone.
    arbol = STRtree(todas)
    izquierda, derecha = arbol.query(todas, predicate="intersects")
    solape = math.fsum(
        shapely.intersection(todas[i], todas[j]).area for i, j in zip(izquierda, derecha) if i < j
    )
    assert solape <= SOLAPE_MAXIMO, f"las piezas se superponen en {solape:.6f} m²"

    # (b) La unión es el terreno: una sola pieza, sin anillos interiores.
    union = shapely.union_all(todas)
    assert isinstance(union, Polygon), f"la unión tiene {shapely.get_num_geometries(union)} partes"
    assert not union.interiors, f"la unión tiene {len(union.interiors)} hueco(s)"
    assert shapely.hausdorff_distance(union.exterior, terreno.exterior) <= DESVIO_BORDE_MAXIMO

    # (c) La suma de las superficies es la del terreno, salvo la banda de la grilla en su borde.
    suma = math.fsum(p.area for p in todas)
    assert abs(suma - terreno.area) <= terreno.length * RESOLUCION, f"Σ áreas − terreno = {suma - terreno.area:+.4f} m²"

    # (d) Los bordes vecinos coinciden. Con `gap_width`, GEOS marca también los escalones de
    # menos de 1 mm que la grilla deja en un borde oblicuo del terreno, que se ven como huecos
    # angostos hacia afuera: esos se aceptan; un hueco entre piezas, no.
    assert shapely.coverage_is_valid(todas), "hay bordes vecinos que no coinciden"
    borde_exterior = union.exterior.buffer(RESOLUCION / 10)
    for pieza, aristas in zip(todas, shapely.coverage_invalid_edges(todas, gap_width=TOLERANCIA)):
        if aristas is not None and not aristas.is_empty:
            assert borde_exterior.covers(aristas), f"hueco angosto junto a la pieza {pieza.wkt[:80]}…"

    # (e) Cada manzana es la unión de sus celdas.
    por_manzana = defaultdict(list)
    for celda in resultado.celdas:
        por_manzana[celda.indice_manzana].append(celda.geometria)
    assert sorted(por_manzana) == list(range(1, len(resultado.manzanas) + 1))
    for indice, manzana in enumerate(resultado.manzanas, 1):
        assert isinstance(manzana, Polygon), f"M{indice} no es un polígono"
        diferencia = shapely.symmetric_difference(manzana, union_cobertura(por_manzana[indice])).area
        assert diferencia <= SOLAPE_MAXIMO, f"las celdas de M{indice} no dan la manzana ({diferencia:.6f} m²)"


# --- El recálculo (CU09, D56) ----------------------------------------------------------------
# Con otra orientación, donde una calle fijada oblicua se cruza con varias nuevas, el ajuste a la
# grilla de 1 mm puede dejar defectos de menos de un milímetro de ancho entre lo fijado y lo nuevo
# (en el barrido, algunos de cada cien recálculos). La versión estricta es `assert_particion`; esta
# los acepta mientras no pasen el ruido numérico del motor (`AREA_RUIDO`, 0,01 m², D25): un solape,
# un hueco o una diferencia de manzana que el motor mismo descartaría como residuo de un overlay.
DEFECTO_MAXIMO = AREA_RUIDO


def defectos_de_particion(solicitud, resultado) -> dict:
    """Lo que la partición de un recálculo se aparta de una cobertura exacta: el área de los solapes,
    la de los huecos, cuántos bordes vecinos no coinciden y la diferencia de cada manzana con sus
    celdas."""
    todas = piezas(resultado)
    arbol = STRtree(todas)
    izquierda, derecha = arbol.query(todas, predicate="intersects")
    solape = math.fsum(shapely.intersection(todas[i], todas[j]).area for i, j in zip(izquierda, derecha) if i < j)
    union = shapely.union_all(todas)
    huecos = math.fsum(Polygon(anillo).area for parte in shapely.get_parts(union) for anillo in parte.interiors)
    bordes = sum(
        1 for aristas in shapely.coverage_invalid_edges(todas) if aristas is not None and not aristas.is_empty
    )
    por_manzana = defaultdict(list)
    for celda in resultado.celdas:
        por_manzana[celda.indice_manzana].append(celda.geometria)
    manzanas = max(
        (
            shapely.symmetric_difference(m, union_cobertura(por_manzana[k])).area
            for k, m in enumerate(resultado.manzanas, 1)
        ),
        default=0.0,
    )
    # Lo que falta del terreno fuera de la banda de ajuste de su borde: una grieta abierta al límite
    # no es un hueco (no es un anillo interior), pero tampoco es la banda de la grilla. Los huecos ya
    # se contaron: la unión se rellena antes de restarla, para no contarlos dos veces (D86).
    banda = solicitud.terreno.exterior.buffer(DESVIO_BORDE_MAXIMO)
    rellena = shapely.union_all([Polygon(parte.exterior) for parte in shapely.get_parts(union)])
    grietas = shapely.difference(shapely.difference(solicitud.terreno, rellena), banda).area
    return {
        "solape": solape,
        "huecos": huecos,
        "grietas": grietas,
        "bordes": bordes,
        "manzanas": manzanas,
        "partes": shapely.get_num_geometries(union),
        "desvio": shapely.hausdorff_distance(shapely.get_parts(union)[0].exterior, solicitud.terreno.exterior),
    }


def assert_particion_recalculo(solicitud, resultado) -> dict:
    """El invariante con tolerancia del recálculo: una sola pieza, y solapes, huecos, grietas contra
    el límite y diferencias de manzana por debajo del ruido numérico. Devuelve los defectos."""
    d = defectos_de_particion(solicitud, resultado)
    assert d["partes"] == 1, f"la unión tiene {d['partes']} partes"
    assert d["solape"] <= DEFECTO_MAXIMO, f"las piezas se superponen en {d['solape']:.6f} m²"
    assert d["huecos"] + d["grietas"] <= DEFECTO_MAXIMO, f"huecos y grietas suman {d['huecos'] + d['grietas']:.6f} m²"
    assert d["manzanas"] <= DEFECTO_MAXIMO, f"una manzana difiere de sus celdas en {d['manzanas']:.6f} m²"
    return d
