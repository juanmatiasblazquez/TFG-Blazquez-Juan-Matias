"""Tolerancias y operaciones geométricas del motor (copia única de las tolerancias; D25).

El motor trabaja en metros, en el sistema de cálculo del proyecto. Tiene que dar siempre el
mismo resultado (RNF05) y no perder superficie en el camino (CU06, 6.a). Para eso:

- Toda operación de overlay que CONSTRUYE la partición (intersección, diferencia, unión) pasa
  por las funciones de este módulo, con `grid_size=RESOLUCION`, en el marco local. Así GEOS usa
  OverlayNG con *snap rounding*: no tira TopologyException, da siempre el mismo resultado y
  colapsa las astillas de menos de 1 mm.
- La partición se cierra al final con `cerrar_particion` (D39): cada borde lo comparten
  exactamente dos piezas. Después nada vuelve a pasar por una grilla: lo que se calcula SOBRE
  la partición cerrada (la superficie de calle, el contorno) usa `union_cobertura`, que
  disuelve los bordes compartidos sin mover vértices. Ajustar otra vez a la grilla, sobre todo
  en otro marco, abre microhuecos entre piezas vecinas.
- Las comparaciones usan TOLERANCIA: una diferencia menor a 1 cm no separa dos nodos ni es un
  incumplimiento.
- Los polígonos de menos de AREA_RUIDO son residuos numéricos de esas operaciones y se
  descartan. Cualquier fracción mayor se conserva: si no alcanza los mínimos de un lote,
  queda como remanente (espacio verde o libre, D41).
- El cálculo se hace en un MarcoLocal (trasladado y rotado): coordenadas de cientos de metros
  en lugar de millones, y la grilla paralela a los ejes, así los cortes salen exactos.
"""

import math
from dataclasses import dataclass

import numpy as np
import shapely
from shapely import LineString, Point, Polygon, STRtree
from shapely.geometry.base import BaseGeometry

# Grilla de las operaciones de overlay (m). Todo vértice que sale de una operación queda en
# múltiplos de 1 mm del marco donde se calculó.
RESOLUCION = 1e-3
# Distancia por debajo de la cual dos cosas se consideran en contacto o iguales (m).
TOLERANCIA = 1e-2
# Superficie por debajo de la cual una diferencia no es incumplimiento y un polígono es
# ruido numérico (m²).
TOLERANCIA_AREA = 1e-2
AREA_RUIDO = 1e-2
# Dos lados contiguos que difieren en menos de este ángulo son el mismo lado (grados).
ANGULO_COLINEAL = 1.0
# Una parte de un dominio más angosta que esto es una astilla, no dominio (m): la que dejan dos
# grillas en un recálculo (D56) o un área reservada a centímetros del borde o de otra (D59).
ANCHO_ASTILLA = 0.1
# Un lado de un área reservada se alinea con la grilla si se aparta de una recta de la grilla a lo
# sumo esto (m): su calle es esa recta, y lo que queda entre la calle y el área es vereda (D59).
DESVIO_ALINEACION = 1.0

Coordenada = tuple[float, float]


def interseccion(a: BaseGeometry, b: BaseGeometry) -> BaseGeometry:
    return shapely.intersection(a, b, grid_size=RESOLUCION)


def diferencia(a: BaseGeometry, b: BaseGeometry) -> BaseGeometry:
    return shapely.difference(a, b, grid_size=RESOLUCION)


def union(geometrias) -> BaseGeometry:
    return shapely.union_all(list(geometrias), grid_size=RESOLUCION)


def ajustar(geometria: BaseGeometry) -> BaseGeometry:
    """Lleva la geometría a la grilla de RESOLUCION (como si saliera de un overlay)."""
    return shapely.set_precision(geometria, RESOLUCION)


def superficie(geometria: BaseGeometry) -> BaseGeometry:
    """Solo la parte de superficie de un overlay: un recorte contra un borde puede dejar líneas o
    puntos sueltos junto a los polígonos, y un overlay posterior con geometrías mixtas falla. A
    diferencia de `poligonos`, no descarta ningún polígono por chico: es superficie del dominio."""
    if geometria.is_empty or geometria.geom_type in ("Polygon", "MultiPolygon"):
        return geometria
    partes = [p for p in shapely.get_parts(geometria) if isinstance(p, Polygon) and not p.is_empty]
    partes += [q for p in shapely.get_parts(geometria) if p.geom_type == "MultiPolygon" for q in p.geoms]
    if not partes:
        return Polygon()
    return partes[0] if len(partes) == 1 else shapely.MultiPolygon(partes)


