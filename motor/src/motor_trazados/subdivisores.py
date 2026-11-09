"""Subdivisores: de una manzana a sus celdas útiles (p. 47).

El mismo motor subdivide loteos y playas de estacionamiento con distinto subdivisor; por ahora
solo existe el de loteo (`MotorGeneracion` responde «no implementado» para playas).
"""

import math
from abc import ABC, abstractmethod

from shapely import LineString, MultiLineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry

from .contrato import CeldaGenerada, ParametrosLoteo, TipoCelda
from .verificador import frente_minimo_en_esquina
from .geometria import (
    TOLERANCIA,
    MarcoLocal,
    angulo,
    cadena_de_frente,
    interseccion,
    lados,
    paralelos,
    poligonos,
    superficie,
)

# Margen de las cajas de corte: alcanza con que exceda la manzana.
_MARGEN = 1.0


class Subdivisor(ABC):
    def identificar_frentes(self, manzana: Polygon, corredores: BaseGeometry) -> list[LineString]:
        """Lados rectos de la manzana que dan a un corredor (incluidas las líneas de ochava)."""
        return [lado.linea() for lado in lados(manzana, corredores) if lado.toca]

    @abstractmethod
    def subdividir(
        self, manzana: Polygon, frentes: list[LineString], parametros, indice_manzana: int
    ) -> list[CeldaGenerada]:
        """Piezas de la manzana, sin descartar ninguna fracción (CU06, 6.a). Salen todas como
        lotes candidatos: el motor decide después cuáles son remanentes (D41)."""

    def redividir(self, celda: Polygon, corredores: BaseGeometry, parametros) -> list[list[Polygon]]:
        """Formas de partir una celda que pasa un máximo, en orden de preferencia. El motor se
        queda con la primera cuyas partes cumplan todo (D47). Por defecto, ninguna."""
        return []


