"""Contrato del motor: lo que recibe y lo que devuelve (diagrama de clases del motor, p. 47; D22).

Todo está en metros, en el sistema de cálculo del proyecto. Pasar de EPSG:4326 a metros y de
vuelta es tarea de `coordenadas`, que llama la API (D21): este contrato no sabe nada de
coordenadas geográficas.

Los tipos son dataclasses inmutables de la biblioteca estándar (pydantic está prohibido en el
motor, RNF07) y los parámetros van tipados, no como `dict`. Construir un tipo nunca falla:
`SolicitudGeneracion.validar()` devuelve los problemas por campo, así la API puede mostrarlos
(RNF01) y el motor los rechaza antes de generar.

Los nombres de los campos son los del ER y del diagrama del dominio (p. 46-47), sin el sufijo
de unidad de las columnas (`frente_minimo` ↔ `frente_minimo_m`), porque el tribunal contrasta
el código con el documento (D29).

Desvíos del diagrama, registrados en D22:
- `SolicitudGeneracion` lleva `terreno` y `reservadas` en lugar de `dominio`: el dominio lo
  arma el motor (`prepararDominio(terreno, reservadas)`), descontando las áreas reservadas (D59).
- `CeldaGenerada` lleva `designacion` (del ER), para que un incumplimiento nombre su celda.
- Los indicadores son un tipo (`Indicadores`), no un `dict`.
- Los espacios verdes y libres son celdas (`TipoCelda.ESPACIO_VERDE` y `ESPACIO_LIBRE`, D41):
  así forman parte de la partición. `ResultadoGeneracion.espacios_verdes`, que el diagrama deja
  en el asignador, se deriva de ellas.
- Las áreas reservadas no son celdas: son piezas aparte de la partición
  (`ResultadoGeneracion.reservadas`), sin manzana (D59).
"""

import itertools
import math
from dataclasses import dataclass, fields
from enum import StrEnum
from typing import TYPE_CHECKING

import shapely
from shapely import LineString, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

from .errores import Problema
from .geometria import TOLERANCIA, TOLERANCIA_AREA, poligonos, sin_astillas
from .semillas import validar_semilla

if TYPE_CHECKING:
    from .red import RedCirculacion


class TipoProyecto(StrEnum):
    LOTEO = "loteo"
    ESTACIONAMIENTO = "estacionamiento"


class PatronRed(StrEnum):
    GRILLA = "grilla"


class TipoCelda(StrEnum):
    """Qué es cada pieza de una manzana. Los remanentes son las fracciones donde no entra un
    lote válido: espacio verde si tiene la superficie, el ancho y el acceso de un verde, o
    espacio libre (D41)."""

    LOTE = "lote"
    PLAZA = "plaza"
    ESPACIO_VERDE = "espacio_verde"
    ESPACIO_LIBRE = "espacio_libre"


class CriterioEspacioVerde(StrEnum):
    """Qué prioriza el asignador de espacios verdes al elegir dónde completar la cesión (D46, D51).

    Es un criterio de diseño, no una norma: la Ley 4146, art. 7, pide espacios verdes de
    ubicación adecuada, no central.
    - `CERCANIA` (el de referencia desde el motor 0.7.0): la pieza que deja los lotes más cerca
      del verde, por la red, sin otra prioridad.
    - `MENOS_LOTES`: la pieza que cuesta menos lotes, con los lotes grandes primero.
    """

    MENOS_LOTES = "menos_lotes"
    CERCANIA = "cercania"


class CalleBorde(StrEnum):
    """Por dónde va la calle de borde del terreno (D50, D86). Es un criterio de diseño: lo que pide la
    norma es el lado menor de la manzana (Ord. 8060, art. 48), no una calle perimetral.
    - `CONTORNO`: una calle recorre todo el límite del terreno (D50).
    - `POR_LADO`: solo los lados donde sin ella una fila quedaría con frente de un solo lado (los
      paralelos a las filas) y los lados con un acceso. En los demás, las filas y las cuadras terminan
      contra el límite (`generador_red.limite_con_calle`).
    """

    CONTORNO = "contorno"
    POR_LADO = "por_lado"


class SentidoCirculacion(StrEnum):
    UNICO = "unico"
    DOBLE = "doble"


class TipoIncumplimiento(StrEnum):
    """Las restricciones que verifica el motor. Desde el 0.6.0 no está `superficie_maxima`: un
    lote grande no es un incumplimiento (D47). Las versiones anteriores lo guardaron así en la
    base, y el portal todavía sabe nombrarlo."""

    CONECTIVIDAD = "conectividad"
    SIN_FRENTE = "sin_frente"
    FRENTE_MINIMO = "frente_minimo"
    FONDO_MINIMO = "fondo_minimo"
    SUPERFICIE_MINIMA = "superficie_minima"
    RELACION_FONDO_FRENTE = "relacion_fondo_frente"
    ANCHO_UTIL = "ancho_util"
    CESION_ESPACIO_VERDE = "cesion_espacio_verde"
    # Ley 4146, art. 12 (D48): el ancho de las calles y la proporción de avenidas.
    ANCHO_CALLE = "ancho_calle"
    PROPORCION_AVENIDAS = "proporcion_avenidas"
    # Ord. 8060, art. 48 (D50): los lados de las manzanas con lotes.
    LADO_MENOR_MANZANA = "lado_menor_manzana"
    LADO_MAYOR_MANZANA = "lado_mayor_manzana"


