"""Generador de la red de circulación (p. 47). Por ahora, el patrón grilla (D24, D48, D50).

Trabaja en el marco local del motor (`geometria.MarcoLocal`), donde la orientación de la
estrategia ya está aplicada: las calles longitudinales son paralelas al eje x y las
transversales al eje y.

**La calle de borde (Ord. 8060, art. 48; D50, D86).** El lado menor de toda manzana mide al menos
42 m. Adentro, las longitudinales separan filas de manzanas de dos fondos, y una calle de borde corre
junto al límite donde sin ella una fila quedaría con frente de un solo lado: ninguna manzana queda
como una franja de un fondo contra el límite. Por dónde va lo dice `limite_con_calle`, según el
parámetro `calle_borde`:

- **todo el contorno** (D50): las calles de la grilla terminan en T contra ella, y los accesos abren
  directo a ella;
- **por lado** (el de referencia desde el motor 0.11.0, D86): solo los lados casi paralelos a las
  filas, los de una entrante (alineados con la grilla si se puede, como los de un área) y los de un
  acceso. En los lados que cruzan la grilla de punta, las filas y las cuadras terminan contra el límite,
  y sus calles siguen afuera (Ord. 8060, art. 20): la manzana conserva sus dos fondos.

**Las avenidas (Ley 4146, art. 12; D48).** No menos del 20 % de la longitud de las calles tiene
que ser de avenidas de al menos 20 m. Todas las calles nacen locales (la jerarquía menor), y se
eligen como avenidas (la mayor) las mínimas para llegar. Se eligen calles enteras, que son una
recta de la grilla, un conector de acceso o un enlace, en este orden:

1. las que conectan accesos: el conector de cada acceso, la calle de borde a la que abre y la
   transversal más cercana a él por la red;
2. las transversales que atraviesan el terreno (las dos puntas en el borde), de la más larga a
   la más corta;
3. las demás transversales y los enlaces, por largo;
4. las demás calles de borde, y
5. como último recurso, las longitudinales. Una calle de borde o una longitudinal se elige solo si
   con el ancho de avenida el fondo de las manzanas no baja del mínimo: en ellas frentean los
   lotes.

Se suman en ese orden hasta llegar, y después se saca toda avenida sin la cual igual se llega.
Las posiciones de los ejes salen de los anchos reales, así que la red se vuelve a trazar con
cada elección. La regla de la proporción es `verificador.faltante_avenidas` (copia única).

**Si no se llega (D53):** se suma una transversal y se vuelve a elegir, y así hasta llegar o hasta
que la cuadra, con el ancho de la local, baje del lado menor del art. 48. Una transversal no le
quita fondo a las filas y puede ser avenida. Si ni así se llega, queda la red sin transversales de
más (la de más lotes) con todas las avenidas que se pudieron, y el generador devuelve la causa y
la sugerencia, que el verificador suma al incumplimiento.

**El recálculo (CU09, D56).** Con `fija`, el dominio es el dominio restante (el terreno menos lo
fijado, que puede tener agujeros o estar en varias piezas) y la red nueva se integra con la fijada:

- la calle de borde va solo donde el dominio restante toca el límite del terreno; contra lo fijado
  no hay calle de borde, porque las calles fijadas ya dan frente;
- una calle fijada paralela a una familia de la grilla fuerza una recta sobre su eje (la grilla nueva
  la continúa), y las demás rectas se reparten entre las forzadas con las reglas de siempre; una
  calle que continúa a una fijada conserva su jerarquía;
- la punta de una calle nueva contra lo fijado se prolonga hasta el eje fijado (un empalme: el tramo
  fijado se parte en dos tramos fijados) o hasta el nodo fijado de la boca;
- un anclaje que quedó sin calle nueva se une con la prolongación de la calle fijada hasta el primer
  eje nuevo;
- la poda nunca saca un tramo fijado, y las avenidas se eligen solo entre las calles nuevas, con la
  proporción medida sobre la red integrada: las avenidas fijadas cuentan.

**Las áreas reservadas (CU06, paso 4; D59).** El dominio es el terreno menos las áreas: puede tener
agujeros (un área en el medio) o muescas (un área contra el borde). Una calle de borde las rodea por
la misma razón que al terreno (D50): sin ella, las manzanas que lindan con el área quedarían de un
fondo. `limite_con_calle` es por dónde va la calle de borde: el límite del terreno y el borde de las
áreas. Un lado del área paralelo a una familia de la grilla fuerza una recta sobre el eje de su
calle, si entran filas y cuadras (`_Trazado._alinear_con_areas`): la calle del área sigue derecho
como calle de la grilla, y las manzanas que lindan con el área son filas de dos fondos.
"""

import math
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

import numpy as np
from shapely import LineString, MultiLineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import substring

from .contrato import (
    CalleBorde,
    Estrategia,
    JerarquiaCorredor,
    ParametrosLoteo,
    PatronRed,
    jerarquia_mayor,
    jerarquia_menor,
)
from .errores import ErrorConectividad, NoImplementado
from .geometria import (
    DESVIO_ALINEACION,
    TOLERANCIA,
    angulo,
    diferencia,
    interseccion,
    lados,
    lados_de_agujero,
    lineas,
    paralelos,
    poligonos,
    union,
    unitario,
)
from .red import RedCirculacion, Tramo
from .verificador import es_avenida, faltante_avenidas, porcentaje_avenidas

SUGERENCIA = "Probá otra orientación de la grilla o ubicá el acceso frente a una calle."

# Los tipos de calle, la unidad que se elige como avenida (D48). BORDE es un tramo de la calle de
# borde entre dos esquinas del contorno (D50). CONTINUACION es una recta de la grilla que continúa a
# una calle fijada en un recálculo (D56): conserva su jerarquía y no se elige como avenida.
LONGITUDINAL, TRANSVERSAL, CONECTOR, ENLACE, BORDE = "longitudinal", "transversal", "conector", "enlace", "borde"
CONTINUACION = "continuacion"
Clave = tuple[str, int]


@dataclass(frozen=True)
class RedFija:
    """Lo fijado de un recálculo (CU09, D56), en el marco local de la grilla nueva.

    - `tramos`: el eje y la jerarquía de cada tramo fijado;
    - `anclajes`: los nodos fijados donde una calle fijada seguía hacia lo que se recalcula;
    - `terreno`: el terreno entero, cuyo límite es el único que lleva calle de borde;
    - `sector`: la superficie fijada (manzanas y calles);
    - `filas_origen`: la dirección (en radianes, en este marco) de las longitudinales de la v1 de la
      alternativa. Con la calle de borde por lado, los lados que la llevan son los de la versión de
      origen, aunque la grilla nueva tenga otra orientación (D86)."""

    tramos: tuple[tuple[LineString, JerarquiaCorredor], ...]
    anclajes: tuple[Point, ...]
    terreno: Polygon
    sector: BaseGeometry
    filas_origen: float = 0.0

# La calle de borde se parte en calles donde el contorno gira esto o más (grados): cada lado de un
# rectángulo es una calle, y un contorno curvo de lados cortos es una sola (D50).
GIRO_CALLE = 45.0

# Con la calle de borde «por lado» (D86), un lado del terreno la lleva si forma con las longitudinales a
# lo sumo este ángulo (grados): está más cerca de las filas que de las transversales, y sin ella la fila
# de al lado quedaría con frente de un solo lado. Con 30° y 20° dio lo mismo en los casos (D86).
UMBRAL_PARALELO = 45.0


def _ninguna(clave: Clave) -> bool:
    """Ninguna calle es ancha: los anchos de la local, con los que se cuentan filas y cuadras."""
    return False



def limite_con_calle(
    terreno: Polygon,
    reservadas: Sequence[Polygon] = (),
    calle_borde: CalleBorde = CalleBorde.CONTORNO,
    accesos: Sequence[Point] = (),
    fijadas: Sequence[tuple[LineString, JerarquiaCorredor]] = (),
    filas: float = 0.0,
) -> BaseGeometry:
    """Por dónde va la calle de borde (D50, D59, D86). Es la copia única: la usan `_Borde`, la
    continuación de las calles de borde fijadas y los corredores (la franja de una calle de borde llega
    exacta a ese límite).

    - Con `CONTORNO` (el valor por omisión), el límite del terreno entero y el borde de cada área
      reservada; sin áreas, el borde del terreno. Es también por dónde *puede* ir una calle de borde:
      con eso se reconocen las fijadas de un recálculo y las franjas de los corredores.
    - Con `POR_LADO`, el borde de las áreas (siempre, D59) y los lados del terreno que la llevan
      (`_lleva_calle`), en el marco local: las longitudinales son paralelas al eje x. En los demás, las
      filas y las cuadras terminan contra el límite, y sus calles se conservan (se asume que siguen
      afuera, Ord. 8060, art. 20). `accesos` y `fijadas` (los tramos fijados de un recálculo) son
      parte de la regla, y `filas` es la dirección de las filas con la que se decide (en radianes; la
      de la v1 en un recálculo, `RedFija.filas_origen`).
    """
    areas = [parte.exterior for area in reservadas for parte in poligonos(area)]
    if calle_borde == CalleBorde.CONTORNO:
        return terreno.boundary if not areas else MultiLineString([terreno.exterior, *areas])
    casco = terreno.convex_hull.exterior
    con_calle = [lado.linea() for lado in lados(terreno, None) if _lleva_calle(lado, casco, accesos, fijadas, filas)]
    return MultiLineString([*con_calle, *areas])