def restaurar(geometria: BaseGeometry) -> BaseGeometry:
    """Devuelve a la grilla de 1 mm cada coordenada que está a menos de un micrómetro de ella, una
    por una, sin tocar la topología ni el orden de los vértices (D56).

    Es para lo fijado de un recálculo: sus piezas salieron de un cierre en el marco de la
    alternativa, con sus vértices en la grilla de 1 mm, y vuelven de la base con un error de
    nanómetros (la ida y vuelta por EPSG:4326). Redondearlas las devuelve a las coordenadas exactas
    de la versión de origen. Un vértice que un recálculo anterior llevó sobre un lado oblicuo no está
    en la grilla, y queda donde está. `ajustar` no sirve: rehace la geometría y puede cambiar dónde
    empieza cada anillo."""

    def a_la_grilla(xy: np.ndarray) -> np.ndarray:
        # Como lo hace GEOS con la grilla (`round(x · escala) / escala`), así es el mismo número.
        escala = 1 / RESOLUCION
        redondeado = np.round(xy * escala) / escala
        return np.where(np.abs(redondeado - xy) <= 1e-6, redondeado, xy)

    return shapely.transform(geometria, a_la_grilla)


def cerrar_con_fijas(
    dominio: Polygon, fijas: list[BaseGeometry], nuevas: list[BaseGeometry]
) -> tuple[list[BaseGeometry], list[BaseGeometry]]:
    """Cierra la partición de un recálculo (D56): las piezas fijadas y las nuevas, en un solo arreglo
    plano, sin mover lo fijado.

    1. `cerrar_particion` sobre el terreno entero, con las piezas fijadas y las nuevas: todas
       comparten sus bordes exactamente (D39). Las fijadas ya estaban en la grilla de 1 mm del marco
       de la alternativa, así que sus vértices quedan donde estaban; pero donde una pieza nueva
       termina sobre un lado fijado oblicuo, el ajuste a la grilla dobla ese lado por un vértice que
       está hasta √2 / 2 mm afuera de él.
    2. Cada vértice que el cierre metió en un lado fijado va exactamente sobre ese lado (el lado
       original entre los dos vértices fijados que lo rodean en el anillo), y el mismo reemplazo se
       aplica a todas las piezas, así siguen compartiendo sus bordes. En un lado paralelo a los ejes
       del marco ya estaba sobre él.
    3. Los anillos quedan sin vértices repetidos ni picos.

    Las piezas fijadas conservan su forma y sus vértices originales; solo suman puntos sobre sus
    lados, donde las tocan las nuevas. Devuelve las fijadas y las nuevas, en su orden.
    """
    cerradas = cerrar_particion(dominio, [*fijas, *nuevas], fijas=len(fijas))
    candidatos: dict[Coordenada, list] = {}
    for original, cerrada in zip(fijas, cerradas[: len(fijas)], strict=True):
        _enderezar(original, cerrada, candidatos)
    movidos = {v: _destino(v, lados) for v, lados in candidatos.items()}
    finales = [
        _como_el_original(original, _limpiar(_reemplazar(g, movidos)))
        for original, g in zip(fijas, cerradas[: len(fijas)], strict=True)
    ]
    return finales, _sin_lo_fijado([_limpiar(_reemplazar(g, movidos)) for g in cerradas[len(fijas) :]], finales)


def _sin_lo_fijado(nuevas: list[BaseGeometry], fijas: list[BaseGeometry]) -> list[BaseGeometry]:
    """Las nuevas sin la superficie que pisan de una fijada. Una fijada que el cierre cambió de otra forma
    vuelve tal cual (`_como_el_original`): si era una calle angosta, casi entera dentro de los cruces, el
    cierre pudo darles parte de ella a las nuevas, y esa parte quedaría dos veces (lo encontró el barrido
    de recálculo con la calle de borde por lado, D86). Se resta exacta, sin la grilla: el borde de la
    fijada ya es el de las nuevas. Sin solapes, las nuevas quedan como estaban."""
    validas = [f for f in fijas if not f.is_empty]
    if not validas:
        return nuevas
    arbol = STRtree(validas)
    resultado = []
    for nueva in nuevas:
        pisadas = [validas[k] for k in arbol.query(nueva, predicate="intersects")]
        if nueva.is_empty or not any(shapely.intersection(nueva, f).area > 1e-6 for f in pisadas):
            resultado.append(nueva)
            continue
        resultado.append(superficie(shapely.difference(nueva, shapely.union_all(pisadas))))
    return resultado


