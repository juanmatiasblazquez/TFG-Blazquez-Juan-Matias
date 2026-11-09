"""La red de circulación como grafo: intersecciones como nodos y tramos como aristas (CU07).

Envuelve un `networkx.Graph`. Los nodos son coordenadas redondeadas al milímetro
(`geometria.clave_punto`), así dos tramos que llegan al mismo punto comparten el nodo aunque
sus coordenadas difieran en el último bit. Todo lo que devuelve sale en orden estable (RNF05):
nada itera un `set` sin ordenarlo.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import networkx as nx
import numpy as np
from shapely import LineString, Point

from .contrato import JerarquiaCorredor
from .geometria import TOLERANCIA, Coordenada, IndiceEjes, clave_punto

Nodo = Coordenada


@dataclass(frozen=True)
class Tramo:
    """Arista de la red. `eje` va de `origen` a `destino` y `origen < destino`.

    `fijado` marca un tramo que se conserva de la versión de origen en un recálculo (CU09, D56):
    la poda no lo toca, y si una calle nueva desemboca en él, se parte en dos tramos fijados."""

    origen: Nodo
    destino: Nodo
    eje: LineString
    jerarquia: JerarquiaCorredor
    fijado: bool = False

    @property
    def longitud(self) -> float:
        return self.eje.length


class RedCirculacion:
    def __init__(self):
        self._grafo = nx.Graph()

    @staticmethod
    def nodo(punto) -> Nodo:
        if isinstance(punto, Point):
            return clave_punto(punto.x, punto.y)
        return clave_punto(*punto)

    # --- Construcción ------------------------------------------------------------------------

    def agregar_tramo(
        self, origen, destino, eje: LineString | None, jerarquia: JerarquiaCorredor, fijado: bool = False
    ) -> Tramo | None:
        """Agrega el tramo origen–destino. Sin `eje`, el eje es el segmento recto entre ambos."""
        u, v = sorted((self.nodo(origen), self.nodo(destino)))
        if u == v:
            return None
        if eje is None:
            eje = LineString([u, v])
        elif self.nodo(eje.coords[0]) != u:
            eje = eje.reverse()
        tramo = Tramo(u, v, eje, jerarquia, fijado)
        self._grafo.add_edge(u, v, tramo=tramo)
        return tramo

    def quitar_tramo(self, tramo: Tramo) -> None:
        self._grafo.remove_edge(tramo.origen, tramo.destino)
        for nodo in (tramo.origen, tramo.destino):
            if self._grafo.degree(nodo) == 0:
                self._grafo.remove_node(nodo)

    def partir_en(self, punto: Point) -> Nodo:
        """Nodo de la red en `punto`: si cae dentro de un tramo, lo parte en dos."""
        nodo = self.nodo(punto)
        if nodo in self._grafo:
            return nodo
        tramos = self.tramos()
        indice = IndiceEjes([t.eje for t in tramos]).mas_cercano(punto)
        tramo = tramos[indice]
        if tramo.eje.distance(punto) > TOLERANCIA:
            raise ValueError(f"El punto {nodo} no está sobre la red.")
        for extremo in (tramo.origen, tramo.destino):
            if math.dist(extremo, nodo) <= TOLERANCIA:
                return extremo
        self.quitar_tramo(tramo)
        # Un tramo fijado que se parte (un empalme, D56) da dos tramos fijados sobre el mismo eje.
        self.agregar_tramo(tramo.origen, nodo, None, tramo.jerarquia, tramo.fijado)
        self.agregar_tramo(nodo, tramo.destino, None, tramo.jerarquia, tramo.fijado)
        return nodo

    def transformada(self, funcion: Callable) -> "RedCirculacion":
        """Copia de la red con `funcion` aplicada a cada eje (por ejemplo, volver del marco local)."""
        copia = RedCirculacion()
        for tramo in self.tramos():
            eje = funcion(tramo.eje)
            copia.agregar_tramo(eje.coords[0], eje.coords[-1], eje, tramo.jerarquia, tramo.fijado)
        return copia

    # --- Consultas ---------------------------------------------------------------------------

    def contiene(self, nodo: Nodo) -> bool:
        return nodo in self._grafo

    def tiene_tramo(self, origen, destino) -> bool:
        return self._grafo.has_edge(self.nodo(origen), self.nodo(destino))

    def nodos(self) -> list[Nodo]:
        return sorted(self._grafo.nodes)

    def tramos(self) -> list[Tramo]:
        return sorted(
            (datos["tramo"] for _, _, datos in self._grafo.edges(data=True)),
            key=lambda t: (t.origen, t.destino),
        )

    def tramos_en(self, nodo: Nodo) -> list[Tramo]:
        return sorted(
            (self._grafo.edges[nodo, vecino]["tramo"] for vecino in self._grafo.neighbors(nodo)),
            key=lambda t: (t.origen, t.destino),
        )

    def grado(self, nodo: Nodo) -> int:
        return self._grafo.degree(nodo)

    def nodo_mas_cercano(self, punto: Point) -> Nodo | None:
        nodos = self.nodos()
        if not nodos:
            return None
        return min(nodos, key=lambda n: (round(math.dist(n, (punto.x, punto.y)), 6), n))

    def servido(self, acceso: Point, tramos: Sequence[Tramo] | None = None) -> bool:
        """El acceso abre a una calle: está dentro del ancho de algún tramo (la boca de la calle)."""
        return any(_sirve(tramo, acceso) for tramo in (self.tramos() if tramos is None else tramos))

    def nodo_de_acceso(self, acceso: Point) -> Nodo | None:
        """Nodo por el que el acceso entra a la red (NodoRed coincide con 0..1 PuntoAcceso, p. 46).

        Entre los tramos que sirven al acceso (mismo criterio que `servido`), el extremo más
        cercano: el propio acceso si se unió con un conector, o la boca de la calle si abre
        directo a ella. `None` si ningún tramo lo sirve.
        """
        candidatos = {
            nodo for tramo in self.tramos() if _sirve(tramo, acceso) for nodo in (tramo.origen, tramo.destino)
        }
        if not candidatos:
            return None
        return min(sorted(candidatos), key=lambda n: (round(math.dist(n, (acceso.x, acceso.y)), 6), n))

    def es_conexa(self, accesos: Sequence[Point]) -> bool:
        """La red es una sola componente y todos los accesos abren a una de sus calles (p. 10)."""
        if self._grafo.number_of_nodes() == 0:
            return False
        return nx.is_connected(self._grafo) and all(self.servido(a) for a in accesos)

    def componentes(self) -> list[list[Nodo]]:
        """Componentes conexas, la principal (la de mayor longitud) primero, en orden estable."""
        componentes = [sorted(c) for c in nx.connected_components(self._grafo)]
        componentes.sort(key=lambda c: (-round(self._longitud_de(c), 6), c[0]))
        return componentes

    def componentes_aisladas(self) -> list[list[Nodo]]:
        """Componentes que quedan fuera de la principal."""
        return self.componentes()[1:]

    def tramos_de(self, nodos: Sequence[Nodo]) -> list[Tramo]:
        incluidos = set(nodos)
        return [t for t in self.tramos() if t.origen in incluidos and t.destino in incluidos]

    def longitud_total(self) -> float:
        return math.fsum(t.longitud for t in self.tramos())

    def distancias_desde(self, accesos: Sequence[Point]) -> dict[Nodo, float]:
        """Distancia por la red desde el acceso más cercano hasta cada nodo alcanzable."""
        nodos = self.nodos()
        distancias = self.matriz_distancias(accesos, [Point(n) for n in nodos]).min(axis=0, initial=math.inf)
        return {nodo: float(d) for nodo, d in zip(nodos, distancias, strict=True) if math.isfinite(d)}

    def distancias_por_red(self, origenes: Sequence[Point], destinos: Sequence[Point]) -> list[float | None]:
        """Para cada destino, la distancia por caminos mínimos desde el origen más cercano.

        Orígenes y destinos se anclan en su proyección sobre el eje más cercano; el tramo
        perpendicular desde el punto hasta el eje no se suma (D26). `None` si no hay camino.
        """
        distancias = self.matriz_distancias(origenes, destinos).min(axis=0, initial=math.inf)
        return [float(d) if math.isfinite(d) else None for d in distancias]

    def matriz_distancias(self, origenes: Sequence[Point], destinos: Sequence[Point]) -> np.ndarray:
        """Distancia por la red de cada origen (filas) a cada destino (columnas); `inf` si no hay
        camino. Es la copia única de cómo se mide una distancia por la red (D26, D44).

        Cada punto se ancla en su proyección sobre el eje más cercano, sin sumar el tramo
        perpendicular. Entre dos anclas, el camino sale por uno de los extremos de su tramo,
        sigue el camino mínimo entre nodos y entra por uno de los extremos del otro; si están
        sobre el mismo tramo, también puede ir derecho. Los caminos entre nodos salen de un
        Dijkstra desde cada nodo, así una consulta con muchos puntos cuesta casi lo mismo que
        una con pocos: es lo que necesita el asignador de espacios verdes.
        """
        tramos = self.tramos()
        if not tramos or not origenes or not destinos:
            return np.full((len(origenes), len(destinos)), math.inf)
        nodos = self.nodos()
        posicion = {nodo: k for k, nodo in enumerate(nodos)}
        grafo = nx.Graph()
        for tramo in tramos:
            grafo.add_edge(tramo.origen, tramo.destino, longitud=tramo.longitud)
        entre_nodos = np.full((len(nodos), len(nodos)), math.inf)
        for fuente, alcanzados in nx.all_pairs_dijkstra_path_length(grafo, weight="longitud"):
            for nodo, distancia in alcanzados.items():
                entre_nodos[posicion[fuente], posicion[nodo]] = distancia

        indice = IndiceEjes([t.eje for t in tramos])

        def anclas(puntos):
            cual, s, u, v, largo = [], [], [], [], []
            for punto in puntos:
                i = indice.mas_cercano(punto)
                tramo = tramos[i]
                cual.append(i)
                s.append(tramo.eje.project(punto))
                u.append(posicion[tramo.origen])
                v.append(posicion[tramo.destino])
                largo.append(tramo.longitud)
            return (np.asarray(cual), np.asarray(s), np.asarray(u), np.asarray(v), np.asarray(largo))

        tramo_o, s_o, u_o, v_o, largo_o = anclas(origenes)
        tramo_d, s_d, u_d, v_d, largo_d = anclas(destinos)
        # Lo que se recorre dentro del tramo de cada ancla hasta cada uno de sus extremos.
        hasta_u_o, hasta_v_o = s_o[:, None], (largo_o - s_o)[:, None]
        desde_u_d, desde_v_d = s_d[None, :], (largo_d - s_d)[None, :]
        caminos = np.stack(
            [
                hasta_u_o + entre_nodos[np.ix_(u_o, u_d)] + desde_u_d,
                hasta_u_o + entre_nodos[np.ix_(u_o, v_d)] + desde_v_d,
                hasta_v_o + entre_nodos[np.ix_(v_o, u_d)] + desde_u_d,
                hasta_v_o + entre_nodos[np.ix_(v_o, v_d)] + desde_v_d,
                np.where(tramo_o[:, None] == tramo_d[None, :], np.abs(s_o[:, None] - s_d[None, :]), math.inf),
            ]
        )
        return caminos.min(axis=0)

    def _longitud_de(self, nodos: Sequence[Nodo]) -> float:
        return math.fsum(t.longitud for t in self.tramos_de(nodos))


def _sirve(tramo: Tramo, acceso: Point) -> bool:
    """El acceso cae dentro del ancho de la calle del tramo (la boca de la calle)."""
    return tramo.eje.distance(acceso) <= tramo.jerarquia.ancho_total / 2 + TOLERANCIA