def lados_entrantes(terreno: Polygon) -> list[LineString]:
    """Los lados del terreno fuera de su cápsula convexa: los de una entrante (D86). Con la calle de borde
    «por lado» la llevan, y si son paralelos a una familia de la grilla, la alinean con ella
    (`_Trazado._alinear_lados`)."""
    casco = terreno.convex_hull.exterior
    return [lado.linea() for lado in lados(terreno, None) if not _sobre(lado, casco)]


def _lleva_calle(lado, casco, accesos: Sequence[Point], fijadas, filas: float = 0.0) -> bool:
    """Con la calle de borde «por lado» (D86), un lado del terreno la lleva si:
    - forma con las longitudinales (`filas`: el eje x del marco local, o en un recálculo las de la v1)
      a lo sumo `UMBRAL_PARALELO`: sin ella, la fila de al lado tendría frente de un solo lado, y el
      art. 48 pide manzanas de dos fondos (D50);
    - es de una entrante (fuera de la cápsula convexa `casco`): sin ella, entre la última calle de la
      grilla y el límite quedaría una faja de cualquier ancho, que sería remanente;
    - tiene un acceso, que abre directo a ella, o
    - en un recálculo, junto a él corre una calle de borde fijada, que la nueva continúa (D56).
    Los demás cruzan la grilla de punta, y las filas terminan contra ellos sin perder el lado menor.

    En un recálculo los lados son los de la versión de origen, aunque la grilla nueva tenga otra
    orientación: un lado que no la tenía no la gana. Si no, la calle nueva terminaría contra lo fijado sin
    salida y les daría frente a lotes fijados que daban de espaldas al límite (lo encontró el barrido de
    recálculo)."""
    inclinacion = math.degrees(abs(math.remainder(lado.direccion - filas, math.pi)))
    if inclinacion <= UMBRAL_PARALELO + 1e-9 or not _sobre(lado, casco):
        return True
    linea = lado.linea()
    if any(linea.distance(acceso) <= TOLERANCIA for acceso in accesos):
        return True
    return any(_corre_junto_al_limite(eje, jerarquia, linea) for eje, jerarquia in fijadas)


@dataclass(frozen=True)
class _Forzada:
    """Una recta forzada de la grilla, con su eje en `base + signo × ancho / 2`.

    - La que continúa a una calle fijada de un recálculo (D56) tiene `signo` 0: su eje es el fijado,
      y su jerarquía, la fijada (`_Trazado.forzado`).
    - La de un lado de un área reservada alineado con la grilla (D59) tiene `base` en el lado y
      `signo` hacia el dominio: el eje va a medio ancho de su calle, que se puede elegir como
      avenida, así la posición sale del ancho (D48)."""

    base: float
    signo: float
    clave: tuple[str, int]


@dataclass(frozen=True)
class Calle:
    """Una calle entera de la red: una recta de la grilla (todos sus pedazos dentro del terreno),
    un conector de acceso o un enlace. `atraviesa` es si todas sus puntas dan al borde."""

    clave: Clave
    tramos: tuple[Tramo, ...]
    longitud: float
    atraviesa: bool

    @property
    def tipo(self) -> str:
        return self.clave[0]


@dataclass(frozen=True)
class RedGenerada:
    """La red, las calles que se eligieron como avenidas y, si no se llegó a la proporción del
    art. 12, la causa y la sugerencia (D48). `transversales_de_mas` es cuántas transversales se
    sumaron a la grilla para llegar (D53)."""

    red: RedCirculacion
    avenidas: tuple[Clave, ...]
    motivo: tuple[str, str] | None
    transversales_de_mas: int = 0


class GeneradorRed:
    def generar(
        self,
        dominio: Polygon,
        accesos: list[Point],
        estrategia: Estrategia,
        parametros: ParametrosLoteo,
        jerarquias: tuple[JerarquiaCorredor, ...],
        fija: RedFija | None = None,
        terreno: Polygon | None = None,
        reservadas: Sequence[Polygon] = (),
    ) -> RedCirculacion:
        """La red de la grilla, con sus avenidas (p. 47). `generar_con_avenidas` devuelve además
        por qué no se llegó a la proporción de avenidas, si es el caso. Con `fija` (un recálculo,
        D56) el dominio es el dominio restante, y la red devuelta es la integrada: fijada y nueva.
        Con `reservadas` (D59) el dominio es `terreno` menos las áreas, que llevan calle alrededor."""
        return self.generar_con_avenidas(
            dominio, accesos, estrategia, parametros, jerarquias, fija, terreno, reservadas
        ).red

    def generar_con_avenidas(
        self,
        dominio: Polygon,
        accesos: list[Point],
        estrategia: Estrategia,
        parametros: ParametrosLoteo,
        jerarquias: tuple[JerarquiaCorredor, ...],
        fija: RedFija | None = None,
        terreno: Polygon | None = None,
        reservadas: Sequence[Polygon] = (),
    ) -> RedGenerada:
        if estrategia.patron_red != PatronRed.GRILLA:
            raise NoImplementado(f"El patrón de red «{estrategia.patron_red}» todavía no está implementado.")
        p = parametros
        mayor, menor = jerarquia_mayor(jerarquias), jerarquia_menor(jerarquias)
        contorno = {"fija": fija, "terreno": terreno, "reservadas": tuple(reservadas)}
        trazado = _Trazado(dominio, accesos, p, menor, mayor, **contorno)
        red, calles = trazado.construir(lambda clave: False)
        if not faltante_avenidas(red, p):
            # Alcanza sin avenidas (porcentaje 0, o la jerarquía menor ya es de avenida).
            return RedGenerada(red, (), None)
        if not es_avenida(mayor, p):
            # Sin una jerarquía de avenida, la red queda como en D24 (transversales, conectores y
            # enlaces con la mayor), y el verificador marca el art. 12.
            red, _ = trazado.construir(lambda clave: clave[0] not in (LONGITUDINAL, BORDE))
            return RedGenerada(red, (), (
                f"Ninguna jerarquía de calle mide los {_numero(p.ancho_minimo_avenida)} m de una avenida: la más "
                f"ancha, «{mayor.nombre}», tiene {_numero(mayor.ancho_total)} m.",
                f"Agregá una jerarquía de al menos {_numero(p.ancho_minimo_avenida)} m entre líneas municipales "
                "(calzada más dos veredas), como el perfil 6 de la Ord. 8060, art. 14.",
            ))
        generada = self._elegir_avenidas(trazado, red, calles, p)
        if generada.motivo is None:
            return generada
        # D53: con todas las candidatas no se llega. Se suman transversales, que no les quitan
        # fondo a las filas y pueden ser avenidas, mientras la cuadra alcance el lado menor.
        extra = 1
        while True:
            otro = _Trazado(dominio, accesos, p, menor, mayor, transversales_de_mas=extra, **contorno)
            if otro.cuadra + TOLERANCIA < p.lado_minimo_manzana:
                break
            try:
                red_otra, calles_otras = otro.construir(lambda clave: False)
            except ErrorConectividad:
                extra += 1
                continue
            con_mas = self._elegir_avenidas(otro, red_otra, calles_otras, p)
            if con_mas.motivo is None:
                return replace(con_mas, transversales_de_mas=extra)
            extra += 1
        # Ni así: queda la red sin transversales de más, que es la de más lotes.
        return replace(generada, motivo=(
            "Las calles que pueden ser avenidas sin dejar a los lotes sin el fondo mínimo llegan al "
            f"{_numero(porcentaje_avenidas(generada.red, p))} % de la longitud de la red, y tampoco se llega "
            f"sumando transversales hasta cuadras de {_numero(p.lado_minimo_manzana)} m.",
            "Probá otra orientación de la grilla: con las calles longitudinales a lo largo del lado más "
            "corto del terreno hay más transversales, que pueden ser avenidas.",
        ))

    def _elegir_avenidas(self, trazado: "_Trazado", red: RedCirculacion, calles: list[Calle], p: ParametrosLoteo):
        """Las avenidas mínimas para llegar a la proporción, en el orden de prioridad (D48)."""
        elegidas: list[Clave] = []
        for calle in prioridad(red, calles, trazado.accesos):
            if not faltante_avenidas(red, p):
                break
            if calle.clave in trazado.forzado:
                continue  # continúa a una calle fijada: conserva su jerarquía (D56)
            prueba = [*elegidas, calle.clave]
            if calle.tipo in (LONGITUDINAL, BORDE) and not trazado.admite_fondo(prueba):
                continue
            nueva = trazado.intentar(prueba)
            if nueva is not None:
                elegidas, red = prueba, nueva
        if faltante_avenidas(red, p):
            return RedGenerada(red, tuple(elegidas), (
                "Las calles que pueden ser avenidas sin dejar a los lotes sin el fondo mínimo llegan al "
                f"{_numero(porcentaje_avenidas(red, p))} % de la longitud de la red.",
                "Probá otra orientación de la grilla: con las calles longitudinales a lo largo del lado más "
                "corto del terreno hay más transversales, que pueden ser avenidas.",
            ))
        # Poda: ninguna avenida sobra.
        for clave in list(reversed(elegidas)):
            prueba = [c for c in elegidas if c != clave]
            nueva = trazado.intentar(prueba)
            if nueva is not None and not faltante_avenidas(nueva, p):
                elegidas, red = prueba, nueva
        return RedGenerada(red, tuple(elegidas), None)

    @staticmethod
    def orientacion_sugerida(dominio: Polygon) -> float:
        """La orientación de la grilla que se propone antes de generar (p. 43, paso 1; D42).

        Las calles longitudinales van paralelas al lado mayor del rectángulo mínimo que
        envuelve al terreno, en grados en [0, 180): un lado y el opuesto dan la misma grilla.
        Entre dos lados iguales (un cuadrado), el de menor ángulo. En el caso de referencia da
        los 20° de su rotación. Sobre un polígono irregular es una propuesta, no un óptimo: el
        proyectista la confirma o la cambia.
        """
        vertices = list(dominio.minimum_rotated_rectangle.exterior.coords)
        lados = []
        for a, b in zip(vertices, vertices[1:]):
            orientacion = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0
            lados.append((round(math.dist(a, b), 3), orientacion))
        _, orientacion = max(lados, key=lambda lado: (lado[0], -round(lado[1], 6)))
        return orientacion