def _como_el_original(original: BaseGeometry, cerrada: BaseGeometry) -> BaseGeometry:
    """La pieza fijada con los anillos de la original (el mismo vértice de comienzo y el mismo
    sentido) y, en cada lado, los puntos que el cierre le sumó. Sin puntos nuevos, es la original tal
    cual. Un vértice original que el cierre no tiene (la punta de un pico sin superficie) se conserva.
    Si el cierre la cambió de otra forma, queda la original tal cual: lo fijado nunca cambia."""
    entre = _entre_originales(original, cerrada)
    if not any(entre.values()):
        return original
    presentes = _vertices(cerrada)
    admitidos = _lados_admitidos(original, cerrada)
    partes = []
    for parte in _partes(original):
        anillos = []
        for anillo in _anillos(parte):
            puntos = anillo[:-1]
            con = [k for k, v in enumerate(puntos) if v in presentes]
            if len(con) < 2:
                return original
            nuevo: list[Coordenada] = []
            for n, k in enumerate(con):
                siguiente = con[(n + 1) % len(con)]
                a, b = puntos[k], puntos[siguiente]
                if (a, b) not in entre or (a, b) not in admitidos:
                    return original
                # Los originales que faltan entre a y b van primero; los puntos del cierre, después.
                faltan = range(k + 1, siguiente) if siguiente > k else [*range(k + 1, len(puntos)), *range(0, siguiente)]
                nuevo += [a, *(puntos[m] for m in faltan), *entre[(a, b)]]
            # El anillo empieza donde empezaba el original.
            inicio = nuevo.index(puntos[0])
            nuevo = nuevo[inicio:] + nuevo[:inicio]
            anillos.append([*nuevo, nuevo[0]])
        partes.append(_poligono(anillos))
    resultado = partes[0] if isinstance(original, Polygon) else shapely.MultiPolygon(partes)
    # Solo puntos sobre sus lados: si no, la original tal cual (lo fijado no cambia; el defecto, de
    # menos de un milímetro, queda del lado de lo nuevo).
    borde = original.boundary
    sumados = [v for v in _vertices(resultado) if v not in _vertices(original)]
    if any(borde.distance(Point(v)) > 1e-6 for v in sumados) or not resultado.is_valid:
        return original
    return resultado


def _lados_admitidos(original: BaseGeometry, cerrada: BaseGeometry) -> set[tuple[Coordenada, Coordenada]]:
    """Los pares de vértices originales que el cierre puede tener seguidos: los lados originales y,
    si el cierre no tiene algún vértice original intermedio, los pares cuyos intermedios faltantes
    están sobre su misma recta (la punta de un pico sin superficie), en los dos sentidos."""
    presentes = _vertices(cerrada)
    admitidos = set()
    for parte in _partes(original):
        for anillo in _anillos(parte):
            puntos = anillo[:-1]
            con = [k for k, v in enumerate(puntos) if v in presentes]
            for n, k in enumerate(con):
                siguiente = con[(n + 1) % len(con)]
                a, b = puntos[k], puntos[siguiente]
                faltan = range(k + 1, siguiente) if siguiente > k else [*range(k + 1, len(puntos)), *range(0, siguiente)]
                if all(_a_la_recta(puntos[m], a, b) <= RESOLUCION for m in faltan):
                    admitidos |= {(a, b), (b, a)}
    return admitidos


def _a_la_recta(v: Coordenada, a: Coordenada, b: Coordenada) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo = math.hypot(dx, dy)
    if largo == 0:
        return math.dist(v, a)
    return abs((v[0] - a[0]) * dy - (v[1] - a[1]) * dx) / largo


def _entre_originales(original: BaseGeometry, cerrada: BaseGeometry) -> dict:
    """Para cada par de vértices originales seguidos en el anillo cerrado, los puntos que el cierre
    puso entre ellos, en los dos sentidos."""
    propios = _vertices(original)
    entre: dict[tuple[Coordenada, Coordenada], list[Coordenada]] = {}
    for parte in _partes(cerrada):
        for anillo in _anillos(parte):
            puntos = anillo[:-1]
            con = [k for k, v in enumerate(puntos) if v in propios]
            for n, k in enumerate(con):
                siguiente = con[(n + 1) % len(con)]
                medio = range(k + 1, siguiente) if siguiente > k else [*range(k + 1, len(puntos)), *range(0, siguiente)]
                intermedios = [puntos[m] for m in medio]
                entre[(puntos[k], puntos[siguiente])] = intermedios
                entre[(puntos[siguiente], puntos[k])] = intermedios[::-1]
    return entre


def _vertices(geometria: BaseGeometry) -> set[Coordenada]:
    return {v for parte in _partes(geometria) for anillo in _anillos(parte) for v in anillo}


def _enderezar(original: BaseGeometry, cerrada: BaseGeometry, candidatos: dict) -> None:
    """Los lados originales sobre los que puede ir cada vértice que el cierre sumó a una pieza fijada:
    el de los dos vértices originales que lo rodean en el anillo cerrado (entre ellos puede faltar la
    punta de un pico sin superficie, que está sobre la misma recta)."""
    admitidos = _lados_admitidos(original, cerrada)
    for (a, b), intermedios in _entre_originales(original, cerrada).items():
        if a > b or (a, b) not in admitidos:
            continue  # cada lado una vez, y solo los lados originales
        for v in intermedios:
            candidatos.setdefault(v, []).append((a, b))