class SubdivisorLoteo(Subdivisor):
    """Divide la manzana en franjas por fondo y cada franja en lotes por frente (D24).

    Trabaja en el marco del frente principal (el más largo): ahí ese frente es horizontal y
    los cortes son paralelos a los ejes. Los cortes entre lotes son perpendiculares al frente
    (Ord. 8060, art. 53 c).

    En una manzana con frente de un solo lado (una manzana de borde), los lotes no pasan del
    fondo con el que cumplen la relación fondo/frente y la superficie máxima: lo que queda
    detrás es una pieza más, que el motor clasifica como remanente (D40).
    """

    def subdividir(
        self, manzana: Polygon, frentes: list[LineString], parametros: ParametrosLoteo, indice_manzana: int
    ) -> list[CeldaGenerada]:
        if not frentes:
            return [self._celda(manzana, manzana, indice_manzana, 1)]
        principal = max(frentes, key=lambda f: f.length)
        marco = MarcoLocal((0.0, 0.0), _angulo_normalizado(principal))
        local = marco.a_local(manzana)
        frentes_locales = [marco.a_local(f) for f in frentes]
        franjas = self._dividir_por_fondo(local, frentes_locales, parametros.frente_minimo)
        un_solo_lado = len(franjas) == 1
        lotes = []
        for franja, frentes_franja in franjas:
            lotes += self._cortar_por_frente(franja, frentes_franja, parametros, limitar_fondo=un_solo_lado)
        return [
            self._celda(marco.a_global(lote), lote, indice_manzana, numero)
            for numero, lote in enumerate(lotes, 1)
        ]

    def _dividir_por_fondo(
        self, manzana: Polygon, frentes: list[LineString], frente_minimo: float
    ) -> list[tuple[Polygon, list[LineString]]]:
        """Franjas de la manzana, cada una con los frentes sobre los que da.

        Con frentes abajo y arriba se corta por la mitad: dos franjas, una por frente. Con un
        solo frente horizontal, la manzana entera es una franja. Un lado horizontal más corto que
        el frente mínimo no cuenta: ahí no entra un lote, y en una esquina con ochavas desplazaría
        el corte (lo encontró la calle de borde de la sesión 8, D50).
        """
        horizontales = [
            f
            for f in frentes
            if paralelos(angulo(f.coords[0], f.coords[-1]), 0.0) and f.length + TOLERANCIA >= frente_minimo
        ]
        altura_media = manzana.centroid.y
        abajo = [f for f in horizontales if _y_media(f) < altura_media]
        arriba = [f for f in horizontales if _y_media(f) >= altura_media]
        if not (abajo and arriba):
            return [(manzana, frentes)]
        corte = (max(_y_media(f) for f in abajo) + min(_y_media(f) for f in arriba)) / 2
        minx, miny, maxx, maxy = manzana.bounds
        inferior = box(minx - _MARGEN, miny - _MARGEN, maxx + _MARGEN, corte)
        superior = box(minx - _MARGEN, corte, maxx + _MARGEN, maxy + _MARGEN)
        franjas = [(parte, frentes) for parte in poligonos(interseccion(manzana, inferior))]
        franjas += [(parte, frentes) for parte in poligonos(interseccion(manzana, superior))]
        return franjas

    def _cortar_por_frente(
        self, franja: Polygon, frentes: list[LineString], parametros: ParametrosLoteo, limitar_fondo: bool = False
    ) -> list[Polygon]:
        """Lotes de la franja, de izquierda a derecha.

        La extensión del frente es la de los lados de la franja que dan a la calle, ochavas
        incluidas. Se reparte en `k` lotes, con `k` lo más cerca posible del frente objetivo sin
        bajar del mínimo (`anchos_de_lotes`): iguales, salvo que una punta en esquina necesite el
        frente de esquina (Ord. 8060, art. 54; D49). Los lotes de las puntas se quedan con lo que la
        franja sobresale de esa extensión. Con `limitar_fondo`, lo que pasa del fondo útil queda
        aparte, al final de la lista.
        """
        sobre_frentes = [lado for lado in lados(franja, MultiLineString(frentes)) if lado.toca]
        en_calle = [punto for lado in sobre_frentes for punto in lado.puntos]
        if not en_calle:
            return [franja]
        a = min(p[0] for p in en_calle)
        b = max(p[0] for p in en_calle)
        largo = b - a
        anchos = anchos_de_lotes(largo, _esquinas(sobre_frentes, a, b), parametros)
        atras: list[Polygon] = []
        if limitar_fondo and largo > 0:
            franja, atras = self._limitar_fondo(franja, frentes, min(anchos), parametros)
        cortes, x = [], a
        for ancho in anchos[:-1]:
            x += ancho
            cortes.append(x)
        return self._cortar(franja, cortes) + atras

    def _cortar(self, franja: BaseGeometry, cortes: list[float]) -> list[Polygon]:
        """Las partes de la franja entre cortes verticales en `cortes` (en el marco del frente),
        de izquierda a derecha. Las de las puntas se quedan con lo que sobresale."""
        minx, miny, maxx, maxy = franja.bounds
        bordes = [minx - _MARGEN, *cortes, maxx + _MARGEN]
        partes = []
        for izquierda, derecha in zip(bordes, bordes[1:]):
            caja = box(izquierda, miny - _MARGEN, derecha, maxy + _MARGEN)
            partes += sorted(
                poligonos(interseccion(franja, caja)), key=lambda p: (round(p.bounds[0], 3), round(p.bounds[1], 3))
            )
        return partes

    def redividir(self, celda: Polygon, corredores: BaseGeometry, parametros: ParametrosLoteo) -> list[list[Polygon]]:
        """Formas de partir un lote grande en `k` lotes iguales a lo largo de uno de sus frentes
        (D47), en orden de preferencia: primero el menor `k`, y con el mismo `k`, el frente más
        largo. El motor se queda con la primera cuyas partes sean todas lotes sin pasar la
        superficie máxima.

        Cada frente es un lado sobre una calle de al menos el frente mínimo (así la línea de
        ochava no cuenta), y su extensión es la de su cadena de lados sobre calles, ochavas
        incluidas, como la mide el verificador. Los cortes son perpendiculares a ese frente
        (Ord. 8060, art. 53 c), igual que en la subdivisión de la manzana. Una forma que deja una
        parte en dos pedazos no sirve.
        """
        todos = lados(celda, corredores)
        frentes = []
        for i, lado in enumerate(todos):
            if lado.toca and lado.largo + TOLERANCIA >= parametros.frente_minimo:
                marco = MarcoLocal((0.0, 0.0), _angulo_normalizado(lado.linea()))
                xs = [marco.a_local(Point(p)).x for p in cadena_de_frente(todos, i)]
                frentes.append((round(max(xs) - min(xs), 6), i, marco, min(xs), max(xs)))
        frentes.sort(key=lambda f: (-f[0], f[1]))
        maximo = max((math.floor(f[0] / parametros.frente_minimo + 1e-9) for f in frentes), default=1)
        formas = []
        for k in range(2, maximo + 1):
            for extension, _, marco, a, b in frentes:
                if extension / k + TOLERANCIA < parametros.frente_minimo:
                    continue
                partes = self._cortar(marco.a_local(celda), [a + j * (b - a) / k for j in range(1, k)])
                if len(partes) == k:
                    formas.append([marco.a_global(parte) for parte in partes])
        return formas

    def _limitar_fondo(
        self, franja: Polygon, frentes: list[LineString], frente: float, p: ParametrosLoteo
    ) -> tuple[BaseGeometry, list[Polygon]]:
        """Separa lo que pasa del fondo útil de una franja con frente de un solo lado (D40).

        Con lotes de frente `frente`, el fondo útil es el mayor con el que cumplen la relación
        fondo/frente y la superficie máxima. Se mide desde el frente horizontal más profundo.
        Devuelve la parte que se lotea y lo que queda detrás.
        """
        fondo_util = min(p.relacion_fondo_frente_max * frente, p.superficie_maxima / frente)
        horizontales = [f for f in frentes if paralelos(angulo(f.coords[0], f.coords[-1]), 0.0)]
        if not horizontales or fondo_util < p.fondo_minimo:
            return franja, []
        minx, miny, maxx, maxy = franja.bounds
        abajo = [f for f in horizontales if _y_media(f) < franja.centroid.y]
        if abajo:
            linea = max(_y_media(f) for f in abajo) + fondo_util
            if maxy - linea <= TOLERANCIA:
                return franja, []
            cerca = box(minx - _MARGEN, miny - _MARGEN, maxx + _MARGEN, linea)
            lejos = box(minx - _MARGEN, linea, maxx + _MARGEN, maxy + _MARGEN)
        else:
            linea = min(_y_media(f) for f in horizontales) - fondo_util
            if linea - miny <= TOLERANCIA:
                return franja, []
            cerca = box(minx - _MARGEN, linea, maxx + _MARGEN, maxy + _MARGEN)
            lejos = box(minx - _MARGEN, miny - _MARGEN, maxx + _MARGEN, linea)
        # Solo la superficie: contra un borde oblicuo, el recorte puede dejar líneas sueltas (D56).
        return superficie(interseccion(franja, cerca)), poligonos(interseccion(franja, lejos))

    def _celda(self, geometria: Polygon, en_marco: Polygon, indice_manzana: int, numero: int) -> CeldaGenerada:
        # Medidas de diseño (extensión en el marco del frente). El motor las reemplaza por las
        # que mide el verificador sobre la geometría final.
        minx, miny, maxx, maxy = en_marco.bounds
        return CeldaGenerada(
            geometria=geometria,
            tipo=TipoCelda.LOTE,
            frente=maxx - minx,
            fondo=maxy - miny,
            indice_manzana=indice_manzana,
            designacion=f"M{indice_manzana}-L{numero:02d}",
        )