# --- Entrada ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class JerarquiaCorredor:
    """Una jerarquía de calle. `orden` 1 es la mayor.

    `radio_ochava` es el LARGO de la línea de ochava: el corte recto de la esquina,
    perpendicular a la bisectriz (D24), no el radio de un arco. El nombre es el del ER
    (`radio_ochava_m`), que manda sobre el código; la diferencia está anotada para corregir
    el documento (D29).
    """

    nombre: str
    orden: int
    ancho_calzada: float
    ancho_vereda: float
    radio_ochava: float

    @property
    def ancho_total(self) -> float:
        return self.ancho_calzada + 2 * self.ancho_vereda


def jerarquia_mayor(jerarquias) -> JerarquiaCorredor:
    """La de menor `orden`: la de las avenidas (D48)."""
    return min(jerarquias, key=lambda j: j.orden)


def jerarquia_menor(jerarquias) -> JerarquiaCorredor:
    """La de mayor `orden`: todas las calles nacen de esta (D48)."""
    return max(jerarquias, key=lambda j: j.orden)


def exige_avenidas(porcentaje_minimo_avenidas) -> bool:
    """Si el loteo pide avenidas (Ley 4146, art. 12; D48). Con 0 %, todas las calles son de la jerarquía
    menor (la casilla «Exigir avenidas», D85). Un valor que no es un número cuenta como que sí: lo que está
    mal lo dice la validación."""
    return not (_finito(porcentaje_minimo_avenidas) and porcentaje_minimo_avenidas <= 0)


def jerarquias_en_uso(jerarquias, porcentaje_minimo_avenidas) -> tuple[bool, ...]:
    """Qué jerarquías puede usar el generador de la red, alineadas con la lista (D85): la menor, que es
    la de todas las calles, y la mayor si se exigen avenidas (D48). Una intermedia no se usa nunca (C6)."""
    if not jerarquias:
        return ()
    # Las mismas que elige el generador (`GeneradorRed.generar_con_avenidas`), comparadas por identidad.
    usadas = [jerarquia_menor(jerarquias)]
    if exige_avenidas(porcentaje_minimo_avenidas):
        usadas.append(jerarquia_mayor(jerarquias))
    return tuple(any(j is u for u in usadas) for j in jerarquias)


@dataclass(frozen=True, slots=True)
class Estrategia:
    """Cómo se genera una alternativa (p. 46).

    `orientacion`: ángulo de las calles longitudinales, en grados y en sentido antihorario,
    medido desde el eje x (este de cuadrícula) del sistema de cálculo. No es un acimut
    geográfico: difiere del norte verdadero en la convergencia de meridianos (D24).
    """

    patron_red: PatronRed
    orientacion: float
    semilla: int


@dataclass(frozen=True, slots=True)
class ParametrosLoteo:
    """Parámetros de un loteo (p. 46 y p. 49). Longitudes en m, superficies en m², % de 0 a 100.

    Son valores configurables, no reglas rígidas. Los de referencia, con su fuente normativa,
    están en `valores_referencia`. Sin columna en el ER (D29):
    - `superficie_minima_verde` y `ancho_minimo_verde` dicen cuándo un remanente es espacio
      verde (D41);
    - `ancho_minimo_lote` es el ancho útil de un lote, medido como el del verde (el diámetro del
      mayor círculo inscripto); con la relación fondo/frente máxima forma el criterio de forma
      que decide si una pieza es un lote (D43);
    - `factor_union_maximo` es el tope de la unión de una fracción con su lote vecino: el lote
      que resulta no puede pasar ese factor por el lote típico de su manzana (D43);
    - `porcentaje_minimo_avenidas`, `ancho_minimo_avenida`, `ancho_minimo_calle` y
      `ancho_minimo_calzada` son los de la Ley 4146, art. 12 (D48): calles de 12 m con 6 m de
      calzada, y no menos del 20 % de la longitud de calles como avenidas de 20 m;
    - `porcentaje_incremento_esquina` es lo que crece el frente mínimo de un lote en esquina
      (Ord. 8060, art. 54; D49);
    - `criterio_espacio_verde` es lo que prioriza el asignador (D46, D51);
    - `lado_minimo_manzana`, `lado_maximo_manzana` y `lado_maximo_sin_pasaje` son los de la Ord.
      8060, art. 48 (D50): el lado menor de una manzana con lotes mide al menos 42 m, y el mayor a
      lo sumo 250 m, con un pasaje peatonal desde los 200 m. El motor no traza pasajes;
    - `calle_borde` es por dónde va la calle de borde: todo el contorno o por lado (D50, D86).

    `superficie_maxima` no es una restricción desde el motor 0.6.0: decide la unión, la zona y la
    subdivisión, y un lote que la pasa es un lote grande (D47).
    """

    frente_minimo: float
    frente_objetivo: float
    fondo_minimo: float
    superficie_minima: float
    superficie_maxima: float
    relacion_fondo_frente_max: float
    longitud_maxima_manzana: float
    porcentaje_espacio_verde: float
    porcentaje_equipamiento: float
    superficie_minima_verde: float
    ancho_minimo_verde: float
    ancho_minimo_lote: float
    factor_union_maximo: float
    porcentaje_minimo_avenidas: float
    ancho_minimo_avenida: float
    ancho_minimo_calle: float
    ancho_minimo_calzada: float
    porcentaje_incremento_esquina: float
    criterio_espacio_verde: CriterioEspacioVerde
    lado_minimo_manzana: float
    lado_maximo_manzana: float
    lado_maximo_sin_pasaje: float
    calle_borde: CalleBorde