def _destino(v: Coordenada, lados: list) -> Coordenada:
    """Adónde va un vértice del cierre: su pie sobre el lado original. Si lo reclaman lados de varias
    piezas fijadas que no lo llevan al mismo punto (una esquina donde se juntan), va a la esquina que
    comparten."""
    pies = []
    for a, b in lados:
        t, pie, _ = _sobre(v, a, b)
        pies.append(a if t <= 0 else b if t >= 1 else pie)
    if all(math.dist(pie, pies[0]) <= 1e-9 for pie in pies):
        return pies[0]
    comunes = set.intersection(*({a, b} for a, b in lados))
    if comunes:
        return min(comunes, key=lambda c: (round(math.dist(v, c), 12), c))
    return pies[0]


def _limpiar(geometria: BaseGeometry) -> BaseGeometry:
    """Sin vértices repetidos seguidos ni picos (ida y vuelta al mismo punto): lo que puede dejar
    llevar un vértice a una esquina. Si igual queda inválida, sus partes válidas, todas."""
    if geometria.is_empty:
        return geometria
    partes = []
    for parte in _partes(geometria):
        anillos = []
        for anillo in _anillos(parte):
            puntos = anillo[:-1]
            cambio = True
            while cambio and len(puntos) >= 3:
                cambio = False
                limpio = [v for k, v in enumerate(puntos) if v != puntos[k - 1]] if len(puntos) > 1 else puntos
                for k in range(len(limpio)):
                    if len(limpio) >= 3 and limpio[k - 2] == limpio[k]:
                        limpio = [v for j, v in enumerate(limpio) if j not in (k - 1 if k >= 1 else len(limpio) - 1, k)]
                        cambio = True
                        break
                cambio = cambio or limpio != puntos
                puntos = limpio
            if len(puntos) >= 3:
                anillos.append([*puntos, puntos[0]])
        if anillos:
            partes.append(_poligono(anillos))
    if not partes:
        return Polygon()
    resultado = partes[0] if isinstance(geometria, Polygon) else shapely.MultiPolygon(partes)
    if resultado.is_valid:
        return resultado
    # Ninguna parte se pierde: quien la usa la separa en partes si hace falta.
    validas = [p for p in shapely.get_parts(shapely.make_valid(resultado)) if isinstance(p, Polygon) and not p.is_empty]
    validas += [q for p in shapely.get_parts(shapely.make_valid(resultado)) if p.geom_type == "MultiPolygon" for q in p.geoms]
    if not validas:
        return resultado
    return validas[0] if len(validas) == 1 else shapely.MultiPolygon(validas)


def _partes(geometria: BaseGeometry) -> list[Polygon]:
    if geometria.is_empty:
        return []
    if isinstance(geometria, Polygon):
        return [geometria]
    return [g for g in shapely.get_parts(geometria) if isinstance(g, Polygon) and not g.is_empty]


def _anillos(poligono: Polygon) -> list[list[Coordenada]]:
    return [[(float(x), float(y)) for x, y in anillo.coords] for anillo in (poligono.exterior, *poligono.interiors)]


