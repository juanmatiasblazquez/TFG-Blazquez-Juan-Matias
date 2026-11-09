"""Materializador de corredores: de los ejes de la red a la superficie de calle (p. 47; D24).

Cada tramo se ensancha con su ancho total (calzada + veredas). El resultado es una partición
sin solapes, alineada con `red.tramos()`: los cruces quedan en la calle de mayor jerarquía y
cada ochava se suma al tramo con el que comparte más borde (es vía pública, Ord. 8060, art. 55).

En un recálculo (D56) los tramos fijados ya tienen su corredor: se materializan solo los nuevos,
recortados al dominio restante, y las ochavas de las manzanas nuevas ven también las calles fijadas
(`contexto`), pero sus triángulos van solo a corredores nuevos.
"""

import math

import numpy as np
import shapely
from shapely import LineString, MultiLineString, MultiPolygon, Point, Polygon, STRtree
from shapely.geometry.base import BaseGeometry

from .geometria import (
    ANGULO_COLINEAL,
    DESVIO_ALINEACION,
    TOLERANCIA,
    Lado,
    ajustar,
    diferencia,
    interseccion,
    lados,
    poligonos,
    union,
    unitario,
)
from .red import RedCirculacion, Tramo


class MaterializadorCorredores:
    def materializar(
        self,
        red: RedCirculacion,
        jerarquias,
        dominio: Polygon,
        contexto: BaseGeometry | None = None,
        limite=None,
        reservadas=(),
        entrantes=(),
    ) -> list[BaseGeometry]:
        """Los corredores de `red.tramos()`, en ese orden.

        `limite` es por dónde va la calle de borde (`generador_red.limite_con_calle`): con áreas
        reservadas (D59) el dominio tiene agujeros o muescas, y la franja de la calle de un área llega
        exacta a su borde, como la del límite del terreno. Sin `limite`, el contorno del dominio. La
        calle de un lado de un área alineado con la grilla corre recta y el lado se puede apartar de
        ella hasta `DESVIO_ALINEACION`: la franja llega igual hasta el área, y esa diferencia es
        vereda (`reservadas`). Lo mismo la calle de un lado de una entrante del terreno, con la calle de
        borde por lado (`entrantes`, las líneas de `generador_red.lados_entrantes`; D86).

        Con `contexto` (la circulación fijada de un recálculo, D56), `dominio` es el dominio restante:
        los tramos fijados salen vacíos (su corredor es el de la versión de origen, que pone el
        motor) y los nuevos se recortan al dominio restante."""
        tramos = red.tramos()
        alineables = [p.exterior for area in reservadas for p in poligonos(area)] + list(entrantes)
        areas = MultiLineString(alineables) if alineables else None
        if contexto is None:
            franjas = [self._franja(tramo, dominio, red, limite, areas) for tramo in tramos]
            corredores = self._particionar(tramos, franjas)
            return self._aplicar_ochavas(corredores, tramos, red, dominio)
        nuevos = [i for i, tramo in enumerate(tramos) if not tramo.fijado]
        if not nuevos:
            return [Polygon()] * len(tramos)
        franjas = [self._franja(tramos[i], dominio, red, limite, areas) for i in nuevos]
        propios = self._particionar([tramos[i] for i in nuevos], franjas)
        propios = self._aplicar_ochavas(propios, [tramos[i] for i in nuevos], red, dominio, contexto)
        corredores: list[BaseGeometry] = [Polygon()] * len(tramos)
        for i, corredor in zip(nuevos, propios, strict=True):
            corredores[i] = corredor
        return corredores

    def _franja(self, tramo: Tramo, dominio: Polygon, red: RedCirculacion, limite=None, areas=None) -> BaseGeometry:
        """El eje ensanchado con extremos planos y recortado al dominio.

        Donde el eje toca el borde del terreno se lo alarga antes de ensancharlo: si la calle
        llega en diagonal al límite, así no queda una cuña de terreno entre ambos.

        Donde la calle dobla (un nodo con solo dos tramos que no son colineales, como en las
        esquinas de una calle de borde, D50), cada tramo se alarga hasta el pie de la
        perpendicular desde la esquina exterior de la curva: las dos franjas cierran la esquina,
        como una unión a inglete. Con extremos planos quedaría una cuña de terreno afuera de la
        curva (de 6 × 6 m en una esquina recta de una calle de 12 m).

        Una calle de borde (D50) corre a medio ancho del límite: su franja se pasa 1 m hacia afuera
        y se recorta con el terreno, así su borde exterior es exactamente el límite. Si no, en un
        lado oblicuo la grilla de 1 mm deja astillas de menos de un milímetro entre los dos.

        De lo recortado queda solo lo que toca al eje (D40): en un terreno cóncavo, la franja
        alargada puede cruzar una entrante y reaparecer del otro lado, y ese pedazo no es calle
        de este tramo. Así cada franja es una pieza con su eje adentro, y si el grafo es conexo
        la superficie de calle también lo es (D34).
        """
        a, b = np.asarray(tramo.eje.coords[0]), np.asarray(tramo.eje.coords[-1])
        a0, b0 = a, b
        ancho = tramo.jerarquia.ancho_total
        direccion = unitario(a, b)
        borde = dominio.exterior if limite is None else limite
        afuera = _hacia_el_limite(tramo, borde)
        holgura = 0.0
        if afuera is None and areas is not None:
            # La calle recta de un lado de un área (D59) o de una entrante (D86) alineado con la grilla.
            afuera = _hacia_el_limite(tramo, areas, DESVIO_ALINEACION)
            holgura = DESVIO_ALINEACION

        def contra_el_borde(punto) -> bool:
            # En un recálculo, también la punta que entra en lo fijado: un empalme o un anclaje (D56).
            fuera = limite is not None and not dominio.buffer(TOLERANCIA).covers(Point(punto))
            return fuera or borde.distance(Point(punto)) <= TOLERANCIA

        if contra_el_borde(a):
            a = a - direccion * 3 * ancho
        else:
            a = a - direccion * _alargue_en_curva(tramo, tramo.origen, red)
        if contra_el_borde(b):
            b = b + direccion * 3 * ancho
        else:
            b = b + direccion * _alargue_en_curva(tramo, tramo.destino, red)
        franja = LineString([a, b]).buffer(ancho / 2, cap_style="flat", join_style="mitre")
        if afuera is not None:
            lejos = ancho / 2 + 1.0 + holgura
            franja = union([franja, Polygon([a0, b0, b0 + afuera * lejos, a0 + afuera * lejos])])
        recortada = interseccion(franja, dominio)
        partes = poligonos(recortada)
        con_eje = [parte for parte in partes if parte.distance(tramo.eje) <= TOLERANCIA]
        if len(con_eje) == len(partes) and recortada.geom_type in ("Polygon", "MultiPolygon"):
            return recortada
        # Una esquina aguda puede dejar en la intersección líneas o puntos sobre el límite: no son
        # superficie de calle.
        return MultiPolygon(con_eje) if len(con_eje) > 1 else (con_eje[0] if con_eje else Polygon())

    def _particionar(self, tramos: list[Tramo], franjas: list[BaseGeometry]) -> list[BaseGeometry]:
        """Cada tramo se queda con su franja menos lo que ya tomaron los anteriores.

        El orden es por jerarquía (la mayor primero) y después por tramo, así un cruce entre
        una colectora y una local queda en la colectora.
        """
        orden = sorted(range(len(tramos)), key=lambda i: (tramos[i].jerarquia.orden, i))
        posicion = {i: p for p, i in enumerate(orden)}
        arbol = STRtree(franjas)
        corredores: list[BaseGeometry | None] = [None] * len(tramos)
        for i in orden:
            anteriores = sorted(
                int(j) for j in arbol.query(franjas[i]) if posicion[int(j)] < posicion[i]
            )
            if anteriores:
                corredores[i] = _superficie(diferencia(franjas[i], union(corredores[j] for j in anteriores)))
            else:
                corredores[i] = _superficie(ajustar(franjas[i]))
        return corredores

    def _aplicar_ochavas(
        self,
        corredores: list[BaseGeometry],
        tramos: list[Tramo],
        red: RedCirculacion,
        dominio: Polygon,
        contexto: BaseGeometry | None = None,
    ) -> list[BaseGeometry]:
        """Corta las esquinas de las manzanas que dan a dos calles.

        En cada esquina convexa cuyos dos lados tocan un corredor se corta un triángulo
        isósceles: su base es la línea de ochava, perpendicular a la bisectriz, de largo
        `radio_ochava` (el mayor entre las calles que se cruzan en el nodo más cercano). Los
        catetos no pasan de la mitad del lado más corto. Las esquinas contra el borde del
        terreno no llevan ochava.

        Con `contexto` (las calles fijadas de un recálculo, D56), una esquina entre una calle nueva y
        una fijada también lleva ochava, pero el triángulo va a un corredor nuevo que comparta un
        lado con él: lo fijado no cambia. Si ninguno lo comparte, la esquina queda sin ochava.
        """
        circulacion = union(corredores if contexto is None else [*corredores, contexto])
        triangulos = []
        for manzana in poligonos(diferencia(dominio, circulacion)):
            todos = lados(manzana, circulacion)
            for i, saliente in enumerate(todos):
                entrante = todos[i - 1]
                if entrante.toca and saliente.toca:
                    triangulo = self._ochava(entrante, saliente, red)
                    if triangulo is not None:
                        triangulos.append(triangulo)
        if not triangulos:
            return corredores
        arbol = STRtree(corredores)
        sumados: dict[int, list[Polygon]] = {}
        orden = sorted(range(len(tramos)), key=lambda i: (tramos[i].jerarquia.orden, i))
        posicion = {i: p for p, i in enumerate(orden)}
        for triangulo in triangulos:
            contorno = triangulo.boundary
            candidatos = [int(j) for j in arbol.query(triangulo.buffer(TOLERANCIA))]
            if not candidatos:
                continue
            def borde_compartido(j: int) -> tuple[float, int]:
                return (round(contorno.intersection(corredores[j].buffer(TOLERANCIA)).length, 3), -posicion[j])

            elegido = max(candidatos, key=borde_compartido)
            if contexto is not None and borde_compartido(elegido)[0] <= TOLERANCIA:
                continue
            sumados.setdefault(elegido, []).append(triangulo)
        return [
            _superficie(union([corredor, *sumados[j]])) if j in sumados else corredor
            for j, corredor in enumerate(corredores)
        ]

    def _ochava(self, entrante: Lado, saliente: Lado, red: RedCirculacion) -> Polygon | None:
        vertice = np.asarray(saliente.inicio)
        hacia_atras = unitario(vertice, entrante.inicio)
        hacia_adelante = unitario(vertice, saliente.fin)
        # El anillo va en sentido antihorario: la esquina es convexa si el giro es a la izquierda.
        giro = -hacia_atras[0] * hacia_adelante[1] + hacia_atras[1] * hacia_adelante[0]
        angulo = math.acos(float(np.clip(hacia_atras @ hacia_adelante, -1.0, 1.0)))
        if giro <= 0 or angulo >= math.pi - math.radians(ANGULO_COLINEAL):
            return None
        nodo = red.nodo_mas_cercano(Point(vertice))
        largo = max((t.jerarquia.radio_ochava for t in red.tramos_en(nodo)), default=0.0)
        if largo <= 0:
            return None
        cateto = min(largo / (2 * math.sin(angulo / 2)), entrante.largo / 2, saliente.largo / 2)
        return Polygon(
            [vertice + hacia_atras * cateto, vertice, vertice + hacia_adelante * cateto]
        )