@dataclass(frozen=True, slots=True)
class ParametrosEstacionamiento:
    """Parámetros de una playa de estacionamiento (p. 46). Todavía no se generan playas."""

    ancho_plaza: float
    largo_plaza: float
    angulo: float
    sentido_circulacion: SentidoCirculacion
    porcentaje_plazas_accesibles: float


@dataclass(frozen=True, slots=True)
class SolicitudGeneracion:
    """Todo lo que el motor necesita para generar una alternativa, en metros.

    `reservadas` son las áreas reservadas del terreno (CU04, paso 5): el motor las descuenta del
    dominio antes de generar (CU06, paso 4) y les pone una calle alrededor (D59). Se designan R1,
    R2… por su posición, como los accesos."""

    tipo: TipoProyecto
    terreno: Polygon
    accesos: tuple[Point, ...]
    parametros: ParametrosLoteo | ParametrosEstacionamiento
    jerarquias: tuple[JerarquiaCorredor, ...]
    estrategia: Estrategia
    reservadas: tuple[Polygon, ...] = ()

    def __post_init__(self):
        # Se aceptan listas por comodidad del llamador; adentro todo es inmutable.
        for nombre in ("accesos", "jerarquias", "reservadas"):
            object.__setattr__(self, nombre, tuple(getattr(self, nombre)))

    def validar(self) -> list[Problema]:
        """Problemas de la solicitud, por campo. Vacía si se puede generar.

        Es la copia única de estas reglas: la API las reusa al configurar parámetros (CU05).
        """
        problemas = []
        problemas += validar_terreno(self.terreno)
        problemas += validar_accesos(self.accesos, self.terreno)
        problemas += validar_reservadas(self.reservadas, self.terreno, self.accesos)
        problemas += _validar_jerarquias(self.jerarquias)
        problemas += _validar_estrategia(self.estrategia)
        esperado = {
            TipoProyecto.LOTEO: ParametrosLoteo,
            TipoProyecto.ESTACIONAMIENTO: ParametrosEstacionamiento,
        }.get(self.tipo)
        if esperado is None:
            problemas.append(Problema("tipo", f"Tipo de proyecto desconocido: {self.tipo!r}."))
        elif not isinstance(self.parametros, esperado):
            problemas.append(
                Problema("parametros", f"Un proyecto de tipo {self.tipo} lleva {esperado.__name__}.")
            )
        elif isinstance(self.parametros, ParametrosLoteo):
            problemas += _validar_parametros_loteo(self.parametros, self.jerarquias)
        else:
            problemas += _validar_parametros_estacionamiento(self.parametros)
        return problemas


@dataclass(frozen=True, slots=True)
class TramoFijado:
    """Un tramo que se conserva al recalcular: su eje, su jerarquía y su superficie de calle (el
    corredor de la versión de origen, vacío si caía entero dentro de un cruce)."""

    eje: LineString
    jerarquia: JerarquiaCorredor
    corredor: BaseGeometry


@dataclass(frozen=True, slots=True)
class ManzanaFijada:
    """Una manzana que se conserva al recalcular, con su designación de origen («M6»)."""

    designacion: str
    geometria: Polygon


@dataclass(frozen=True, slots=True)
class ElementosFijados:
    """Lo que se conserva de una versión al recalcular (CU09, p. 47; D56). Lo arma
    `MotorGeneracion.fijar`, que es la regla de qué se fija: las manzanas elegidas, enteras, con sus
    celdas y las calles que las rodean.

    - `sector`: la unión de las manzanas y los corredores fijados; el dominio restante es el
      terreno menos el sector.
    - `anclajes`: los nodos de la red fijada donde, en la versión de origen, una calle fijada seguía
      hacia lo que se recalcula.

    Desvíos del diagrama de la p. 47 (D29): `tramos` lleva además la jerarquía y el corredor de cada
    tramo (el diagrama dice `list[LineString]`), y se suman las manzanas, con su designación, y la
    orientación del marco de la alternativa: toda versión de una alternativa se cierra en el marco
    local de su v1, así lo fijado vuelve exacto a la grilla de 1 mm.
    """

    sector: MultiPolygon
    celdas: tuple["CeldaGenerada", ...]
    tramos: tuple[TramoFijado, ...]
    anclajes: tuple[Point, ...]
    manzanas: tuple[ManzanaFijada, ...] = ()
    orientacion_marco: float = 0.0

    def __post_init__(self):
        for nombre in ("celdas", "tramos", "anclajes", "manzanas"):
            object.__setattr__(self, nombre, tuple(getattr(self, nombre)))