def prioridad(red: RedCirculacion, calles: Sequence[Calle], accesos: Sequence[Point]) -> list[Calle]:
    """Las calles en el orden en que se eligen como avenidas (D48, D50).

    1. Las que conectan accesos: los conectores, la calle de borde a la que abre cada acceso y, por
       cada acceso, la transversal más cercana por la red (`RedCirculacion.matriz_distancias`, la
       copia única de la distancia).
    2. Las transversales que atraviesan el terreno.
    3. Las demás transversales y los enlaces.
    4. Las demás calles de borde.
    5. Las longitudinales.

    Dentro de cada grupo, primero las que atraviesan, después la más larga, y por último la
    clave (orden estable, RNF05).
    """
    transversales = [c for c in calles if c.tipo == TRANSVERSAL]
    cercanas: set[Clave] = set()
    if transversales and accesos:
        puntos, duenas = [], []
        for calle in transversales:
            for tramo in calle.tramos:
                for nodo in (tramo.origen, tramo.destino):
                    puntos.append(Point(nodo))
                    duenas.append(calle.clave)
        for fila in np.round(red.matriz_distancias(list(accesos), puntos), 3):
            if np.isfinite(fila).any():
                cercanas.add(duenas[int(np.argmin(fila))])

    def grupo(calle: Calle) -> int:
        if calle.tipo == CONECTOR or calle.clave in cercanas:
            return 0
        if calle.tipo == BORDE and any(red.servido(acceso, calle.tramos) for acceso in accesos):
            return 0
        if calle.tipo == TRANSVERSAL and calle.atraviesa:
            return 1
        if calle.tipo in (TRANSVERSAL, ENLACE):
            return 2
        if calle.tipo == BORDE:
            return 3
        return 4

    return sorted(calles, key=lambda c: (grupo(c), not c.atraviesa, -round(c.longitud, 3), c.clave))