def _alargue_en_curva(tramo: Tramo, nodo, red: RedCirculacion) -> float:
    """Cuánto se alarga `tramo` más allá de `nodo` para cerrar la curva de la calle (D50): hasta el
    pie de la perpendicular desde la esquina exterior, el cruce de los bordes exteriores de las dos
    franjas. 0 si en el nodo no hay una curva: un extremo, un cruce o una calle que sigue derecho."""
    if red.grado(nodo) != 2:
        return 0.0
    otro = next(t for t in red.tramos_en(nodo) if (t.origen, t.destino) != (tramo.origen, tramo.destino))
    lejos = tramo.destino if nodo == tramo.origen else tramo.origen
    sigue = otro.destino if nodo == otro.origen else otro.origen
    llega = unitario(lejos, nodo)  # el tramo, hacia el nodo
    sale = unitario(nodo, sigue)  # el otro, desde el nodo
    giro = llega[0] * sale[1] - llega[1] * sale[0]
    if abs(giro) < math.sin(math.radians(ANGULO_COLINEAL)) and float(llega @ sale) > 0:
        return 0.0
    # Afuera de la curva: a la derecha si dobla a la izquierda, y al revés.
    lado = -1.0 if giro > 0 else 1.0

    def normal(u):
        return np.array([-u[1], u[0]]) * lado

    centro = np.asarray(nodo)
    pa = centro + normal(llega) * tramo.jerarquia.ancho_total / 2
    pb = centro + normal(sale) * otro.jerarquia.ancho_total / 2
    det = llega[0] * sale[1] - llega[1] * sale[0]
    if abs(det) < 1e-12:
        return 0.0
    t = ((pb[0] - pa[0]) * sale[1] - (pb[1] - pa[1]) * sale[0]) / det
    esquina = pa + llega * t
    return max(0.0, float((esquina - centro) @ llega))