# --- Salida ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CeldaGenerada:
    """Una pieza de una manzana: un lote (o una plaza) o un remanente, espacio verde o libre.

    `frente` y `fondo` son los que mide el verificador (`geometria.medir`, D26).
    `indice_manzana` empieza en 1, igual que la designación: «M3-L07» para un lote, «M3-EV01»
    para un espacio verde y «M3-EL01» para un espacio libre.
    """

    geometria: Polygon
    tipo: TipoCelda
    frente: float
    fondo: float
    indice_manzana: int
    designacion: str


@dataclass(frozen=True, slots=True)
class Incumplimiento:
    """Una restricción que no se cumple. `elemento` es la designación de lo que incumple
    («M3-L07», «A2», «red» o «terreno») y `detalle` lleva los valores, en español."""

    tipo: TipoIncumplimiento
    elemento: str
    detalle: str
    geometria: BaseGeometry


@dataclass(frozen=True, slots=True)
class Indicadores:
    """Indicadores de una alternativa (CU08). Superficies en m², longitudes en m, % de 0 a 100.

    Una celda útil es un lote sin incumplimientos (D26): `cantidad_celdas` cuenta solo las
    útiles (RF11) y `superficie_aprovechable` suma su superficie. Los porcentajes son sobre la
    superficie disponible (el terreno menos las áreas reservadas, D61), salvo `porcentaje_cesion`: el verde sobre la superficie de todos
    los lotes, la base de la cesión (Ley 4146, art. 7); `None` si no hay lotes. Los nombres son
    los del ER (`version_alternativa`, D29); los tres de los remanentes no tienen columna en el
    ER (D41), y tampoco `cantidad_lotes_grandes`: los lotes que pasan la superficie máxima, que
    son útiles (D47), ni `porcentaje_avenidas`: la longitud de las avenidas sobre la de toda la
    red, la base del art. 12 de la Ley 4146 (D48), ni las dos distancias al verde: la media y la
    máxima, sobre todos los lotes, de la distancia por la red de cada lote al espacio verde más
    cercano (`remanentes.distancias_al_verde`, D51); `None` sin lotes o sin verde.

    El verde se informa dos veces (D55): `superficie_espacio_verde` y `porcentaje_espacio_verde`
    son todo el verde, y `superficie_verde_computable` el que cuenta para la cesión: con «más
    cercanía», sin las puntas que no alcanzan el lado menor del art. 48
    (`verificador.computa_para_cesion`, D58). `porcentaje_cesion` es el computable sobre los lotes.

    `superficie_reservada` suma las áreas reservadas (D59): no son lotes ni verde y no cuentan para
    la cesión. `superficie_disponible` es el terreno menos las áreas, el dominio que se lotea, y es
    la base del aprovechamiento, la circulación y el verde (D61): lotes, circulación, verde y libre
    suman la disponible. Sin áreas es el terreno, bit a bit.
    """

    cantidad_celdas: int
    cantidad_fracciones_no_conformes: int
    superficie_terreno: float
    superficie_aprovechable: float
    porcentaje_aprovechamiento: float
    porcentaje_circulacion: float
    porcentaje_espacio_verde: float
    longitud_red: float
    distancia_media_acceso: float | None
    superficie_espacio_verde: float
    superficie_espacio_libre: float
    porcentaje_cesion: float | None
    cantidad_lotes_grandes: int
    porcentaje_avenidas: float
    distancia_media_verde: float | None
    distancia_maxima_verde: float | None
    superficie_verde_computable: float
    superficie_disponible: float
    superficie_reservada: float = 0.0


@dataclass(frozen=True, slots=True, eq=False)
class ResultadoGeneracion:
    """Una alternativa generada, en metros.

    `corredores[i]` es la superficie de calle del tramo `red.tramos()[i]`: una partición sin
    solapes de la circulación, donde los cruces quedan en la calle de mayor jerarquía. Puede
    quedar vacía si el tramo cae entero dentro de un cruce.

    Corredores, celdas y áreas reservadas son una partición cerrada del terreno (D39): no se
    superponen, no dejan huecos y cada manzana es la unión de sus celdas. `reservadas[k]` es la pieza
    del área `k` de la solicitud (R{k + 1}): la misma forma, con los puntos que el cierre le sumó
    sobre sus lados donde la tocan las calles (D59).

    `indice_manzana` de cada celda es la posición de su manzana en `manzanas` (desde 1), y
    `designaciones` el nombre de cada manzana. Al generar es «M1» … «Mn» (vacío lo dice); en un
    recálculo (D56) las manzanas fijadas conservan el suyo y las nuevas toman los números libres,
    así que puede haber saltos. Los tramos fijados de un recálculo llevan `Tramo.fijado`.
    """

    red: "RedCirculacion"
    corredores: tuple[BaseGeometry, ...]
    manzanas: tuple[Polygon, ...]
    celdas: tuple[CeldaGenerada, ...]
    incumplimientos: tuple[Incumplimiento, ...] = ()
    indicadores: Indicadores | None = None
    designaciones: tuple[str, ...] = ()
    reservadas: tuple[Polygon, ...] = ()

    def designacion_manzana(self, indice: int) -> str:
        """El nombre de la manzana `indice` (desde 1): «M3»."""
        return self.designaciones[indice - 1] if self.designaciones else f"M{indice}"

    @property
    def lotes(self) -> tuple[CeldaGenerada, ...]:
        return tuple(celda for celda in self.celdas if celda.tipo is TipoCelda.LOTE)

    @property
    def espacios_verdes(self) -> tuple[Polygon, ...]:
        return tuple(c.geometria for c in self.celdas if c.tipo is TipoCelda.ESPACIO_VERDE)

    @property
    def espacios_libres(self) -> tuple[Polygon, ...]:
        return tuple(c.geometria for c in self.celdas if c.tipo is TipoCelda.ESPACIO_LIBRE)

    def cumple(self) -> bool:
        return not self.incumplimientos

    def celdas_no_conformes(self) -> tuple[CeldaGenerada, ...]:
        marcadas = {incumplimiento.elemento for incumplimiento in self.incumplimientos}
        return tuple(celda for celda in self.celdas if celda.designacion in marcadas)