class _Trazado:
    """La grilla de un dominio con los anchos de cada calle: la cantidad de calles es fija, y las
    posiciones salen de los anchos (D48).

    Una calle de borde va por los lados que dice `limite_con_calle` (todo el contorno, D50, o por lado,
    D86), y adentro las longitudinales separan filas de manzanas de dos fondos, de al menos max(2 ×
    fondo mínimo, lado menor del art. 48), desde el borde interior de la calle de borde: toda manzana
    tiene calle de los dos lados, y ninguna queda como una franja de un fondo contra el límite (hasta
    el motor 0.6.0, D24). Las calles de la grilla terminan en T contra la calle de borde, o contra el
    límite en un lado sin ella.

    `transversales_de_mas` suma transversales a las que pide la longitud máxima: el generador lo
    usa cuando sin ellas no se llega a la proporción de avenidas (D53).

    Con `fija` (un recálculo, D56) el dominio es el dominio restante: la calle de borde va solo sobre
    el límite del terreno, las calles fijadas paralelas a la grilla fuerzan sus rectas, y las filas y
    las columnas se reparten en los intervalos entre los bordes de la región y esas rectas. Sin
    rectas forzadas hay un solo intervalo, con la misma aritmética de siempre.

    Con `reservadas` (D59) el dominio es `terreno` menos las áreas: la calle de borde rodea también
    las áreas, y sus lados alineados con la grilla fuerzan rectas (`_alinear_lados`). Con la calle de
    borde por lado (D86), lo mismo los lados de una entrante del terreno.
    """

    def __init__(
        self,
        dominio,
        accesos,
        p: ParametrosLoteo,
        menor: JerarquiaCorredor,
        ancha: JerarquiaCorredor,
        transversales_de_mas: int = 0,
        fija: RedFija | None = None,
        terreno: Polygon | None = None,
        reservadas: Sequence[Polygon] = (),
    ):
        self.dominio, self.accesos, self.p, self.menor, self.ancha = dominio, list(accesos), p, menor, ancha
        self.fija = fija
        self.reservadas = tuple(reservadas)
        # El terreno entero, si el dominio no lo es: el restante de un recálculo (D56) o el terreno
        # menos las áreas reservadas (D59).
        terreno = fija.terreno if fija is not None else terreno
        # El límite del terreno: donde una calle puede terminar (se asume que sigue afuera, D24).
        self.limite = dominio.exterior if terreno is None else terreno.exterior
        # Por dónde puede ir una calle de borde: el límite del terreno y el borde de las áreas (D50, D59).
        # Con eso se reconocen las calles de borde fijadas de un recálculo (D56).
        con_calle = None if terreno is None else limite_con_calle(terreno, self.reservadas)
        self.con_calle = self.limite if con_calle is None else con_calle
        entrantes = None
        if p.calle_borde == CalleBorde.POR_LADO:
            # Por dónde va la de esta grilla (D86): solo algunos lados del terreno, y los de un lado
            # donde lo fijado ya tiene la suya.
            entero = dominio if terreno is None else terreno
            con_calle = limite_con_calle(
                entero,
                self.reservadas,
                p.calle_borde,
                self.accesos,
                () if fija is None else fija.tramos,
                0.0 if fija is None else fija.filas_origen,
            )
            if lineas_entrantes := lados_entrantes(entero):
                entrantes = MultiLineString(lineas_entrantes)
        areas = None
        if self.reservadas:
            areas = MultiLineString([parte.exterior for area in self.reservadas for parte in poligonos(area)])
        self.borde = _Borde(dominio, con_calle, areas, entrantes)
        # Las calles cuya jerarquía no se elige: las que continúan a una calle fijada (D56).
        self.forzado: dict[Clave, JerarquiaCorredor] = {}
        # Las rectas forzadas de cada familia, en orden (`_Forzada`).
        self.forzadas: dict[str, list[_Forzada]] = {LONGITUDINAL: [], TRANSVERSAL: []}
        if fija is not None:
            self._continuar_bordes(fija)
        ancho = menor.ancho_total
        minx, miny, maxx, maxy = self.region(lambda clave: False)
        self.largo, self.alto = maxx - minx, maxy - miny
        profundidad = max(2 * p.fondo_minimo, p.lado_minimo_manzana)
        if fija is not None:
            self._continuar_rectas(fija, (minx, miny, maxx, maxy))
        if self.reservadas or entrantes is not None:
            self._alinear_lados((minx, miny, maxx, maxy))
        # Las filas de cada intervalo entre longitudinales forzadas, y las cuadras de cada intervalo
        # entre transversales forzadas: ninguna manzana pasa la longitud máxima, contada con el
        # ancho de la local, así ninguna la pasa elija lo que elija (una avenida solo la acorta). La
        # calle de borde ya une las longitudinales.
        self.filas_de = [
            max(1, math.floor((b - a + ancho) / (profundidad + ancho) + 1e-9)) if b > a else 0
            for a, b in self._intervalos(LONGITUDINAL, miny, maxy)
        ]
        self.n_de = [
            max(1, math.ceil((b - a + ancho) / (p.longitud_maxima_manzana + ancho) - 1e-9)) if b > a else 0
            for a, b in self._intervalos(TRANSVERSAL, minx, maxx)
        ]
        largos = [b - a for a, b in self._intervalos(TRANSVERSAL, minx, maxx)]
        for _ in range(transversales_de_mas):
            # Cada transversal de más va al intervalo de cuadras más largas (D53).
            k = max(
                (k for k in range(len(self.n_de)) if self.n_de[k] > 0),
                key=lambda k: (round(largos[k] / self.n_de[k], 6), -k),
            )
            self.n_de[k] += 1
        # Las filas útiles: un intervalo de menos de una fila no decide si una calle admite el ancho
        # de avenida (sus manzanas no llevan lotes).
        self.util_de = [b - a + 1e-9 >= profundidad for a, b in self._intervalos(LONGITUDINAL, miny, maxy)]
        self.filas = sum(self.filas_de)
        self.m = sum(max(0, f - 1) for f in self.filas_de)
        self.n = sum(self.n_de)

    @property
    def cuadra(self) -> float:
        """El largo de cada cuadra entre transversales contado con el ancho de la avenida: el tope
        de las transversales de más es que no baje del lado menor del art. 48 (D53). Contada así,
        ninguna cuadra baja elija lo que elija (una avenida solo la acorta). Con varios intervalos,
        la más corta."""
        minx, _, maxx, _ = self.region(lambda clave: False)
        cuadras = [
            ((b - a) - (n - 1) * self.ancha.ancho_total) / n
            for (a, b), n in zip(self._intervalos(TRANSVERSAL, minx, maxx), self.n_de, strict=True)
            if n > 0
        ]
        return min(cuadras) if cuadras else 0.0

    def jerarquias(self, es_ancha: Callable[[Clave], bool], tipo: str, cantidad: int) -> list[JerarquiaCorredor]:
        return [self._de(es_ancha, (tipo, k)) for k in range(cantidad)]

    def region(self, es_ancha: Callable[[Clave], bool]) -> tuple[float, float, float, float]:
        """El rectángulo donde se reparten las filas y las columnas: el del dominio sin la calle de
        borde, con el ancho de cada una de sus calles."""
        return self.borde.geometria(lambda k: self._de(es_ancha, (BORDE, k)).ancho_total).region

    def fondo(self, anchos: list[JerarquiaCorredor], alto: float) -> float:
        """El fondo común de las manzanas, con estos anchos de longitudinales (un solo intervalo)."""
        return (alto - math.fsum(j.ancho_total for j in anchos)) / (2 * self.filas)

    def admite_fondo(self, claves: Sequence[Clave]) -> bool:
        """Con estas avenidas, el fondo común sigue alcanzando el mínimo: una longitudinal o una calle
        de borde más ancha se lo quita a las filas (D48, D50). Con varios intervalos, en todos los que
        tienen al menos una fila."""
        es_ancha = lambda c: c in claves  # noqa: E731
        _, miny, _, maxy = self.region(es_ancha)
        indice = 0
        for j, (a, b) in enumerate(self._intervalos(LONGITUDINAL, miny, maxy, es_ancha)):
            partes = self.filas_de[j]
            anchos = self.jerarquias_de(es_ancha, LONGITUDINAL, indice, partes - 1)
            indice += len(anchos)
            if partes < 1 or (self.forzadas[LONGITUDINAL] and not self.util_de[j]):
                continue
            fondo = (b - a - math.fsum(w.ancho_total for w in anchos)) / (2 * partes)
            if not fondo + TOLERANCIA >= self.p.fondo_minimo:
                return False
        return True

    def jerarquias_de(self, es_ancha, tipo: str, desde: int, cantidad: int) -> list[JerarquiaCorredor]:
        return [self._de(es_ancha, (tipo, desde + k)) for k in range(max(0, cantidad))]

    def intentar(self, claves: Sequence[Clave]) -> RedCirculacion | None:
        """La red con estas avenidas, o `None` si deja un acceso sin calle o la red partida."""
        try:
            red, _ = self.construir(lambda c: c in claves)
        except ErrorConectividad:
            return None
        if red.componentes_aisladas() or not all(red.servido(a) for a in self.accesos):
            return None
        return red

    def construir(self, es_ancha: Callable[[Clave], bool]) -> tuple[RedCirculacion, list[Calle]]:
        """Traza la calle de borde y la grilla con la jerarquía de cada calle, la une a los accesos y
        la poda (D24, D40, D50). Con `fija`, además la integra con la red fijada (D56). Devuelve la
        red y sus calles enteras (solo las nuevas)."""
        dminx, dminy, dmaxx, dmaxy = self.dominio.bounds
        borde = self.borde.geometria(lambda k: self._de(es_ancha, (BORDE, k)).ancho_total)
        minx, miny, maxx, maxy = borde.region
        rectas = []
        for clave, y, j in self._lineas(LONGITUDINAL, miny, maxy, es_ancha):
            rectas.append((clave, LineString([(dminx - 1, y), (dmaxx + 1, y)]), j))
        for clave, x, j in self._lineas(TRANSVERSAL, minx, maxx, es_ancha):
            rectas.append((clave, LineString([(x, dminy - 1), (x, dmaxy + 1)]), j))
        registro: list[tuple[Clave, LineString]] = []
        piezas: list[tuple[LineString, JerarquiaCorredor]] = []
        for clave, recta, jerarquia in rectas:
            for pieza in lineas(interseccion(recta, self.dominio)):
                piezas.append((pieza, jerarquia))
                registro.append((clave, pieza))
        for clave, segmento in borde.ejes:
            piezas.append((segmento, self._de(es_ancha, clave)))
            registro.append((clave, segmento))
        red = RedCirculacion()
        _armar_tramos(red, piezas)
        _quitar_afuera(red, borde.afuera, [segmento for _, segmento in borde.ejes])
        if self.fija is not None:
            _integrar(red, self.fija, self.limite)
        registro += _conectar_accesos(red, self.dominio, self.accesos, lambda k: self._de(es_ancha, (CONECTOR, k)))
        registro += _podar_tramos_sin_salida(
            red, self.dominio, self.accesos, lambda k: self._de(es_ancha, (ENLACE, k)), self.limite
        )
        return red, _calles(red, registro, self.limite)

    def _lineas(self, familia: str, lo: float, hi: float, es_ancha) -> list[tuple[Clave, float, JerarquiaCorredor]]:
        """Las rectas de una familia entre `lo` y `hi`: (clave, posición, jerarquía), en orden. En cada
        intervalo entre las forzadas, las libres se reparten como siempre: longitudinales separadas
        por filas de dos fondos, transversales por cuadras iguales; las posiciones salen de los anchos."""
        cantidades = self.filas_de if familia == LONGITUDINAL else self.n_de
        forzadas = self.forzadas[familia]
        resultado = []
        indice = 0
        for j, (a, b) in enumerate(self._intervalos(familia, lo, hi, es_ancha)):
            partes = cantidades[j]
            anchos = self.jerarquias_de(es_ancha, familia, indice, partes - 1)
            if partes >= 1:
                anterior = 0.0
                if familia == LONGITUDINAL:
                    fondo = (b - a - math.fsum(w.ancho_total for w in anchos)) / (2 * partes)
                    for k, jerarquia in enumerate(anchos):
                        posicion = a + (2 * k + 2) * fondo + anterior + jerarquia.ancho_total / 2
                        anterior += jerarquia.ancho_total
                        resultado.append(((familia, indice + k), posicion, jerarquia))
                else:
                    manzana = (b - a - math.fsum(w.ancho_total for w in anchos)) / partes
                    for k, jerarquia in enumerate(anchos):
                        posicion = a + (k + 1) * manzana + anterior + jerarquia.ancho_total / 2
                        anterior += jerarquia.ancho_total
                        resultado.append(((familia, indice + k), posicion, jerarquia))
            indice += len(anchos)
            if j < len(forzadas):
                posicion, jerarquia = self._posicion(forzadas[j], es_ancha)
                resultado.append((forzadas[j].clave, posicion, jerarquia))
        return resultado

    def _intervalos(self, familia: str, lo: float, hi: float, es_ancha=None) -> list[tuple[float, float]]:
        """Los intervalos entre los bordes de la región y las rectas forzadas de la familia, con los
        anchos de `es_ancha` (sin ella, todas locales)."""
        resultado, a = [], lo
        for forzada in self.forzadas[familia]:
            posicion, jerarquia = self._posicion(forzada, es_ancha)
            resultado.append((a, posicion - jerarquia.ancho_total / 2))
            a = posicion + jerarquia.ancho_total / 2
        resultado.append((a, hi))
        return resultado

    def _posicion(self, forzada: _Forzada, es_ancha=None) -> tuple[float, JerarquiaCorredor]:
        """El eje de una recta forzada y su jerarquía, con los anchos de `es_ancha`."""
        jerarquia = self._de(es_ancha or _ninguna, forzada.clave)
        if forzada.signo == 0:
            return forzada.base, jerarquia
        return forzada.base + forzada.signo * jerarquia.ancho_total / 2, jerarquia

    def _continuar_bordes(self, fija: RedFija) -> None:
        """Una calle de borde nueva sobre el mismo lado del terreno que una calle de borde fijada la
        continúa: conserva su jerarquía (D56). Si no, con otro ancho, su eje quedaría corrido."""
        bordes = [(eje, j) for eje, j in fija.tramos if _corre_junto_al_limite(eje, j, self.con_calle)]
        for i, (a, b) in enumerate(self.borde.lados):
            calle = self.borde.calle_de.get(i)
            if calle is None or (BORDE, calle) in self.forzado:
                continue
            direccion = unitario(a, b)
            normal = np.array([-direccion[1], direccion[0]])
            for eje, jerarquia in bordes:
                c, d = np.asarray(eje.coords[0]), np.asarray(eje.coords[-1])
                if not paralelos(angulo(tuple(c), tuple(d)), angulo(tuple(a), tuple(b))):
                    continue
                medio = (c + d) / 2
                if abs(abs(float((medio - a) @ normal)) - jerarquia.ancho_total / 2) <= 2 * TOLERANCIA:
                    self.forzado[(BORDE, calle)] = jerarquia
                    break

    def _continuar_rectas(self, fija: RedFija, region) -> None:
        """Las calles fijadas paralelas a una familia de la grilla fuerzan una recta sobre su eje: la
        grilla nueva las continúa (D56). Las que caen fuera de la región (o en la calle de borde) no."""
        minx, miny, maxx, maxy = region
        candidatas: dict[str, list[tuple[float, JerarquiaCorredor]]] = {LONGITUDINAL: [], TRANSVERSAL: []}
        for eje, jerarquia in fija.tramos:
            a, b = eje.coords[0], eje.coords[-1]
            if math.dist(a, b) <= TOLERANCIA or _corre_junto_al_limite(eje, jerarquia, self.con_calle):
                continue
            direccion = angulo(a, b)
            if paralelos(direccion, 0.0):
                candidatas[LONGITUDINAL].append(((a[1] + b[1]) / 2, jerarquia))
            elif paralelos(direccion, math.pi / 2):
                candidatas[TRANSVERSAL].append(((a[0] + b[0]) / 2, jerarquia))
        numero = 0
        for familia, (lo, hi) in ((LONGITUDINAL, (miny, maxy)), (TRANSVERSAL, (minx, maxx))):
            unidas: list[tuple[float, JerarquiaCorredor]] = []
            for posicion, jerarquia in sorted(candidatas[familia], key=lambda par: (round(par[0], 3), par[1].orden)):
                if unidas and posicion - unidas[-1][0] <= TOLERANCIA:
                    continue  # la misma calle, de otro tramo
                unidas.append((posicion, jerarquia))
            for posicion, jerarquia in unidas:
                mitad = jerarquia.ancho_total / 2
                anterior = self.forzadas[familia][-1] if self.forzadas[familia] else None
                if posicion - mitad <= lo or posicion + mitad >= hi:
                    continue
                if anterior is not None:
                    posicion_anterior, jerarquia_anterior = self._posicion(anterior)
                    if posicion - mitad < posicion_anterior + jerarquia_anterior.ancho_total / 2:
                        continue
                clave = (CONTINUACION, numero)
                numero += 1
                self.forzado[clave] = jerarquia
                self.forzadas[familia].append(_Forzada(posicion, 0.0, clave))
            if familia == LONGITUDINAL and not self._filas_posibles(lo, hi):
                # Las longitudinales forzadas dejan intervalos donde no entran filas de lotes (con
                # otra orientación, el largo de una cuadra fijada no es un múltiplo de una fila):
                # no se fuerzan, y la grilla reparte sus filas como siempre.
                for forzada in self.forzadas[familia]:
                    del self.forzado[forzada.clave]
                self.forzadas[familia] = []

    def _alinear_lados(self, region) -> None:
        """Los lados de las áreas reservadas (D59) y, con la calle de borde por lado, los de una entrante
        del terreno (D86), paralelos a una familia de la grilla, fuerzan una recta sobre el eje de su
        calle, como las calles fijadas de un recálculo (D56).

        La calle del lado sigue derecho como calle de la grilla, y las filas de dos fondos y las
        cuadras se reparten entre esas rectas: las manzanas que lindan con el lado tienen dos fondos y
        el lado menor del art. 48. Sin alinear, la grilla pasaría a cualquier distancia del lado y
        dejaría manzanas angostas entre las dos calles.

        - Un lado se alinea si se aparta de una recta de la familia a lo sumo `DESVIO_ALINEACION`. La
          recta pasa a medio ancho del punto del lado más adentro del dominio, así la calle no pisa el
          área; lo que queda entre la calle y el área es vereda (`corredores`).
        - Se fuerza de a una recta, en orden estable, solo si después siguen entrando filas
          (`_filas_posibles`) o cuadras de al menos el lado menor, si no se pisa con otra forzada y si
          no cruza otra área. Si no, el lado queda con su calle de borde.
        - Un lado sobre la misma recta que otro ya alineado es la misma calle.
        """
        minx, miny, maxx, maxy = region
        dminx, dminy, dmaxx, dmaxy = self.dominio.bounds
        areas = [parte for area in self.reservadas for parte in poligonos(area)]
        candidatas = []
        for i, (a, b) in enumerate(self.borde.lados):
            alineable = self.borde.de_area[i] or self.borde.entrante[i]
            if not (self.borde.en_limite[i] and alineable) or math.dist(a, b) <= DESVIO_ALINEACION:
                continue
            for familia, eje in ((LONGITUDINAL, 1), (TRANSVERSAL, 0)):
                if abs(float(a[eje] - b[eje])) > DESVIO_ALINEACION:
                    continue
                signo = 1.0 if self.borde._normal(i)[eje] > 0 else -1.0
                base = float(max(a[eje], b[eje]) if signo > 0 else min(a[eje], b[eje]))
                candidatas.append((familia, base, signo, i, eje))
        for familia, base, signo, i, eje in sorted(candidatas, key=lambda c: (c[0], round(c[1], 3), c[2], c[3])):
            lo, hi = (miny, maxy) if familia == LONGITUDINAL else (minx, maxx)
            nueva = _Forzada(base, signo, (BORDE, self.borde.calle_de[i]))
            posicion, jerarquia = self._posicion(nueva)
            mitad = jerarquia.ancho_total / 2
            if posicion - mitad <= lo + TOLERANCIA or posicion + mitad >= hi - TOLERANCIA:
                continue  # la calle del área ya es el borde de la región
            misma = next(
                (f for f in self.forzadas[familia] if abs(self._posicion(f)[0] - posicion) <= TOLERANCIA), None
            )
            if misma is not None:
                if misma.clave[0] == BORDE:
                    # Otro lado (de otra área) sobre la misma recta: es la misma calle. Si está del
                    # otro lado de la recta, la calle queda local: con otro ancho no podrían seguir
                    # las dos sobre el mismo eje.
                    self.borde.calle_de[i] = misma.clave[1]
                    self.borde.alineados[i] = (eje, base, signo)
                    if misma.signo != signo:
                        self.forzado[misma.clave] = self.menor
                continue
            if eje == 1:
                recta = LineString([(dminx - 1, posicion), (dmaxx + 1, posicion)])
            else:
                recta = LineString([(posicion, dminy - 1), (posicion, dmaxy + 1)])
            if any(recta.intersection(area).length > TOLERANCIA for area in areas):
                continue
            prueba = sorted([*self.forzadas[familia], nueva], key=lambda f: round(self._posicion(f)[0], 6))
            if any(
                self._posicion(f)[0] + self._posicion(f)[1].ancho_total / 2
                > self._posicion(g)[0] - self._posicion(g)[1].ancho_total / 2 + TOLERANCIA
                for f, g in zip(prueba, prueba[1:])
            ):
                continue
            anteriores = self.forzadas[familia]
            self.forzadas[familia] = prueba
            if self._reparto_posible(familia, lo, hi):
                self.borde.alineados[i] = (eje, base, signo)
            else:
                self.forzadas[familia] = anteriores

    def _reparto_posible(self, familia: str, lo: float, hi: float) -> bool:
        """Con las rectas forzadas de la familia, siguen entrando filas de lotes (longitudinales) o
        cuadras de al menos el lado menor del art. 48 (transversales) en cada intervalo."""
        if familia == LONGITUDINAL:
            return self._filas_posibles(lo, hi)
        return all(b - a + TOLERANCIA >= self.p.lado_minimo_manzana for a, b in self._intervalos(familia, lo, hi))

    def _filas_posibles(self, lo: float, hi: float) -> bool:
        """En cada intervalo entre las longitudinales forzadas entran filas cuyos lotes tienen un fondo
        posible: con las filas que pone la grilla, el fondo común no baja del mínimo ni pasa el que
        admite la relación fondo/frente con el frente objetivo (D43)."""
        p, ancho = self.p, self.menor.ancho_total
        profundidad = max(2 * p.fondo_minimo, p.lado_minimo_manzana)
        maximo = p.relacion_fondo_frente_max * p.frente_objetivo
        for a, b in self._intervalos(LONGITUDINAL, lo, hi):
            alto = b - a
            if alto + TOLERANCIA < profundidad:
                return False
            filas = max(1, math.floor((alto + ancho) / (profundidad + ancho) + 1e-9))
            fondo = (alto - (filas - 1) * ancho) / (2 * filas)
            if fondo > maximo + TOLERANCIA:
                return False
        return True

    def _de(self, es_ancha, clave: Clave) -> JerarquiaCorredor:
        if clave in self.forzado:
            return self.forzado[clave]
        return self.ancha if es_ancha(clave) else self.menor