def _superficie(geometria: BaseGeometry) -> BaseGeometry:
    """Solo la parte de superficie de un overlay. Donde dos franjas se tocan en un ángulo agudo,
    la diferencia con la grilla de 1 mm puede dejar una línea o un punto sueltos junto al
    polígono: no son calle, y un overlay posterior con geometrías mixtas falla."""
    if geometria.is_empty or geometria.geom_type in ("Polygon", "MultiPolygon"):
        return geometria
    partes = [parte for parte in shapely.get_parts(geometria) if parte.geom_type == "Polygon" and not parte.is_empty]
    partes += [p for parte in shapely.get_parts(geometria) if parte.geom_type == "MultiPolygon" for p in parte.geoms]
    if not partes:
        return Polygon()
    return partes[0] if len(partes) == 1 else MultiPolygon(partes)


def _hacia_el_limite(tramo: Tramo, borde, holgura: float = 0.0) -> np.ndarray | None:
    """Si el tramo es de una calle de borde (D50): su eje corre a medio ancho del límite, en toda
    su extensión, o hasta `holgura` más lejos (la calle de un lado de un área alineado con la
    grilla, D59). Devuelve la normal hacia el límite, o `None`."""
    a, b = np.asarray(tramo.eje.coords[0]), np.asarray(tramo.eje.coords[-1])
    direccion = unitario(a, b)
    mitad = tramo.jerarquia.ancho_total / 2
    for normal in (np.array([-direccion[1], direccion[0]]), np.array([direccion[1], -direccion[0]])):
        puntos = [a + (b - a) * t + normal * mitad for t in (0.25, 0.5, 0.75)]
        if all(borde.distance(Point(p)) <= 2 * TOLERANCIA + holgura for p in puntos):
            return normal
    return None