# --- Validaciones ----------------------------------------------------------------------------


def validar_terreno(terreno) -> list[Problema]:
    """Problemas del polígono del terreno, en metros. Públicas, como `validar_accesos`, porque
    la API las usa al registrar el terreno (CU04, 3.a y 6.a): son la misma regla que aplica
    `SolicitudGeneracion.validar`, no una copia."""
    if not isinstance(terreno, Polygon) or terreno.is_empty:
        return [Problema("terreno", "El terreno tiene que ser un polígono.")]
    if not terreno.is_valid:
        return [Problema("terreno", "El polígono del terreno no es válido (¿se cruza a sí mismo?).")]
    if terreno.interiors:
        return [
            Problema("terreno", "El terreno no puede tener huecos: las áreas interiores van como reservadas.")
        ]
    return []


def validar_reservadas(reservadas, terreno, accesos=()) -> list[Problema]:
    """Problemas de las áreas reservadas, en metros (CU04, pasos 5 y 6, curso 6.a; D59). Pública,
    como `validar_terreno`: la API la usa al registrar el terreno y al cambiar las áreas, y es la
    misma regla que aplica `SolicitudGeneracion.validar`.

    - Cada área es un polígono válido y sin huecos (lo de adentro quedaría sin acceso).
    - Está dentro del terreno (6.a): puede tocar su borde, no salir de él.
    - Dos áreas pueden tocarse, pero no superponerse.
    - No cubren todo el terreno: queda dominio donde lotear.
    - Ningún acceso cae sobre un tramo del borde que tomó un área: por ahí no se entra al loteo.
    - Toda parte del terreno que dejan las áreas tiene algún acceso: si no, la red no llegaría.
    """
    if not reservadas:
        return []
    problemas = []
    validas: list[tuple[int, Polygon]] = []
    for k, area in enumerate(reservadas):
        campo, nombre = f"reservadas[{k}]", f"R{k + 1}"
        if not isinstance(area, Polygon) or area.is_empty:
            problemas.append(Problema(campo, f"El área {nombre} tiene que ser un polígono."))
        elif not area.is_valid:
            problemas.append(Problema(campo, f"El polígono del área {nombre} no es válido (¿se cruza a sí mismo?)."))
        elif area.interiors:
            problemas.append(
                Problema(campo, f"El área {nombre} no puede tener huecos: lo de adentro quedaría sin acceso.")
            )
        else:
            validas.append((k, area))
    if not isinstance(terreno, Polygon) or terreno.is_empty or not terreno.is_valid:
        return problemas
    contenedor = terreno.buffer(TOLERANCIA)
    for k, area in validas:
        if not contenedor.covers(area):
            afuera = area.difference(terreno).area
            problemas.append(
                Problema(
                    f"reservadas[{k}]",
                    f"El área R{k + 1} sale del terreno ({_m2(afuera)} afuera): tiene que quedar dentro del "
                    "polígono.",
                )
            )
    for (i, a), (j, b) in itertools.combinations(validas, 2):
        solape = a.intersection(b).area
        if solape > TOLERANCIA_AREA:
            problemas.append(
                Problema(
                    f"reservadas[{j}]",
                    f"Las áreas R{i + 1} y R{j + 1} se superponen en {_m2(solape)}: pueden tocarse, pero no "
                    "superponerse.",
                )
            )
    if problemas:
        return problemas
    partes = poligonos(sin_astillas(terreno.difference(shapely.union_all([a for _, a in validas]))))
    if not partes:
        return [Problema("reservadas", "Las áreas reservadas cubren todo el terreno: no queda dónde lotear.")]
    puntos = [(k, a) for k, a in enumerate(accesos) if isinstance(a, Point) and not a.is_empty]
    for k, acceso in puntos:
        tomada = next((j for j, area in validas if area.distance(acceso) <= TOLERANCIA), None)
        if tomada is not None:
            problemas.append(
                Problema(
                    f"accesos[{k}]",
                    f"El acceso A{k + 1} está sobre el borde del área R{tomada + 1}: por ahí no se entra al "
                    "loteo. Ubicalo en un tramo del borde que no tome un área.",
                )
            )
    if problemas or not puntos:
        return problemas
    sin_acceso = [parte for parte in partes if not any(parte.distance(a) <= TOLERANCIA for _, a in puntos)]
    if sin_acceso:
        superficie_sin = math.fsum(parte.area for parte in sin_acceso)
        problemas.append(
            Problema(
                "reservadas",
                f"Las áreas reservadas dejan {len(sin_acceso)} parte(s) del terreno ({_m2(superficie_sin)}) sin "
                "ningún acceso: lo que se genere ahí no llegaría a la red.",
            )
        )
    return problemas