def _corre_junto_al_limite(eje: LineString, jerarquia: JerarquiaCorredor, limite) -> bool:
    """El eje corre a medio ancho del límite del terreno en toda su extensión: es una calle de borde
    (D50), como en `corredores._hacia_el_limite`."""
    a, b = np.asarray(eje.coords[0]), np.asarray(eje.coords[-1])
    if math.dist(a, b) <= TOLERANCIA:
        return False
    direccion = unitario(a, b)
    mitad = jerarquia.ancho_total / 2
    for normal in (np.array([-direccion[1], direccion[0]]), np.array([direccion[1], -direccion[0]])):
        puntos = [a + (b - a) * t + normal * mitad for t in (0.25, 0.5, 0.75)]
        if all(limite.distance(Point(p)) <= 2 * TOLERANCIA for p in puntos):
            return True
    return False


def _integrar(red: RedCirculacion, fija: RedFija, limite) -> None:
    """Integra la red nueva con la fijada (el `integrar` de la p. 44; D56).

    1. Los tramos fijados entran a la red marcados (`Tramo.fijado`): la poda no los toca.
    2. Cada punta de una calle nueva que toca lo fijado (sin estar sobre el límite del terreno) se
       prolonga en su dirección hasta el primer eje fijado: si cae en medio de un tramo fijado, ese
       tramo se parte en dos tramos fijados (un empalme). Si en esa dirección no hay ningún eje
       fijado cerca, se une al nodo fijado más cercano, a menos de un ancho de calle.
    3. Cada anclaje que quedó sin calle nueva se une con la prolongación de cada calle fijada que
       llega a él, hasta el primer eje nuevo, si la prolongación cruza lo fijado solo en el cruce.
    """
    # Un pedazo de calle nueva que quedó dentro de lo fijado, o encima de una calle fijada (una recta
    # forzada que corre por el borde del sector), no es calle nueva: lo fijado ya tiene la suya. Si
    # quedara, al prolongarlo partiría el tramo fijado sin que llegue ninguna calle (D86).
    adentro = fija.sector.buffer(-TOLERANCIA)
    ejes_fijados = [eje for eje, _ in fija.tramos]
    for tramo in red.tramos():
        medio = tramo.eje.interpolate(0.5, normalized=True)
        puntos = (Point(tramo.eje.coords[0]), medio, Point(tramo.eje.coords[-1]))
        encima = any(all(eje.distance(p) <= TOLERANCIA for p in puntos) for eje in ejes_fijados)
        if encima or adentro.contains(medio):
            red.quitar_tramo(tramo)
    for eje, jerarquia in fija.tramos:
        red.agregar_tramo(eje.coords[0], eje.coords[-1], eje, jerarquia, fijado=True)
    if not fija.tramos:
        return
    alcance = 2 * max(j.ancho_total for _, j in fija.tramos)

    for nodo in red.nodos():
        if not red.contiene(nodo) or red.grado(nodo) != 1:
            continue
        (tramo,) = red.tramos_en(nodo)
        punto = Point(nodo)
        if tramo.fijado or limite.distance(punto) <= TOLERANCIA or fija.sector.distance(punto) > TOLERANCIA:
            continue
        otro = tramo.destino if nodo == tramo.origen else tramo.origen
        direccion = unitario(otro, nodo)
        rayo = LineString([nodo, (nodo[0] + direccion[0] * alcance, nodo[1] + direccion[1] * alcance)])
        fijos = [t for t in red.tramos() if t.fijado]
        cruces = sorted(
            (round(Point(c).distance(punto), 6), c)
            for t in fijos
            for c in _coordenadas(rayo.intersection(t.eje))
            if Point(c).distance(punto) > TOLERANCIA
        )
        if cruces:
            destino = red.partir_en(Point(cruces[0][1]))
            red.quitar_tramo(tramo)
            # Nunca se pisa un tramo que ya une esos nodos (uno fijado, sobre todo).
            if not red.tiene_tramo(otro, destino):
                red.agregar_tramo(otro, destino, None, tramo.jerarquia)
            continue
        extremos = sorted(
            (round(math.dist(n, nodo), 6), n) for t in fijos for n in (t.origen, t.destino) if math.dist(n, nodo) > TOLERANCIA
        )
        if extremos and extremos[0][0] <= alcance / 2 and not red.tiene_tramo(nodo, extremos[0][1]):
            red.agregar_tramo(nodo, extremos[0][1], None, tramo.jerarquia)

    minx, miny, maxx, maxy = fija.terreno.bounds
    largo = math.hypot(maxx - minx, maxy - miny)
    terreno = fija.terreno.buffer(TOLERANCIA)
    for anclaje in fija.anclajes:
        nodo = red.nodo(anclaje)
        if not red.contiene(nodo):
            continue
        llegan = red.tramos_en(nodo)
        if any(not t.fijado for t in llegan):
            continue
        direcciones = []
        for t in llegan:
            otro = t.destino if nodo == t.origen else t.origen
            direccion = unitario(otro, nodo)
            # Si otra calle fijada ya sigue derecho desde el anclaje, no hay nada que continuar.
            sigue = any(
                float(unitario(nodo, u.destino if nodo == u.origen else u.origen) @ direccion) > math.cos(math.radians(1))
                for u in llegan
                if u is not t
            )
            if not sigue:
                direcciones.append((t, direccion))
        for t, direccion in direcciones:
            rayo = LineString([nodo, (nodo[0] + direccion[0] * largo, nodo[1] + direccion[1] * largo)])
            cruces = sorted(
                (round(Point(c).distance(Point(nodo)), 6), c)
                for u in red.tramos()
                if not u.fijado
                for c in _coordenadas(rayo.intersection(u.eje))
                if Point(c).distance(Point(nodo)) > TOLERANCIA
            )
            if not cruces:
                continue
            segmento = LineString([nodo, cruces[0][1]])
            if not terreno.covers(segmento) or segmento.intersection(fija.sector).length > alcance:
                continue
            destino = red.partir_en(Point(cruces[0][1]))
            if not red.tiene_tramo(nodo, destino):
                red.agregar_tramo(nodo, destino, None, t.jerarquia)