def anchos_de_lotes(largo: float, esquinas: tuple[bool, bool], p: ParametrosLoteo) -> list[float]:
    """Los frentes de los lotes de una franja de frente `largo`, de izquierda a derecha (D24, D49).

    `k` es lo más cerca posible del frente objetivo sin bajar del mínimo, y los lotes son iguales.
    Si una punta es de esquina (`esquinas` = izquierda, derecha) y el lote igual no llega al frente
    de esquina (`verificador.frente_minimo_en_esquina`), ese lote toma el frente de esquina y los
    del medio se reparten el resto. Si así un lote del medio baja del mínimo, va un lote menos.
    """
    minimo, en_esquina = p.frente_minimo, frente_minimo_en_esquina(p)
    maximo = max(1, math.floor(largo / minimo + 1e-9))
    cantidad = min(max(1, math.floor(largo / p.frente_objetivo + 0.5)), maximo)
    puntas = sum(esquinas)
    while cantidad > 1:
        igual = largo / cantidad
        if not puntas or igual + TOLERANCIA >= en_esquina:
            return [igual] * cantidad
        medio = cantidad - puntas
        if medio > 0:
            resto = (largo - puntas * en_esquina) / medio
            if resto + TOLERANCIA >= minimo:
                return [en_esquina] * esquinas[0] + [resto] * medio + [en_esquina] * esquinas[1]
        cantidad -= 1
    return [largo]


def _esquinas(sobre_frentes, a: float, b: float) -> tuple[bool, bool]:
    """Si cada punta de la franja (en el marco del frente, que es horizontal) da a otra calle: la
    punta tiene un lado sobre una calle que no es horizontal, la transversal o su ochava. Donde la
    calle llega al borde del terreno no hay esquina."""
    oblicuos = [lado for lado in sobre_frentes if not paralelos(lado.direccion, 0.0)]

    def en(x: float) -> bool:
        return any(abs(punto[0] - x) <= TOLERANCIA for lado in oblicuos for punto in lado.puntos)

    return en(a), en(b)


def _angulo_normalizado(linea: LineString) -> float:
    """Dirección de la línea en grados, llevada a (−90, 90]: el frente queda horizontal."""
    grados = math.degrees(angulo(linea.coords[0], linea.coords[-1]))
    while grados <= -90:
        grados += 180
    while grados > 90:
        grados -= 180
    return grados


def _y_media(linea: LineString) -> float:
    return (linea.coords[0][1] + linea.coords[-1][1]) / 2