def _m2(valor: float) -> str:
    """Una superficie en español: «0,35 m²», «5.459 m²» (RNF01)."""
    if valor < 10:
        return f"{valor:.2f}".replace(".", ",") + " m²"
    return f"{valor:,.0f}".replace(",", ".") + " m²"


def validar_accesos(accesos, terreno) -> list[Problema]:
    """Problemas de los puntos de acceso (en metros): tienen que estar sobre el perímetro."""
    if not accesos:
        return [Problema("accesos", "Hace falta al menos un punto de acceso.")]
    problemas = []
    for k, acceso in enumerate(accesos):
        campo = f"accesos[{k}]"
        if not isinstance(acceso, Point) or acceso.is_empty:
            problemas.append(Problema(campo, f"El acceso A{k + 1} tiene que ser un punto."))
        elif isinstance(terreno, Polygon) and not terreno.is_empty:
            distancia = terreno.exterior.distance(acceso)
            if distancia > TOLERANCIA:
                problemas.append(
                    Problema(
                        campo,
                        f"El acceso A{k + 1} está a {distancia:.2f} m del perímetro; "
                        "tiene que estar sobre él.",
                    )
                )
    return problemas


def _validar_jerarquias(jerarquias) -> list[Problema]:
    if not jerarquias:
        return [Problema("jerarquias", "Hace falta al menos una jerarquía de calle.")]
    problemas = []
    for k, jerarquia in enumerate(jerarquias):
        campo = f"jerarquias[{k}]"
        if not _positivo(jerarquia.ancho_calzada):
            problemas.append(Problema(f"{campo}.ancho_calzada", "Tiene que ser mayor que 0."))
        if not _finito(jerarquia.ancho_vereda) or jerarquia.ancho_vereda < 0:
            problemas.append(Problema(f"{campo}.ancho_vereda", "No puede ser negativo."))
        if not _finito(jerarquia.radio_ochava) or jerarquia.radio_ochava < 0:
            problemas.append(Problema(f"{campo}.radio_ochava", "No puede ser negativo."))
    ordenes = [jerarquia.orden for jerarquia in jerarquias]
    if len(set(ordenes)) != len(ordenes):
        problemas.append(Problema("jerarquias", "Dos jerarquías no pueden tener el mismo orden."))
    return problemas


def _validar_estrategia(estrategia: Estrategia) -> list[Problema]:
    problemas = []
    if estrategia.patron_red not in PatronRed:
        problemas.append(Problema("estrategia.patron_red", f"Patrón desconocido: {estrategia.patron_red!r}."))
    if not _finito(estrategia.orientacion):
        problemas.append(Problema("estrategia.orientacion", "Tiene que ser un número."))
    try:
        validar_semilla(estrategia.semilla)
    except (TypeError, ValueError) as error:
        problemas.append(Problema("estrategia.semilla", str(error)))
    return problemas


def coherencia_de_loteo(
    parametros: ParametrosLoteo, jerarquias=()
) -> tuple[list[Problema], list["ReglaCoherencia"]]:
    """Los parámetros de un loteo y sus jerarquías, sin terreno ni estrategia: los problemas por campo
    (los mismos que da `SolicitudGeneracion.validar()`) y las reglas de coherencia, cumplidas o no, para
    mostrarlas en vivo (p. 49; D78). Si un valor no es un número válido, todavía no hay reglas."""
    campos = _campos_de_loteo(parametros)
    reglas = [] if campos else reglas_de_coherencia(parametros, jerarquias)
    problemas = _validar_jerarquias(jerarquias) + campos + [pr for regla in reglas for pr in regla.problemas]
    return problemas, reglas


def _validar_parametros_loteo(p: ParametrosLoteo, jerarquias=()) -> list[Problema]:
    problemas = _campos_de_loteo(p)
    if problemas:
        return problemas
    # La coherencia entre los valores (p. 49): sus reglas, con su nombre, son las que muestra el portal.
    return [problema for regla in reglas_de_coherencia(p, jerarquias) for problema in regla.problemas]


def _campos_de_loteo(p: ParametrosLoteo) -> list[Problema]:
    """Cada valor por separado: un número, positivo o un porcentaje, y los dos que son una opción (el
    criterio del verde y la calle de borde)."""
    problemas = []
    opciones_de = {"criterio_espacio_verde": CriterioEspacioVerde, "calle_borde": CalleBorde}
    for campo in fields(p):
        valor = getattr(p, campo.name)
        if campo.name in opciones_de:
            if valor not in opciones_de[campo.name]:
                opciones = " o ".join(f"«{c}»" for c in opciones_de[campo.name])
                problemas.append(Problema(f"parametros.{campo.name}", f"Tiene que ser {opciones}."))
        elif campo.name.startswith("porcentaje_"):
            if not _finito(valor) or not 0 <= valor <= 100:
                problemas.append(Problema(f"parametros.{campo.name}", "Tiene que estar entre 0 y 100."))
        elif not _positivo(valor):
            problemas.append(Problema(f"parametros.{campo.name}", "Tiene que ser mayor que 0."))
    return problemas