def _quitar_afuera(red: RedCirculacion, afuera, ejes_borde: list[LineString]) -> None:
    """Saca los pedazos de las calles de la grilla que quedan entre la calle de borde y el límite:
    la grilla termina en T contra la calle de borde (D50). Un tramo de la calle de borde no se
    toca, aunque en un contorno cóncavo los trapecios de afuera lleguen a cubrirlo."""
    if afuera is None or afuera.is_empty:
        return
    if afuera.geom_type == "GeometryCollection":
        # En un dominio restante en piezas (D56) el recorte puede dejar líneas sueltas: solo cuenta
        # la superficie.
        afuera = union(poligonos(afuera))
    for tramo in red.tramos():
        medio = tramo.eje.interpolate(0.5, normalized=True)
        if any(eje.distance(medio) <= TOLERANCIA for eje in ejes_borde):
            continue
        if afuera.contains(medio) and afuera.boundary.distance(medio) > TOLERANCIA:
            red.quitar_tramo(tramo)


@dataclass(frozen=True)
class _GeometriaBorde:
    """La calle de borde con unos anchos: los ejes (clave, segmento), lo que queda entre los ejes y
    el límite (`afuera`), y el rectángulo del dominio sin la calle (`region`)."""

    ejes: tuple[tuple[Clave, LineString], ...]
    afuera: object
    region: tuple[float, float, float, float]