def _sobre(v: Coordenada, a: Coordenada, b: Coordenada) -> tuple[float, Coordenada, float]:
    """La posición de `v` a lo largo de a→b (0 a 1), su pie sobre el lado y la distancia. En un lado
    paralelo a un eje el pie es exacto: el vértice ya está sobre el lado."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = ((v[0] - a[0]) * dx + (v[1] - a[1]) * dy) / (dx * dx + dy * dy)
    if a[1] == b[1]:
        punto = (v[0], a[1])
    elif a[0] == b[0]:
        punto = (a[0], v[1])
    else:
        punto = (a[0] + t * dx, a[1] + t * dy)
    return t, punto, math.dist(v, punto)


def _reemplazar(geometria: BaseGeometry, movidos: dict) -> BaseGeometry:
    if not movidos or geometria.is_empty:
        return geometria
    partes = [_poligono([[movidos.get(v, v) for v in anillo] for anillo in _anillos(p)]) for p in _partes(geometria)]
    return partes[0] if isinstance(geometria, Polygon) else shapely.MultiPolygon(partes)


def _poligono(anillos: list[list[Coordenada]]) -> Polygon:
    return Polygon(anillos[0], anillos[1:])


def union_cobertura(geometrias) -> BaseGeometry:
    """Unión de piezas de una partición cerrada (D39): disuelve los bordes compartidos sin
    volver a ajustar los vértices a una grilla.

    Está pensada para piezas que no se superponen y cuyos bordes comunes coinciden exactamente,
    como las que deja `cerrar_particion`. Si las piezas no son una cobertura así (un trazado
    armado a mano en una prueba, por ejemplo), GEOS lo rechaza o da un resultado inválido, y se
    usa la unión común, sin grilla: tampoco mueve vértices.
    """
    piezas = [g for g in geometrias if not g.is_empty]
    if not piezas:
        return Polygon()
    try:
        resultado = shapely.coverage_union_all(piezas)
        if resultado.is_valid:
            return resultado
    except shapely.errors.GEOSException:
        pass
    return shapely.union_all(piezas)


def cerrar_particion(dominio: Polygon, piezas: list[BaseGeometry], fijas: int = 0) -> list[BaseGeometry]:
    """Cierra una partición del dominio: sin huecos, sin solapes y con cada borde compartido
    exactamente por dos piezas (D39).

    Las piezas salen de operaciones distintas (franjas, ochavas, cortes en el marco de cada
    manzana) y, aunque todas usan la grilla de 1 mm, el *snap rounding* de una operación no ve
    los vértices de las otras: entre vecinas quedan astillas de menos de un milímetro. Para
    cerrarlas:

    - se nodan juntos los bordes de todas las piezas y el del dominio, con la grilla, y
      `polygonize` da las caras de ese arreglo plano;
    - cada cara del dominio va a la pieza que la contiene;
    - las caras dudosas (dentro de ninguna pieza, un hueco, o de más de una, un solape) van a
      la vecina con la que comparten más borde, entre las que la contienen si alguna es vecina;
    - cada pieza es la unión de sus caras.

    Devuelve las piezas en el mismo orden; una pieza que se quedó sin caras sale vacía. Trabaja
    en el marco local, donde se construyó la partición.

    Las primeras `fijas` piezas son las fijadas de un recálculo (D56): una cara dentro de una de ellas
    es siempre suya, y una dudosa va a una pieza nueva si alguna es vecina. Así cada fijada se queda
    exactamente con su superficie.
    """
    if not piezas:
        return []
    lineas = union([dominio.boundary, *(p.boundary for p in piezas if not p.is_empty)])
    caras = [
        cara
        for cara in shapely.get_parts(shapely.polygonize(shapely.get_parts(lineas)))
        if cara.area > 0 and dominio.contains(cara.point_on_surface())
    ]
    caras.sort(key=clave_poligono)
    arbol_piezas = STRtree(piezas)
    dueno: list[int | None] = []
    candidatas: list[list[int]] = []
    for cara in caras:
        contienen = sorted(int(i) for i in arbol_piezas.query(cara.point_on_surface(), predicate="within"))
        candidatas.append(contienen)
        if contienen and contienen[0] < fijas:
            dueno.append(contienen[0])
        else:
            dueno.append(contienen[0] if len(contienen) == 1 else None)

    # Las dudosas se resuelven por vecindad, de afuera hacia adentro: en cada vuelta toma dueño
    # toda dudosa que limita con una cara que ya lo tiene.
    arbol_caras = STRtree(caras)
    dudosas = [k for k, d in enumerate(dueno) if d is None]
    while dudosas:
        resueltas = {}
        for k in dudosas:
            borde = {}
            for j in sorted(int(j) for j in arbol_caras.query(caras[k])):
                if j == k or dueno[j] is None:
                    continue
                largo = caras[k].boundary.intersection(caras[j].boundary).length
                if largo > 0:
                    borde[dueno[j]] = borde.get(dueno[j], 0.0) + largo
            if fijas and any(i >= fijas for i in borde):
                borde = {i: largo for i, largo in borde.items() if i >= fijas}
            if borde:
                preferidas = [i for i in candidatas[k] if i in borde] or sorted(borde)
                resueltas[k] = max(preferidas, key=lambda i: (round(borde[i], 6), -i))
        if not resueltas:
            # Una cara degenerada (de área casi nula, contra el límite) puede tocar a sus vecinas
            # solo en un punto: va a la pieza de la cara con dueño más cercana (lo encontró el
            # barrido de la sesión 8 con la calle de borde, D50).
            con_dueno = [j for j, d in enumerate(dueno) if d is not None]
            if not con_dueno:
                raise ValueError("La partición tiene una zona sin ninguna pieza vecina.")
            for k in dudosas:
                cercana = min(con_dueno, key=lambda j: (round(caras[k].distance(caras[j]), 6), j))
                resueltas[k] = dueno[cercana]
        for k, i in resueltas.items():
            dueno[k] = i
        dudosas = [k for k in dudosas if k not in resueltas]

    por_pieza: dict[int, list[Polygon]] = {}
    for cara, i in zip(caras, dueno, strict=True):
        por_pieza.setdefault(i, []).append(cara)
    return [union_cobertura(por_pieza.get(i, [])) for i in range(len(piezas))]


def clave_punto(x: float, y: float) -> Coordenada:
    """Clave estable de un punto: coordenadas redondeadas al milímetro (sin -0.0)."""
    return (round(x, 3) + 0.0, round(y, 3) + 0.0)


def clave_poligono(poligono: Polygon) -> tuple[float, float, float]:
    """Orden estable entre polígonos: de abajo hacia arriba y de izquierda a derecha."""
    centro = poligono.centroid
    return (round(centro.y, 3), round(centro.x, 3), round(poligono.area, 3))


def poligonos(geometria: BaseGeometry) -> list[Polygon]:
    """Partes poligonales de una geometría, sin el ruido numérico, en orden estable."""
    partes = []
    pendientes = [geometria]
    while pendientes:
        g = pendientes.pop()
        if g.is_empty:
            continue
        if isinstance(g, Polygon):
            if g.area >= AREA_RUIDO:
                partes.append(g)
        elif hasattr(g, "geoms"):
            pendientes.extend(g.geoms)
    return sorted(partes, key=clave_poligono)


def lineas(geometria: BaseGeometry) -> list[LineString]:
    """Partes lineales de una geometría (por ejemplo, una recta recortada por el terreno)."""
    partes = []
    pendientes = [geometria]
    while pendientes:
        g = pendientes.pop()
        if g.is_empty:
            continue
        if isinstance(g, LineString):
            if g.length > TOLERANCIA:
                partes.append(g)
        elif hasattr(g, "geoms"):
            pendientes.extend(g.geoms)
    return sorted(partes, key=lambda l: (clave_punto(*l.coords[0]), clave_punto(*l.coords[-1])))


def angulo(a: Coordenada, b: Coordenada) -> float:
    """Dirección del segmento a→b, en radianes."""
    return math.atan2(b[1] - a[1], b[0] - a[0])


def paralelos(alfa: float, beta: float) -> bool:
    """Dos direcciones son paralelas (en cualquier sentido) si difieren menos de ANGULO_COLINEAL."""
    return abs(math.remainder(alfa - beta, math.pi)) < math.radians(ANGULO_COLINEAL)


def unitario(a: Coordenada, b: Coordenada) -> np.ndarray:
    v = np.asarray(b, dtype=float) - np.asarray(a, dtype=float)
    return v / np.hypot(v[0], v[1])


@dataclass(frozen=True)
class MarcoLocal:
    """Traslado al origen y rotación de −`angulo` grados: la orientación pasa a ser el eje x."""

    origen: Coordenada
    angulo: float

    @classmethod
    def para(cls, poligono: Polygon, angulo: float) -> "MarcoLocal":
        # El origen se redondea al metro: restar un entero es exacto en coma flotante.
        centro = poligono.centroid
        return cls((float(round(centro.x)), float(round(centro.y))), float(angulo))

    def _coseno_seno(self) -> tuple[float, float]:
        # Exactos en los múltiplos de 90°: una rotación de 90° es un intercambio de ejes.
        exactos = {0.0: (1.0, 0.0), 90.0: (0.0, 1.0), 180.0: (-1.0, 0.0), 270.0: (0.0, -1.0)}
        grados = self.angulo % 360.0
        if grados in exactos:
            return exactos[grados]
        radianes = math.radians(grados)
        return math.cos(radianes), math.sin(radianes)

    def a_local(self, geometria):
        cos, sen = self._coseno_seno()
        ox, oy = self.origen

        def transformar(xy: np.ndarray) -> np.ndarray:
            x, y = xy[:, 0] - ox, xy[:, 1] - oy
            return np.column_stack((x * cos + y * sen, -x * sen + y * cos))

        return shapely.transform(geometria, transformar)

    def a_global(self, geometria):
        cos, sen = self._coseno_seno()
        ox, oy = self.origen

        def transformar(xy: np.ndarray) -> np.ndarray:
            x, y = xy[:, 0], xy[:, 1]
            return np.column_stack((x * cos - y * sen + ox, x * sen + y * cos + oy))

        return shapely.transform(geometria, transformar)


# --- Lados, frentes y medidas de una celda ---------------------------------------------------


@dataclass(frozen=True)
class Lado:
    """Tramo recto del borde de un polígono: segmentos contiguos colineales, en sentido antihorario."""

    puntos: tuple[Coordenada, ...]
    toca: bool

    @property
    def inicio(self) -> Coordenada:
        return self.puntos[0]

    @property
    def fin(self) -> Coordenada:
        return self.puntos[-1]

    @property
    def largo(self) -> float:
        return math.fsum(math.dist(a, b) for a, b in zip(self.puntos, self.puntos[1:]))

    @property
    def direccion(self) -> float:
        return angulo(self.inicio, self.fin)

    def linea(self) -> LineString:
        return LineString(self.puntos)


def lados(poligono: Polygon, referencia: BaseGeometry) -> list[Lado]:
    """Lados del borde exterior, marcando cuáles tocan `referencia` (los corredores).

    Un segmento toca si sus extremos y su punto medio están a TOLERANCIA o menos. Los
    segmentos contiguos colineales con el mismo estado forman un solo lado. El anillo se
    normaliza y se recorre en sentido antihorario, así el resultado no depende de cómo se
    construyó el polígono.
    """
    anillo = shapely.normalize(poligono).exterior
    coordenadas = [(float(x), float(y)) for x, y in anillo.coords]
    if not anillo.is_ccw:
        coordenadas.reverse()
    segmentos = [
        (a, b) for a, b in zip(coordenadas, coordenadas[1:]) if math.dist(a, b) > RESOLUCION / 2
    ]
    if not segmentos:
        return []
    toca = _tocan(segmentos, referencia)
    direcciones = [angulo(a, b) for a, b in segmentos]

    def mismo_lado(i: int, j: int) -> bool:
        giro = abs(math.remainder(direcciones[i] - direcciones[j], math.tau))
        return toca[i] == toca[j] and giro < math.radians(ANGULO_COLINEAL)

    cantidad = len(segmentos)
    comienzo = next((i for i in range(cantidad) if not mismo_lado(i - 1, i)), 0)
    grupos: list[list[int]] = []
    for k in range(cantidad):
        i = (comienzo + k) % cantidad
        if grupos and mismo_lado(i - 1, i):
            grupos[-1].append(i)
        else:
            grupos.append([i])
    return [
        Lado(tuple([segmentos[g[0]][0]] + [segmentos[i][1] for i in g]), toca[g[0]]) for g in grupos
    ]


def lados_de_agujero(anillo, referencia: BaseGeometry) -> list[Lado]:
    """Lados de un anillo interior de un dominio (un agujero: un área reservada en el medio, D59),
    con el dominio a la izquierda: en sentido horario alrededor del agujero. Son los lados de
    `lados` sobre el agujero como polígono, recorridos al revés."""
    propios = lados(Polygon(anillo), referencia)
    return [Lado(tuple(reversed(lado.puntos)), lado.toca) for lado in reversed(propios)]


def sin_astillas(dominio: BaseGeometry, ancho: float = ANCHO_ASTILLA) -> BaseGeometry:
    """El dominio sin las partes más angostas que `ancho`: una apertura morfológica con inglete,
    recortada al dominio, y sin las piezas que no alcanzan ese ancho (D56, D59). Las esquinas
    quedan; las ranuras y las tiras de milímetros o centímetros, no."""
    radio = ancho / 2
    abierto = dominio.buffer(-radio, join_style="mitre").buffer(radio, join_style="mitre")
    partes = [parte for parte in poligonos(interseccion(abierto, dominio)) if alcanza_ancho(parte, ancho)]
    return union(partes) if partes else Polygon()


def _tocan(segmentos: list[tuple[Coordenada, Coordenada]], referencia: BaseGeometry) -> list[bool]:
    if referencia is None or referencia.is_empty:
        return [False] * len(segmentos)
    shapely.prepare(referencia)
    puntos = []
    for a, b in segmentos:
        puntos.extend((a, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), b))
    cerca = shapely.dwithin(shapely.points(np.asarray(puntos)), referencia, TOLERANCIA)
    return [bool(fila.all()) for fila in np.asarray(cerca).reshape(-1, 3)]


class IndiceEjes:
    """Ejes de la red con un índice espacial, para saber qué calle tiene cerca un lado."""

    def __init__(self, ejes: list[LineString]):
        self.ejes = list(ejes)
        self._arbol = STRtree(self.ejes) if self.ejes else None

    def mas_cercano(self, punto: Point) -> int | None:
        """Índice del eje más cercano; ante un empate, el de menor índice (orden estable)."""
        if self._arbol is None:
            return None
        return int(min(self._arbol.query_nearest(punto, all_matches=True)))


def ancho(poligono: Polygon) -> float:
    """Ancho de una pieza: el diámetro del mayor círculo que entra en ella (D41, D43).

    Es el ancho en su parte más ancha y no depende de la orientación: una plaza de 30 × 30 m
    mide 30, una franja de 12 m mide 12 y un triángulo, el doble de su radio inscripto. Es la
    copia única: con ella se mide el ancho mínimo del verde y el ancho útil de un lote.
    """
    return 2 * shapely.maximum_inscribed_circle(poligono, tolerance=RESOLUCION).length


def alcanza_ancho(poligono: Polygon, minimo: float) -> bool:
    """Si la pieza alcanza el ancho `minimo`: lo mismo que `ancho(poligono) + TOLERANCIA >=
    minimo`, la convención del verificador, pero sin buscar el círculo.

    Un círculo de diámetro `d` entra en el polígono si y solo si al erosionarlo `d / 2` queda
    algo. Es la comparación que se usa para decidir (si una pieza es lote o verde), porque buscar
    el círculo con 1 mm de tolerancia tarda unos 5 ms por lote y 75 ms por manzana, y erosionar,
    unos 10 µs (D43). `ancho` queda para informar el valor. Las curvas de la erosión (en los
    vértices entrantes) van con 64 segmentos por cuarto de círculo: el error es menor a 1 mm con
    los anchos del verde. Una prueba exige que las dos digan lo mismo.
    """
    radio = (minimo - TOLERANCIA) / 2
    if radio <= 0:
        return True
    return not poligono.buffer(-radio, quad_segs=64).is_empty


@dataclass(frozen=True)
class Medida:
    """Frente y fondo de una celda, como los mide el verificador (D26)."""

    frente: float
    fondo: float
    linea_frente: LineString | None
    # Tiene frente sobre dos calles que no son paralelas (Ord. 8060, art. 54; D49).
    esquina: bool = False


def medir(poligono: Polygon, corredores: BaseGeometry, ejes: IndiceEjes) -> Medida:
    """Mide el frente y el fondo de una celda contra los corredores de la red.

    - Candidatos a frente: los lados que tocan un corredor y son paralelos al eje de la calle
      más cercana. Así la línea de ochava (diagonal) no cuenta como frente propio.
    - Frente: la extensión, medida a lo largo de esa calle, de la cadena de lados contiguos
      que tocan corredores. Incluye la ochava, que es vía pública cedida por el lote (Ord.
      8060, art. 55): el frente se mide hasta el vértice teórico de la esquina.
    - Fondo: la extensión de la celda perpendicular al frente.
    - En un lote con dos frentes (esquina) se toma el lado que deja el mayor fondo, es decir,
      el más angosto, como es usual.
    - Es de esquina si tiene lados sobre dos calles que no son paralelas: la línea de ochava no
      cuenta, y un lote entre dos calles paralelas (pasante) no es de esquina (D49).
    """
    todos = lados(poligono, corredores)
    tocan = [i for i, lado in enumerate(todos) if lado.toca]
    if not tocan:
        return Medida(0.0, 0.0, None)
    sobre_calle = [i for i in tocan if _paralelo_a_su_calle(todos[i], ejes)]
    esquina = any(
        not paralelos(todos[i].direccion, todos[j].direccion) for i in sobre_calle for j in sobre_calle if i < j
    )
    vertices = np.asarray(poligono.exterior.coords)
    mejor: tuple[tuple[float, float, int], Medida] | None = None
    for i in sobre_calle or tocan:
        direccion = unitario(todos[i].inicio, todos[i].fin)
        normal = np.array([-direccion[1], direccion[0]])
        fondo = float(np.ptp(vertices @ normal))
        cadena = np.asarray(cadena_de_frente(todos, i))
        frente = float(np.ptp(cadena @ direccion))
        clave = (round(fondo, 4), round(frente, 4), -i)
        if mejor is None or clave > mejor[0]:
            mejor = (clave, Medida(frente, fondo, todos[i].linea(), esquina))
    return mejor[1]


def _paralelo_a_su_calle(lado: Lado, ejes: IndiceEjes) -> bool:
    medio = Point((lado.inicio[0] + lado.fin[0]) / 2, (lado.inicio[1] + lado.fin[1]) / 2)
    indice = ejes.mas_cercano(medio)
    if indice is None:
        return False
    eje = ejes.ejes[indice]
    return paralelos(lado.direccion, angulo(eje.coords[0], eje.coords[-1]))


def cadena_de_frente(todos: list[Lado], i: int) -> list[Coordenada]:
    """Puntos de los lados que tocan y son contiguos a `todos[i]` (recorriendo el anillo): el
    frente con sus ochavas. Con esta cadena mide `medir` el frente, y el subdivisor corta un lote
    grande a lo largo de ella (D47)."""
    cantidad = len(todos)
    indices = [i]
    j = (i - 1) % cantidad
    while j != i and todos[j].toca:
        indices.insert(0, j)
        j = (j - 1) % cantidad
    j = (i + 1) % cantidad
    while j not in indices and todos[j].toca:
        indices.append(j)
        j = (j + 1) % cantidad
    return [punto for k in indices for punto in todos[k].puntos]