@dataclass(frozen=True, slots=True)
class ReglaCoherencia:
    """Una regla de coherencia de los parámetros de un loteo (p. 49, «Validación de coherencia»; D78).

    `descripcion` es la regla («Superficie mínima ≤ superficie máxima») y `detalle`, sus valores
    («250,00 m² ≤ 600,00 m²»). Si no se cumple, `problemas` dice qué campo corregir: son los mismos que
    da `SolicitudGeneracion.validar()`, que las usa (copia única)."""

    clave: str
    descripcion: str
    cumple: bool
    detalle: str
    problemas: tuple[Problema, ...] = ()


def _numero(valor: float) -> str:
    """«10,00», «1.234,50»: como el portal (RNF01)."""
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _regla(clave: str, descripcion: str, cumple: bool, detalle: str, *problemas: Problema) -> ReglaCoherencia:
    return ReglaCoherencia(clave, descripcion, cumple, detalle, () if cumple else tuple(problemas))


def reglas_de_coherencia(p: ParametrosLoteo, jerarquias=()) -> list[ReglaCoherencia]:
    """Las reglas de coherencia de un loteo, cumplidas o no, en el orden de la p. 49 y después las del
    motor. Supone valores numéricos válidos (`_validar_parametros_loteo` lo controla antes).

    - Las cuatro de la p. 49. La cuarta, «frente mín. × fondo mín. compatible con la superficie», no
      estaba definida (D36): un lote con el frente y el fondo mínimos no puede pasar la superficie
      máxima, porque entonces ningún lote cumpliría a la vez los dos mínimos y la máxima. Es la única
      lectura que marca una contradicción (D78).
    - La calzada de cada jerarquía alcanza la mínima de la Ley 4146, art. 12 (D78). El verificador
      sigue controlando el resultado (D48); esto la rechaza antes de generar.
    - Sin avenidas (0 %, D85), ni el ancho de avenida ni la jerarquía mayor se usan: sus reglas no van.
    """
    m2 = lambda valor: f"{_numero(valor)} m²"  # noqa: E731
    m = lambda valor: f"{_numero(valor)} m"  # noqa: E731
    lote_minimo = p.frente_minimo * p.fondo_minimo
    cesiones = p.porcentaje_espacio_verde + p.porcentaje_equipamiento
    con_avenidas = exige_avenidas(p.porcentaje_minimo_avenidas)
    reglas = [
        _regla(
            "superficie",
            "Superficie mínima ≤ superficie máxima",
            p.superficie_minima <= p.superficie_maxima,
            f"{m2(p.superficie_minima)} ≤ {m2(p.superficie_maxima)}",
            Problema("parametros.superficie_minima", "No puede ser mayor que la superficie máxima."),
        ),
        _regla(
            "frente_objetivo",
            "Frente objetivo ≥ frente mínimo",
            p.frente_objetivo >= p.frente_minimo,
            f"{m(p.frente_objetivo)} ≥ {m(p.frente_minimo)}",
            Problema("parametros.frente_objetivo", "No puede ser menor que el frente mínimo."),
        ),
        _regla(
            "cesiones",
            "Cesiones dentro del límite",
            cesiones <= 100,
            f"Espacio verde y equipamiento: {_numero(cesiones)} %",
            Problema("parametros.porcentaje_espacio_verde", "Las cesiones suman más del 100 %."),
        ),
        _regla(
            "lote_minimo",
            "Frente y fondo mínimos compatibles con la superficie",
            lote_minimo <= p.superficie_maxima + TOLERANCIA_AREA,
            f"{m(p.frente_minimo)} × {m(p.fondo_minimo)} = {m2(lote_minimo)} ≤ {m2(p.superficie_maxima)}",
            Problema(
                "parametros.fondo_minimo",
                f"Con el frente mínimo, un lote de fondo mínimo mide {m2(lote_minimo)}: más que la superficie "
                "máxima. Ningún lote podría cumplir a la vez los dos mínimos y la máxima.",
            ),
        ),
        # Criterio de forma (D43): un ancho útil mayor que el frente mínimo pasaría a ser el frente
        # mínimo real, y con un factor menor que 1 ninguna fracción se podría unir a un lote.
        _regla(
            "ancho_util",
            "Ancho útil ≤ frente mínimo",
            p.ancho_minimo_lote <= p.frente_minimo,
            f"{m(p.ancho_minimo_lote)} ≤ {m(p.frente_minimo)}",
            Problema("parametros.ancho_minimo_lote", "No puede ser mayor que el frente mínimo."),
        ),
        _regla(
            "tope_union",
            "Tope de unión de al menos 1",
            p.factor_union_maximo >= 1,
            f"{_numero(p.factor_union_maximo)} × el lote típico",
            Problema(
                "parametros.factor_union_maximo",
                "Tiene que ser al menos 1: con menos, ninguna fracción se puede unir a su lote vecino.",
            ),
        ),
        # Ley 4146, art. 12 (D48): la calzada es parte de la calle, y una avenida es una calle.
        _regla(
            "calzada_calle",
            "Calzada mínima ≤ ancho mínimo de calle",
            p.ancho_minimo_calzada <= p.ancho_minimo_calle,
            f"{m(p.ancho_minimo_calzada)} ≤ {m(p.ancho_minimo_calle)}",
            Problema("parametros.ancho_minimo_calzada", "No puede ser mayor que el ancho mínimo de la calle."),
        ),
        *(
            [
                _regla(
                    "avenida_calle",
                    "Ancho de avenida ≥ ancho de calle",
                    p.ancho_minimo_avenida >= p.ancho_minimo_calle,
                    f"{m(p.ancho_minimo_avenida)} ≥ {m(p.ancho_minimo_calle)}",
                    Problema(
                        "parametros.ancho_minimo_avenida", "No puede ser menor que el ancho mínimo de la calle."
                    ),
                )
            ]
            if con_avenidas
            else []
        ),
        # Ord. 8060, art. 48 (D50): la grilla corta las manzanas en la longitud máxima, que tiene que
        # admitir el lado menor y no pedir un pasaje peatonal, porque el motor no los traza.
        _regla(
            "lado_menor",
            "Lado menor ≤ longitud máxima de manzana",
            p.lado_minimo_manzana <= p.longitud_maxima_manzana,
            f"{m(p.lado_minimo_manzana)} ≤ {m(p.longitud_maxima_manzana)}",
            Problema("parametros.lado_minimo_manzana", "No puede ser mayor que la longitud máxima de manzana."),
        ),
        _regla(
            "sin_pasaje",
            "Longitud máxima de manzana sin pasaje peatonal",
            p.longitud_maxima_manzana <= p.lado_maximo_sin_pasaje,
            f"{m(p.longitud_maxima_manzana)} ≤ {m(p.lado_maximo_sin_pasaje)}",
            Problema(
                "parametros.longitud_maxima_manzana",
                f"No puede pasar de {p.lado_maximo_sin_pasaje:g} m: una manzana más larga necesita un pasaje "
                "peatonal (Ord. 8060, art. 48), y el motor no los traza.",
            ),
        ),
        _regla(
            "lado_mayor",
            "Lado mayor sin pasaje ≤ lado mayor de manzana",
            p.lado_maximo_sin_pasaje <= p.lado_maximo_manzana,
            f"{m(p.lado_maximo_sin_pasaje)} ≤ {m(p.lado_maximo_manzana)}",
            Problema("parametros.lado_maximo_sin_pasaje", "No puede ser mayor que el lado máximo de manzana."),
        ),
    ]
    # La calzada de cada jerarquía que se usa (Ley 4146, art. 12; D78, D85), si las calzadas son números
    # válidos (lo que no, lo dice `_validar_jerarquias`).
    en_uso = jerarquias_en_uso(jerarquias, p.porcentaje_minimo_avenidas)
    medibles = [(k, j) for k, j in enumerate(jerarquias) if en_uso[k] and _positivo(j.ancho_calzada)]
    if medibles and len(medibles) == sum(en_uso):
        angostas = [(k, j) for k, j in medibles if j.ancho_calzada + TOLERANCIA < p.ancho_minimo_calzada]
        reglas.append(
            _regla(
                "calzada_jerarquias",
                "La calzada de cada jerarquía alcanza la mínima",
                not angostas,
                "; ".join(f"{j.nombre}: {m(j.ancho_calzada)}" for _, j in medibles)
                + f" (mínima {m(p.ancho_minimo_calzada)})",
                *(
                    Problema(
                        f"jerarquias[{k}].ancho_calzada",
                        f"Mide menos que la calzada mínima de {m(p.ancho_minimo_calzada)} (Ley 4146, art. 12).",
                    )
                    for k, j in angostas
                ),
            )
        )
    return reglas


def _validar_parametros_estacionamiento(p: ParametrosEstacionamiento) -> list[Problema]:
    problemas = []
    for nombre in ("ancho_plaza", "largo_plaza"):
        if not _positivo(getattr(p, nombre)):
            problemas.append(Problema(f"parametros.{nombre}", "Tiene que ser mayor que 0."))
    if not _finito(p.angulo) or not 0 < p.angulo <= 90:
        problemas.append(Problema("parametros.angulo", "Tiene que estar entre 0 y 90 grados."))
    if p.sentido_circulacion not in SentidoCirculacion:
        problemas.append(Problema("parametros.sentido_circulacion", "Tiene que ser «unico» o «doble»."))
    if not _finito(p.porcentaje_plazas_accesibles) or not 0 <= p.porcentaje_plazas_accesibles <= 100:
        problemas.append(
            Problema("parametros.porcentaje_plazas_accesibles", "Tiene que estar entre 0 y 100.")
        )
    return problemas


def _finito(valor) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)


def _positivo(valor) -> bool:
    return _finito(valor) and valor > 0