class _Borde:
    """La calle de borde de un dominio y cómo se parte en calles (D50).

    Los lados son los del contorno, con los tramos colineales unidos, en sentido antihorario: el
    interior queda a la izquierda. La calle recorre todos los lados, y se parte en calles donde el
    contorno gira `GIRO_CALLE` o más: un rectángulo tiene cuatro, y un contorno curvo de muchos
    lados cortos, una sola.

    El eje de cada lado va a medio ancho de su calle, y el borde interior de la calle, a un ancho:
    dos lados seguidos se cortan donde se cruzan sus paralelas (a inglete).

    Con `limite` (por dónde va la calle de borde: `limite_con_calle`) el dominio puede estar en varias
    piezas, cada una con su anillo exterior y sus agujeros, y solo los lados sobre el límite llevan
    calle de borde:
    - en un recálculo (D56), un lado contra lo fijado tiene ancho 0, no es calle y corta la calle de
      borde; un agujero que es todo fijado no la lleva;
    - con áreas reservadas (D59), los lados contra un área llevan calle, también los de un agujero
      (recorrido en sentido horario, con el dominio a la izquierda). `areas` es el borde de las
      áreas: la calle se parte en calles donde pasa del terreno a un área (`de_area`);
    - con la calle de borde por lado (D86), un lado del terreno sin ella tiene ancho 0, como uno contra
      lo fijado: la calle de borde termina contra él, en el límite. `entrantes` son los lados de una
      entrante (`lados_entrantes`), que se alinean como los de un área (`entrante`).
    `alineados` son los lados de un área o de una entrante cuya calle es una recta de la grilla:
    `_Trazado` la traza entera, y acá no se repite su eje.
    """

    def __init__(self, dominio, limite=None, areas=None, entrantes=None):
        self.dominio = dominio
        # Con `limite`, el dominio puede tener ranuras entre lados con calle (D56, D59).
        self.con_ranuras = limite is not None
        if limite is None:
            anillos = [[(lado, True) for lado in lados(dominio, None)]]
        else:
            anillos = []
            for parte in poligonos(dominio):
                anillos.append([(lado, lado.toca) for lado in lados(parte, limite)])
                for agujero in parte.interiors:
                    anillo = [(lado, lado.toca) for lado in lados_de_agujero(agujero, limite)]
                    if any(toca for _, toca in anillo):
                        anillos.append(anillo)
        self.lados: list[tuple[np.ndarray, np.ndarray]] = []
        self.en_limite: list[bool] = []
        self.de_area: list[bool] = []
        # Los lados de una entrante del terreno (D86): con «por lado», se alinean como los de un área.
        self.entrante: list[bool] = []
        self.anillos: list[list[int]] = []
        self.alineados: dict[int, tuple[int, float, float]] = {}
        for anillo in anillos:
            indices = []
            for lado, en_limite in anillo:
                indices.append(len(self.lados))
                self.lados.append((np.asarray(lado.inicio), np.asarray(lado.fin)))
                self.en_limite.append(en_limite)
                self.de_area.append(en_limite and areas is not None and _sobre(lado, areas))
                self.entrante.append(en_limite and entrantes is not None and _sobre(lado, entrantes))
            self.anillos.append(indices)
        self.calle_de: dict[int, int] = {}
        calle = -1
        for indices in self.anillos:

            def corta(k: int) -> bool:
                anterior, actual = indices[k - 1], indices[k]
                return (
                    not self.en_limite[anterior]
                    or self.de_area[anterior] != self.de_area[actual]
                    or self._giro(anterior, actual) >= GIRO_CALLE
                )

            orden = list(range(len(indices)))
            cortes = [k for k in orden if corta(k)]
            if cortes:
                orden = orden[cortes[0] :] + orden[: cortes[0]]
            for posicion, k in enumerate(orden):
                i = indices[k]
                if not self.en_limite[i]:
                    continue
                if posicion == 0 or corta(k):
                    calle += 1
                self.calle_de[i] = calle
        self.cantidad_calles = calle + 1

    def _direccion(self, i: int) -> np.ndarray:
        return unitario(*self.lados[i])

    def _normal(self, i: int) -> np.ndarray:
        d = self._direccion(i)
        return np.array([-d[1], d[0]])  # hacia adentro: el anillo va en sentido antihorario

    def _giro(self, i: int, j: int) -> float:
        u, v = self._direccion(i), self._direccion(j)
        return abs(math.degrees(math.remainder(math.atan2(v[1], v[0]) - math.atan2(u[1], u[0]), math.tau)))

    def geometria(self, ancho_de: Callable[[int], float]) -> _GeometriaBorde:
        """Los ejes, lo de afuera y la región, con el ancho de cada calle de borde."""
        eje = self._paralela(0.5, ancho_de)
        interior = self._paralela(1.0, ancho_de)
        ejes = tuple(
            ((BORDE, self.calle_de[i]), LineString([eje[i][0], eje[i][1]]))
            for i in range(len(self.lados))
            if self.en_limite[i] and i not in self.alineados
        )
        region = diferencia(self.dominio, self._lado_de_afuera(interior))
        return _GeometriaBorde(ejes, self._lado_de_afuera(eje), region.bounds)

    def _paralela(self, factor: float, ancho_de) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """El tramo de cada lado sobre el anillo paralelo a los lados, a `factor` × ancho de la calle de
        cada lado: (dónde empieza, dónde termina). Un lado contra lo fijado tiene ancho 0."""
        tramos: list = [None] * len(self.lados)
        for indices in self.anillos:
            rectas = [self._recta(i, factor * ancho_de(self.calle_de[i]) if self.en_limite[i] else 0.0) for i in indices]
            vertices = [self._esquina(indices, rectas, k) for k in range(len(rectas))]
            for k, i in enumerate(indices):
                tramos[i] = (vertices[k], vertices[(k + 1) % len(vertices)])
        return tramos

    def _recta(self, i: int, distancia: float):
        """La recta (punto, dirección) paralela al lado `i` a `distancia` hacia el dominio. Un lado
        contra lo fijado no tiene calle: su recta es el lado. Un lado alineado con la grilla (D59)
        tiene por recta la de la grilla: paralela a un eje del marco, a `distancia` de su base."""
        if i in self.alineados:
            eje, base, signo = self.alineados[i]
            sentido = self._direccion(i)
            direccion = np.array([1.0, 0.0]) if eje == 1 else np.array([0.0, 1.0])
            if float(direccion @ sentido) < 0:
                direccion = -direccion
            punto = np.array(self.lados[i][0], dtype=float)
            punto[eje] = base + signo * distancia
            return punto, direccion
        if self.en_limite[i]:
            return self.lados[i][0] + self._normal(i) * distancia, self._direccion(i)
        return self.lados[i][0], self._direccion(i)

    def _esquina(self, indices: list[int], rectas, k: int) -> tuple[float, float]:
        """Donde se cruzan las paralelas del lado anterior y del lado `k`. Entre un lado con calle y
        uno contra lo fijado (de ancho 0) casi paralelos, el cruce se iría lejos: va el pie de la
        paralela del lado con calle en el vértice que comparten (D56)."""
        punto = _cruce(rectas[k - 1], rectas[k])
        anterior, actual = indices[k - 1], indices[k]
        if self.en_limite[anterior] == self.en_limite[actual] and not (self.con_ranuras and self.en_limite[actual]):
            return punto
        if self.en_limite[anterior] == self.en_limite[actual]:
            # En un recálculo o con áreas, dos lados con calle casi opuestos (una ranura del dominio):
            # el cruce se iría lejos, y va el pie de la paralela del lado anterior en el vértice.
            vertice = self.lados[actual][0]
            desplazamiento = float(np.linalg.norm(rectas[k - 1][0] - self.lados[anterior][0]))
            if math.dist(punto, (float(vertice[0]), float(vertice[1]))) <= 10 * desplazamiento + 1:
                return punto
            pie = vertice + self._normal(anterior) * desplazamiento
            return (float(pie[0]), float(pie[1]))
        vertice = self.lados[actual][0]
        con_calle, recta = (anterior, rectas[k - 1]) if self.en_limite[anterior] else (actual, rectas[k])
        desplazamiento = float(np.linalg.norm(recta[0] - self.lados[con_calle][0]))
        if math.dist(punto, (float(vertice[0]), float(vertice[1]))) <= 10 * desplazamiento + 1:
            return punto
        pie = vertice + self._normal(con_calle) * desplazamiento
        return (float(pie[0]), float(pie[1]))

    def _lado_de_afuera(self, paralela):
        """Lo que queda entre la paralela y el límite: un trapecio por lado con calle, entre el lado y
        su tramo de paralela."""
        trapecios = []
        for i, (a, b) in enumerate(self.lados):
            if not self.en_limite[i]:
                continue
            inicio, fin = paralela[i]
            trapecio = Polygon([a, b, fin, inicio])
            if trapecio.is_valid and trapecio.area > 0:
                trapecios.append(trapecio)
        afuera = interseccion(union(trapecios), self.dominio)
        if afuera.geom_type == "GeometryCollection":
            # En un dominio restante en piezas (D56) el recorte puede dejar líneas sueltas junto a la
            # superficie, y un overlay con geometrías mixtas falla: solo cuenta la superficie.
            afuera = union(poligonos(afuera))
        return afuera


def _sobre(lado, referencia) -> bool:
    """El lado corre sobre `referencia`: sus puntas y su punto medio están a la tolerancia."""
    a, b = np.asarray(lado.inicio), np.asarray(lado.fin)
    return all(referencia.distance(Point(p)) <= TOLERANCIA for p in (a, b, (a + b) / 2))


def _cruce(recta_a, recta_b) -> tuple[float, float]:
    """Donde se cruzan dos rectas (punto, dirección). Si son paralelas, el punto de la segunda."""
    (pa, da), (pb, db) = recta_a, recta_b
    det = da[0] * db[1] - da[1] * db[0]
    if abs(det) < 1e-12:
        return (float(pb[0]), float(pb[1]))
    t = ((pb[0] - pa[0]) * db[1] - (pb[1] - pa[1]) * db[0]) / det
    punto = pa + da * t
    return (float(punto[0]), float(punto[1]))


def _calles(red: RedCirculacion, registro: list[tuple[Clave, LineString]], borde) -> list[Calle]:
    """Agrupa los tramos de la red por la calle de la que salieron: un tramo es de una calle si
    sus dos puntas y su punto medio están sobre ella. `borde` es el límite del terreno: una calle
    atraviesa si todas sus puntas dan a él. Los tramos fijados de un recálculo no son de ninguna
    calle nueva (D56)."""
    por_calle: dict[Clave, list[Tramo]] = {}
    for tramo in red.tramos():
        if tramo.fijado:
            continue
        puntos = [Point(tramo.eje.coords[0]), Point(tramo.eje.coords[-1]), tramo.eje.interpolate(0.5, normalized=True)]
        clave = next(
            (c for c, linea in registro if all(linea.distance(punto) <= TOLERANCIA for punto in puntos)), None
        )
        if clave is not None:
            por_calle.setdefault(clave, []).append(tramo)
    calles = []
    for clave in sorted(por_calle):
        tramos = por_calle[clave]
        grados = Counter(nodo for t in tramos for nodo in (t.origen, t.destino))
        puntas = [nodo for nodo, grado in sorted(grados.items()) if grado == 1]
        atraviesa = bool(puntas) and all(borde.distance(Point(n)) <= TOLERANCIA for n in puntas)
        calles.append(Calle(clave, tuple(tramos), math.fsum(t.longitud for t in tramos), atraviesa))
    return calles


def _armar_tramos(red: RedCirculacion, piezas: list[tuple[LineString, JerarquiaCorredor]]) -> None:
    """Parte cada eje en sus cruces con los demás: cada parte es un tramo.

    Los puntos de corte a menos de la tolerancia (1 cm) de otro son el mismo nodo para todas las
    piezas: primero cuentan las puntas de las piezas, después los cruces. Si no, un cruce que cae
    a milímetros de la punta de una pieza deja un pedacito que se descarta y abre la red (lo
    encontró la calle de borde de la sesión 8 en el barrido, D50).
    """
    cortes_de: list[list[Point]] = []
    for i, (pieza, _) in enumerate(piezas):
        cortes = []
        for j, (otra, _) in enumerate(piezas):
            if i != j:
                cortes += [Point(c) for c in _coordenadas(pieza.intersection(otra))]
        cortes_de.append(cortes)
    casilleros: dict[tuple[int, int], list[Point]] = {}

    def nodo(punto: Point) -> Point:
        cx, cy = math.floor(punto.x / TOLERANCIA), math.floor(punto.y / TOLERANCIA)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for existente in casilleros.get((cx + dx, cy + dy), ()):
                    if math.hypot(existente.x - punto.x, existente.y - punto.y) <= TOLERANCIA:
                        return existente
        casilleros.setdefault((cx, cy), []).append(punto)
        return punto

    puntas = [(nodo(Point(p.coords[0])), nodo(Point(p.coords[-1]))) for p, _ in piezas]
    for (pieza, jerarquia), (inicio, fin), cortes in zip(piezas, puntas, cortes_de, strict=True):
        puntos = [inicio, fin, *(nodo(c) for c in sorted(cortes, key=lambda c: (round(c.x, 6), round(c.y, 6))))]
        posiciones = sorted({round(pieza.project(c), 3): c for c in puntos}.items())
        for (_, a), (_, b) in zip(posiciones, posiciones[1:]):
            if a.distance(b) > TOLERANCIA:
                red.agregar_tramo(a, b, None, jerarquia)


def _conectar_accesos(
    red: RedCirculacion, dominio: Polygon, accesos: list[Point], jerarquia_de: Callable[[int], JerarquiaCorredor]
) -> list[tuple[Clave, LineString]]:
    """Une cada acceso con la red (en orden A1, A2…) y devuelve los conectores que agregó.

    - Si el acceso ya abre a una calle (cae dentro de su ancho), no hace falta nada.
    - Si no, un conector perpendicular al lado del terreno llega hasta el primer eje.
    - Si ese rayo no encuentra la red, se une al punto más cercano.
    - En ambos casos el conector tiene que quedar dentro del terreno.
    """
    conectores = []
    for k, acceso in enumerate(accesos, 1):
        if red.servido(acceso):
            continue
        destino = _rayo_hacia_la_red(red, dominio, acceso) or _punto_mas_cercano(red, dominio, acceso)
        if destino is None:
            raise ErrorConectividad(
                f"El acceso A{k} no se puede unir a la red de circulación sin salir del terreno.",
                SUGERENCIA,
                acceso,
            )
        nodo = red.partir_en(destino)
        red.agregar_tramo(acceso, nodo, None, jerarquia_de(k))
        conectores.append(((CONECTOR, k), LineString([(acceso.x, acceso.y), nodo])))
    return conectores


def _rayo_hacia_la_red(red: RedCirculacion, dominio: Polygon, acceso: Point) -> Point | None:
    # El dominio restante de un recálculo puede estar en varias piezas (D56).
    anillos = [list(dominio.exterior.coords)] if isinstance(dominio, Polygon) else [
        list(parte.exterior.coords) for parte in poligonos(dominio)
    ]
    lado = next(
        (
            (a, b)
            for anillo in anillos
            for a, b in zip(anillo, anillo[1:])
            if LineString([a, b]).distance(acceso) <= TOLERANCIA
        ),
        None,
    )
    if lado is None:
        return None
    direccion = unitario(*lado)
    hacia_adentro = None
    for normal in ((-direccion[1], direccion[0]), (direccion[1], -direccion[0])):
        if dominio.contains(Point(acceso.x + normal[0] / 2, acceso.y + normal[1] / 2)):
            hacia_adentro = normal
            break
    if hacia_adentro is None:
        return None
    minx, miny, maxx, maxy = dominio.bounds
    alcance = math.hypot(maxx - minx, maxy - miny) + 1
    rayo = LineString(
        [(acceso.x, acceso.y), (acceso.x + hacia_adentro[0] * alcance, acceso.y + hacia_adentro[1] * alcance)]
    )
    cruces = [
        Point(c)
        for tramo in red.tramos()
        for c in _coordenadas(rayo.intersection(tramo.eje))
        if Point(c).distance(acceso) > TOLERANCIA
    ]
    if not cruces:
        return None
    destino = min(cruces, key=lambda c: (round(c.distance(acceso), 6), red.nodo(c)))
    return destino if _dentro(dominio, acceso, destino) else None


def _punto_mas_cercano(red: RedCirculacion, dominio: Polygon, acceso: Point) -> Point | None:
    tramos = red.tramos()
    if not tramos:
        return None
    destino = min(
        (Point(t.eje.interpolate(t.eje.project(acceso))) for t in tramos),
        key=lambda c: (round(c.distance(acceso), 6), red.nodo(c)),
    )
    return destino if _dentro(dominio, acceso, destino) else None


def _podar_tramos_sin_salida(
    red: RedCirculacion,
    dominio: Polygon,
    accesos: list[Point],
    jerarquia_de: Callable[[int], JerarquiaCorredor],
    borde=None,
) -> list[tuple[Clave, LineString]]:
    """Saca lo que no lleva a ningún lado, y devuelve los enlaces que agregó.

    - Los tramos que terminan en el interior sin seguir a ningún lado.
    - Los pedazos de calle sueltos, que no se conectan con ningún acceso, si no se los
      puede enlazar con una transversal (`_enlazar_sueltos`). Aparecen en las esquinas
      cuando la grilla va oblicua al terreno, o en un brazo de un terreno cóncavo que
      ninguna transversal cruza. Lo que queda sin frente es remanente (D41).

    Las calles que llegan al borde del terreno se conservan: dan frente a lotes y se
    asume que continúan en el entorno (Ord. 8060, art. 20). `borde` es ese límite (el contorno del
    dominio, salvo en un recálculo, donde es el del terreno). Un tramo fijado nunca se saca (D56).
    """
    borde = dominio.exterior if borde is None else borde
    _podar_colgantes(red, borde)
    enlaces = _enlazar_sueltos(red, dominio, accesos, jerarquia_de)
    _podar_colgantes(red, borde)
    for nodos in red.componentes():
        tramos = red.tramos_de(nodos)
        if not any(red.servido(acceso, tramos) for acceso in accesos):
            for tramo in tramos:
                if not tramo.fijado:
                    red.quitar_tramo(tramo)
    return enlaces


def _podar_colgantes(red: RedCirculacion, borde) -> None:
    while True:
        colgantes = [n for n in red.nodos() if red.grado(n) == 1 and borde.distance(Point(n)) > TOLERANCIA]
        # Primero se juntan: un tramo suelto con las dos puntas en el interior aparece dos
        # veces, y al quitarlo por una punta desaparece también la otra.
        por_quitar = {(t.origen, t.destino): t for nodo in colgantes for t in red.tramos_en(nodo) if not t.fijado}
        if not por_quitar:
            return
        for clave in sorted(por_quitar):
            red.quitar_tramo(por_quitar[clave])


def _enlazar_sueltos(
    red: RedCirculacion, dominio: Polygon, accesos: list[Point], jerarquia_de: Callable[[int], JerarquiaCorredor]
) -> list[tuple[Clave, LineString]]:
    """Une a la red los pedazos de calle sueltos con una transversal de enlace (D40).

    En un terreno cóncavo, las transversales repartidas sobre todo el ancho pueden no
    cruzar un brazo, y sus calles longitudinales quedan sueltas. Para cada pedazo suelto
    (sin ningún acceso), en orden estable, se traza una recta transversal por el medio de
    su extensión a lo largo de la grilla. Si dentro del terreno cruza el pedazo suelto y la
    parte de la red que llega a un acceso, se suma solo el tramo entre los dos cruces más
    cercanos: una transversal entera agregaría una calle paralela a otra, con manzanas
    angostas entre ambas. Si no, el pedazo se poda después, como antes. El enlace es local,
    salvo que se lo elija como avenida (D48).
    """
    intentados: set = set()
    enlaces: list[tuple[Clave, LineString]] = []
    minx, miny, maxx, maxy = dominio.bounds
    while True:
        componentes = red.componentes()
        servidos = [c for c in componentes if any(red.servido(a, red.tramos_de(c)) for a in accesos)]
        sueltos = [c for c in componentes if c not in servidos and c[0] not in intentados]
        if not servidos or not sueltos:
            return enlaces
        nodos = sueltos[0]
        intentados.add(nodos[0])
        tramos = red.tramos_de(nodos)
        jerarquia = jerarquia_de(len(enlaces) + 1)
        xs = [x for tramo in tramos for x, _ in (tramo.eje.coords[0], tramo.eje.coords[-1])]
        if max(xs) - min(xs) < jerarquia.ancho_total:
            continue  # una transversal suelta: otra paralela no la enlaza
        x = round((min(xs) + max(xs)) / 2, 3)
        recta = LineString([(x, miny - 1), (x, maxy + 1)])
        servidos_tramos = [tramo for c in servidos for tramo in red.tramos_de(c)]
        for pieza in lineas(interseccion(recta, dominio)):
            en_suelto, en_servido = _posiciones(pieza, tramos), _posiciones(pieza, servidos_tramos)
            if not (en_suelto and en_servido):
                continue
            a, b = min(
                ((s, v) for s in en_suelto for v in en_servido), key=lambda par: (round(abs(par[0] - par[1]), 3), par)
            )
            if abs(a - b) > TOLERANCIA:
                enlace = substring(pieza, min(a, b), max(a, b))
                _insertar(red, enlace, jerarquia)
                enlaces.append(((ENLACE, len(enlaces) + 1), enlace))
                break


def _insertar(red: RedCirculacion, pieza: LineString, jerarquia: JerarquiaCorredor) -> None:
    """Suma un eje a la red, partiendo los tramos que cruza (como `_armar_tramos`)."""
    cruces = [Point(c) for tramo in red.tramos() for c in _coordenadas(pieza.intersection(tramo.eje))]
    nodos = [red.partir_en(cruce) for cruce in sorted(cruces, key=lambda c: round(pieza.project(c), 3))]
    cortes = [Point(pieza.coords[0]), *(Point(n) for n in nodos), Point(pieza.coords[-1])]
    posiciones = sorted({round(pieza.project(c), 3): c for c in cortes}.items())
    for (_, a), (_, b) in zip(posiciones, posiciones[1:]):
        if a.distance(b) > TOLERANCIA:
            red.agregar_tramo(a, b, None, jerarquia)


def _coordenadas(geometria) -> list[tuple[float, float]]:
    if geometria.is_empty:
        return []
    if hasattr(geometria, "geoms"):
        return [c for parte in geometria.geoms for c in _coordenadas(parte)]
    return [tuple(c) for c in geometria.coords]


def _posiciones(linea: LineString, tramos) -> list[float]:
    """Dónde cruza `linea` a los ejes de los tramos, medido a lo largo de ella."""
    return sorted(
        round(linea.project(Point(c)), 3) for tramo in tramos for c in _coordenadas(linea.intersection(tramo.eje))
    )


def _dentro(dominio: Polygon, a: Point, b: Point) -> bool:
    return dominio.buffer(TOLERANCIA).covers(LineString([a, b]))


def _numero(valor: float) -> str:
    """Número con hasta dos decimales, coma decimal (RNF01): 20 → «20», 18,5 → «18,5»."""
    texto = f"{valor:.2f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")
