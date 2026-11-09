"""Asignador de espacios verdes (p. 47; D44): completa la cesión del verde convirtiendo parcelas.

La cesión pide verde por al menos el 10 % de la superficie de todos los lotes (Ley 4146, art. 7;
`verificador.faltante_cesion`). Cuenta solo el verde computable: las puntas que no alcanzan el lado
menor del art. 48 son verde, y computan solo con «menos lotes» (`verificador.computa_para_cesion`,
D55, D58); para la distancia de los lotes al verde siempre cuentan. El verde de los remanentes
(D41) casi nunca alcanza: el asignador convierte en verde parcelas enteras de la partición ya
cerrada, con el menor exceso posible. Nunca corta un lote: une celdas vecinas de una misma manzana
con `union_cobertura`, así la partición sigue cerrada (D39) y cada pieza nueva es una celda
«espacio_verde».

**La circularidad del 10 %.** Convertir lotes en verde achica la base. Con verde `V`, lotes `L`
y porcentaje `p`, convertir lotes por `a_L` y libres por `a_E` deja `V + a_L + a_E` de verde
sobre `L − a_L` de lotes, y la condición `V' ≥ p·L'` es `a_L·(1 + p) + a_E ≥ p·L − V`. Por eso
cada parcela se mide por su **aporte** (un lote, su superficie × (1 + p); un libre, su
superficie) y se cubre «lo que falta» en esa unidad, sin iterar. Cada paso se comprueba con la
regla del verificador sobre los totales que quedarían.

**El criterio** (`ParametrosLoteo.criterio_espacio_verde`, D46, D51) es un criterio de diseño, no
una norma: la Ley 4146, art. 7, pide una ubicación adecuada, no central. No hay plaza central
obligatoria.

**«Más cercanía»** (el de referencia desde el motor 0.7.0, D51): en cada paso compiten juntas todas
las candidatas, sin prioridades, y gana la que deja menor distancia media de los lotes al verde
más cercano, por la red (`remanentes.distancias_al_verde`, la medida del indicador); desempatan la
distancia máxima, los lotes, la superficie de lotes, el exceso y la clave. Las candidatas son los
lotes grandes que solos son un verde válido, cada verde agrandado con parcelas de su manzana, y
cada manzana desde una punta o entera. Si la elegida no cubre lo que falta, se aplica y se vuelve
a elegir.

**«Menos lotes perdidos»**, con los pasos del autor (D44, D46):
0. Primero se convierten los **lotes grandes** (los que pasan la superficie máxima y no se
   pudieron subdividir, D47) que solos son un verde válido. Si alguno cubre lo que falta, se
   elige según el criterio; si no, se convierte el que más aporta y se repite. Un lote grande
   vecino de un verde de su manzana lo agranda.
1. Después se agrandan los verdes que ya existen: dentro de su manzana suman parcelas vecinas de
   a una, primero la que comparte más borde. Si alguno, agrandado lo mínimo, cubre lo que falta,
   se elige según el criterio; si ninguno alcanza, el que más aporta llena su manzana y se
   repite.
2. Por último se convierten manzanas: enteras, o desde una punta (las parcelas en el orden en
   que se recorre su frente principal, hasta cubrir lo que falta). Se usan las menos piezas
   posibles (`k*`: pocas piezas grandes antes que muchas chicas).

   En cada paso, la candidata que convierte menos lotes; desempatan la superficie de lotes, la
   distancia media, el exceso y la clave estable.

**Los dos planes.** Se arman los dos y queda el que mejor cumple el pedido del criterio: menos
lotes convertidos, o menor distancia media. Es una heurística: ninguno asegura el óptimo.

Al final se podan las conversiones que dejaron de hacer falta (una anterior puede sobrar después
de una pieza grande): cada pieza es necesaria.

Toda pieza verde cumple `remanentes.es_espacio_verde` (superficie, ancho y frente a una calle).
Si no se puede llegar, no se convierte nada y el asignador devuelve la causa y la sugerencia,
que el verificador suma al incumplimiento.

Desvío del diagrama (D22, D29): la p. 47 dice `asignar(manzanas, porcentaje, superficieTerreno)`
y la secuencia de la p. 43 lo pone antes de subdividir. Acá corre después de clasificar los
remanentes, porque la base de la cesión (los lotes) y los remanentes recién existen ahí.
"""

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np
from shapely import Polygon, STRtree
from shapely.geometry.base import BaseGeometry

from .contrato import CeldaGenerada, CriterioEspacioVerde, ParametrosLoteo, TipoCelda
from .geometria import TOLERANCIA, IndiceEjes, lados, unitario, union_cobertura
from .red import RedCirculacion
from .remanentes import es_espacio_verde, medida_de, numerar, punto_de_frente, puntos_de_acceso
from .verificador import computables, es_lote_grande, exigido_cesion, faltante_cesion


@dataclass(frozen=True)
class PiezaVerde:
    """Una pieza que armó el asignador: las designaciones de entrada de sus parcelas, en el orden
    en que se sumaron. `base` es el verde que se agrandó, o `None` si la pieza es nueva."""

    indice_manzana: int
    parcelas: tuple[str, ...]
    base: str | None


@dataclass(frozen=True)
class Asignacion:
    """Las celdas después de asignar, las piezas convertidas (en orden) y, si no se pudo llegar a
    la cesión, su causa y su sugerencia."""

    celdas: tuple[CeldaGenerada, ...]
    piezas: tuple[PiezaVerde, ...]
    motivo: tuple[str, str] | None


@dataclass(frozen=True)
class Candidata:
    """Una conversión posible: las parcelas que se suman, en orden, y si con ellas se cubre lo que
    falta. `lotes` es cuántos lotes convierte. `clave` es el desempate estable (RNF05)."""

    manzana: int
    parcelas: tuple[int, ...]
    base: int | None
    aporte: float
    superficie_lotes: float
    cubre: bool
    clave: tuple
    lotes: int = 0


def elegir(
    candidatas: Sequence[Candidata],
    criterio: CriterioEspacioVerde,
    distancia,
    exceso,
    rendimiento: bool = False,
    maxima=None,
) -> Candidata:
    """La candidata que prefiere el criterio (D46, D51). `distancia`, `exceso` y `maxima` son
    funciones de la candidata.

    - Menos lotes perdidos: la que convierte menos lotes; desempatan la menor superficie de lotes
      convertida, la menor distancia media, el menor exceso y la clave estable. Con `rendimiento`
      (una manzana entera que no cubre sola lo que falta), primero la que convierte menos lotes
      por m² de aporte: la que menos lotes cuesta no es la mejor si deja casi todo por cubrir.
    - Más cercanía: la que deja menor distancia media de los lotes al verde más cercano, sin otra
      prioridad; desempatan la menor distancia máxima, los lotes convertidos, la superficie de
      lotes, el menor exceso y la clave.
    """
    if criterio is CriterioEspacioVerde.MENOS_LOTES:

        def clave(c):
            por_aporte = round(c.lotes / c.aporte, 9) if c.aporte > 0 else math.inf
            return (
                por_aporte if rendimiento else 0,
                c.lotes,
                round(c.superficie_lotes, 2),
                round(distancia(c), 3),
                round(exceso(c), 2),
                c.clave,
            )

    else:

        def clave(c):
            return (
                round(distancia(c), 3),
                round(maxima(c), 3) if maxima else 0,
                c.lotes,
                round(c.superficie_lotes, 2),
                round(exceso(c), 2),
                c.clave,
            )

    return min(candidatas, key=clave)


def piezas_minimas(aportes: Sequence[float], faltante: float) -> int | None:
    """`k*`: la menor cantidad de piezas con la que se cubre lo que falta, sumando los aportes de
    mayor a menor. `None` si ni con todas alcanza."""
    acumulado = 0.0
    for k, aporte in enumerate(sorted(aportes, reverse=True), 1):
        acumulado += aporte
        if acumulado + TOLERANCIA >= faltante:
            return k
    return None


class AsignadorEspaciosVerdes:
    def asignar(
        self,
        celdas: Sequence[CeldaGenerada],
        manzanas: Sequence[Polygon],
        circulacion: BaseGeometry,
        red: RedCirculacion,
        ejes: IndiceEjes,
        p: ParametrosLoteo,
        convertibles: frozenset[int] | None = None,
        nombres: Sequence[str] = (),
    ) -> Asignacion:
        """Convierte parcelas en verde hasta cubrir la cesión, o no convierte nada y devuelve por
        qué. `manzanas[k]` es la manzana `k + 1`; `circulacion`, la unión de los corredores.

        `convertibles` son las manzanas donde se puede convertir (todas, si es `None`). En un
        recálculo (CU09, D56) son las nuevas: lo fijado cuenta para la cesión (sus lotes en la
        base, su verde computable) y para las distancias, pero no se toca. `nombres` son los de
        las manzanas, para designar las celdas (`remanentes.numerar`).

        Se arman los planes de los dos criterios y queda el que mejor cumple el pedido (D46, D51):
        con «menos lotes perdidos», el que convierte menos lotes; con «más cercanía», el que deja
        menor distancia media al verde. Con un empate, el del propio criterio. Así, por
        construcción, «menos lotes» nunca pierde más lotes que «cercanía», y «cercanía» nunca deja
        los lotes más lejos que «menos lotes». Es una heurística: los pasos son voraces y ninguno
        de los dos asegura el óptimo (el barrido de la sesión 7 encontró, en la U a 90°, un plan de
        «menos lotes» que perdía 26 lotes contra 19 de «cercanía»).
        """
        plan = _Plan(list(celdas), manzanas, circulacion, red, ejes, p, convertibles)
        if not plan.faltante():
            return Asignacion(tuple(celdas), (), None)
        motivo = plan.resolver()
        otro_criterio = (
            CriterioEspacioVerde.CERCANIA
            if p.criterio_espacio_verde is CriterioEspacioVerde.MENOS_LOTES
            else CriterioEspacioVerde.MENOS_LOTES
        )
        # El plan del otro criterio elige como ese criterio, pero la cesión se cuenta con la regla de
        # esta corrida: qué verde computa depende del criterio pedido (D58).
        otro = _Plan(list(celdas), manzanas, circulacion, red, ejes, p, convertibles, criterio=otro_criterio)
        if otro.resolver() is None and (motivo is not None or otro.mejor_que(plan)):
            plan, motivo = otro, None
        if motivo is not None:
            return Asignacion(tuple(celdas), (), motivo)
        return Asignacion(plan.celdas_resultantes(nombres), plan.piezas_resultantes(), None)


class _Plan:
    """El estado de una asignación: qué parcela es verde y de qué pieza, el verde y los lotes que
    quedarían, y la distancia de cada lote al verde más cercano."""

    def __init__(self, celdas, manzanas, circulacion, red, ejes, p, convertibles=None, criterio=None):
        """`p` es el de la corrida: define la cesión y qué verde computa (D58). `criterio` es la
        preferencia con la que elige este plan; si falta, la de `p`."""
        self.celdas = celdas
        self.manzanas = manzanas
        self.circulacion = circulacion
        self.ejes = ejes
        self.p = p
        self.factor = 1 + p.porcentaje_espacio_verde / 100
        self.tipos = [c.tipo for c in celdas]
        self.areas = [c.geometria.area for c in celdas]
        self.lotes = [i for i, tipo in enumerate(self.tipos) if tipo is TipoCelda.LOTE]
        # Solo el verde que computa para la cesión, con la regla del criterio de la corrida: con «más
        # cercanía», una punta que no alcanza el lado menor del art. 48 es verde (cuenta para la
        # distancia) pero no computa (D55, D58).
        self.verde = math.fsum(a for a, computa in zip(self.areas, computables(celdas, manzanas, p)) if computa)
        self.superficie_lotes = math.fsum(self.areas[i] for i in self.lotes)
        self.por_manzana = defaultdict(list)
        for i, celda in enumerate(celdas):
            self.por_manzana[celda.indice_manzana].append(i)
        # Las manzanas donde se puede convertir: todas al generar, las nuevas al recalcular (D56).
        self.convertibles = sorted(self.por_manzana if convertibles is None else set(convertibles) & set(self.por_manzana))
        self.vecinos = self._vecinos()
        # Cada verde es una pieza; las parcelas de una pieza, en el orden en que se sumaron.
        self.pieza_de: list[int | None] = [None] * len(celdas)
        self.piezas: list[list[int]] = []
        self.base: list[int | None] = []
        for i, tipo in enumerate(self.tipos):
            if tipo is TipoCelda.ESPACIO_VERDE:
                self.pieza_de[i] = len(self.piezas)
                self.piezas.append([i])
                self.base.append(i)
        self.originales = len(self.piezas)
        self.criterio = p.criterio_espacio_verde if criterio is None else criterio
        # Los lotes grandes (D47): se convierten antes que cualquier otro lote (paso 0).
        convertible = set(self.convertibles)
        self.grandes = [
            i for i in self.lotes if celdas[i].indice_manzana in convertible and es_lote_grande(celdas[i].geometria, p)
        ]
        # Las conversiones aplicadas, en orden, para podar las que sobren al final.
        self.aplicadas: list[Candidata] = []
        self._distancias(red, ejes)
        self._validez_manzana: dict[int, tuple[float, bool]] = {}

    # --- Cesión ----------------------------------------------------------------------------

    def faltante(self, verde: float | None = None, lotes: float | None = None) -> float:
        return faltante_cesion(
            self.verde if verde is None else verde, self.superficie_lotes if lotes is None else lotes, self.p
        )

    def aporte(self, i: int) -> float:
        if self.tipos[i] is TipoCelda.LOTE:
            return self.areas[i] * self.factor
        if self.tipos[i] is TipoCelda.ESPACIO_LIBRE:
            return self.areas[i]
        return 0.0

    def _tras(self, parcelas) -> tuple[float, float]:
        """El verde y los lotes que quedarían si `parcelas` pasaran a ser verde."""
        lotes = math.fsum(self.areas[i] for i in parcelas if self.tipos[i] is TipoCelda.LOTE)
        libres = math.fsum(self.areas[i] for i in parcelas if self.tipos[i] is TipoCelda.ESPACIO_LIBRE)
        return self.verde + lotes + libres, self.superficie_lotes - lotes

    def cubre(self, parcelas) -> bool:
        verde, lotes = self._tras(parcelas)
        return lotes > 0 and not self.faltante(verde, lotes)

    def exceso(self, c: Candidata) -> float:
        verde, lotes = self._tras(c.parcelas)
        return verde - exigido_cesion(lotes, self.p)

    def candidata(self, manzana, parcelas, base, clave) -> Candidata:
        return Candidata(
            manzana=manzana,
            parcelas=tuple(parcelas),
            base=base,
            aporte=math.fsum(self.aporte(i) for i in parcelas),
            superficie_lotes=math.fsum(self.areas[i] for i in parcelas if self.tipos[i] is TipoCelda.LOTE),
            cubre=self.cubre(parcelas),
            clave=clave,
            lotes=sum(1 for i in parcelas if self.tipos[i] is TipoCelda.LOTE),
        )

    def elegir(self, candidatas: Sequence[Candidata], rendimiento: bool = False) -> Candidata:
        return elegir(candidatas, self.criterio, self.distancia, self.exceso, rendimiento, self.distancia_maxima)

    def lotes_convertidos(self) -> int:
        return sum(1 for i in self.lotes if self.pieza_de[i] is not None)

    def distancia_final(self) -> float:
        """La distancia media de los lotes que quedan al verde más cercano, con el plan aplicado: la
        del indicador (`remanentes.distancias_al_verde`)."""
        quedan = [self.columna[i] for i in self.lotes if self.pieza_de[i] is None]
        return float(self.al_verde[quedan].mean()) if quedan else 0.0

    def mejor_que(self, otro: "_Plan") -> bool:
        """Este plan (del otro criterio) cumple mejor el pedido de `otro` (D46, D51): convierte
        menos lotes si `otro` es de «menos lotes», o deja menor distancia media si es de
        «cercanía». Con un empate, no."""
        if otro.criterio is CriterioEspacioVerde.MENOS_LOTES:
            return self.lotes_convertidos() < otro.lotes_convertidos()
        return round(self.distancia_final(), 3) < round(otro.distancia_final(), 3)

    # --- Vecindad y distancias ---------------------------------------------------------------

    def _vecinos(self) -> list[list[tuple[int, float]]]:
        """Las parcelas de la misma manzana con las que cada una comparte un lado, y su largo."""
        geometrias = [c.geometria for c in self.celdas]
        arbol = STRtree(geometrias)
        vecinos: list[list[tuple[int, float]]] = [[] for _ in geometrias]
        izquierda, derecha = arbol.query(geometrias, predicate="intersects")
        for i, j in sorted(zip(izquierda.tolist(), derecha.tolist())):
            if i < j and self.celdas[i].indice_manzana == self.celdas[j].indice_manzana:
                largo = geometrias[i].boundary.intersection(geometrias[j].boundary).length
                if largo > TOLERANCIA:
                    vecinos[i].append((j, largo))
                    vecinos[j].append((i, largo))
        return vecinos

    def _distancias(self, red: RedCirculacion, ejes: IndiceEjes) -> None:
        """La distancia por la red de cada parcela a cada lote, con la regla de los indicadores
        (`remanentes.distancias_al_verde`, D51): desde los puntos de acceso de la parcela hasta
        el punto medio del frente del lote. Una pieza verde llega a un lote desde el más cercano
        de los puntos de sus parcelas, que son los de la pieza unida."""
        puntos, filas = [], []
        for celda in self.celdas:
            propios = puntos_de_acceso(celda.geometria, self.circulacion)
            filas.append(list(range(len(puntos), len(puntos) + len(propios))))
            puntos += propios
        destinos = [punto_de_frente(self.celdas[i].geometria, self.circulacion, ejes) for i in self.lotes]
        self.matriz = red.matriz_distancias(puntos, destinos)
        self.filas = filas
        self.columna = {i: k for k, i in enumerate(self.lotes)}
        self.al_verde = np.full(len(self.lotes), math.inf)
        for pieza in self.piezas:
            self.al_verde = np.minimum(self.al_verde, self._vector(pieza))

    def _vector(self, parcelas) -> np.ndarray:
        filas = [fila for i in parcelas for fila in self.filas[i]]
        if not filas:
            return np.full(len(self.lotes), math.inf)
        return self.matriz[filas].min(axis=0)

    def distancia(self, c: Candidata) -> float:
        """Distancia media de los lotes que quedarían al verde más cercano, con la candidata."""
        al_verde, quedan = self._con(c)
        return float(al_verde[quedan].mean()) if quedan else 0.0

    def distancia_maxima(self, c: Candidata) -> float:
        """Distancia del lote que quedaría más lejos del verde, con la candidata."""
        al_verde, quedan = self._con(c)
        return float(al_verde[quedan].max()) if quedan else 0.0

    def _con(self, c: Candidata) -> tuple[np.ndarray, list[int]]:
        al_verde = np.minimum(self.al_verde, self._vector(c.parcelas))
        convertidas = set(c.parcelas)
        quedan = [self.columna[i] for i in self.lotes if self.pieza_de[i] is None and i not in convertidas]
        return al_verde, quedan

    # --- Candidatas --------------------------------------------------------------------------

    def _libres_de(self, manzana: int) -> list[int]:
        return [i for i in self.por_manzana[manzana] if self.pieza_de[i] is None]

    def crecimiento(self, pieza: int) -> list[int]:
        """Las parcelas que se suman a una pieza, de a una, primero la que comparte más borde con
        ella (con desempate por su orden), hasta que no queda ninguna vecina libre."""
        dentro = set(self.piezas[pieza])
        borde: dict[int, float] = defaultdict(float)
        for k in sorted(dentro):
            for j, largo in self.vecinos[k]:
                if j not in dentro and self.pieza_de[j] is None:
                    borde[j] += largo
        orden = []
        while borde:
            j = min(borde, key=lambda j: (-round(borde[j], 6), j))
            del borde[j]
            dentro.add(j)
            orden.append(j)
            for k, largo in self.vecinos[j]:
                if k not in dentro and self.pieza_de[k] is None:
                    borde[k] += largo
        return orden

    def recorridos(self, manzana: int) -> list[list[int]]:
        """Las parcelas libres de la manzana desde cada punta: en el orden en que se recorre su
        frente principal (el lado más largo que da a una calle) y en el contrario."""
        libres = self._libres_de(manzana)
        lados_calle = [lado for lado in lados(self.manzanas[manzana - 1], self.circulacion) if lado.toca]
        if not libres or not lados_calle:
            return []
        principal = max(enumerate(lados_calle), key=lambda par: (round(par[1].largo, 6), -par[0]))[1]
        u = unitario(principal.inicio, principal.fin)
        n = np.array([-u[1], u[0]])

        def proyecciones(i):
            centro = np.asarray(self.celdas[i].geometria.centroid.coords[0])
            return round(float(centro @ u), 3), round(float(centro @ n), 3)

        desde_inicio = sorted(libres, key=lambda i: (*proyecciones(i), i))
        desde_fin = sorted(libres, key=lambda i: (-proyecciones(i)[0], proyecciones(i)[1], i))
        return [desde_inicio, desde_fin]

    def es_verde(self, parcelas) -> bool:
        geometria = union_cobertura([self.celdas[i].geometria for i in parcelas])
        return isinstance(geometria, Polygon) and es_espacio_verde(geometria, self.circulacion, self.p)

    def minima(self, recorrido: list[int]) -> list[int] | None:
        """El menor prefijo del recorrido que cubre lo que falta y forma un verde válido."""
        for k in range(1, len(recorrido) + 1):
            if self.cubre(recorrido[:k]) and self.es_verde(recorrido[:k]):
                return recorrido[:k]
        return None

    def manzana_entera(self, manzana: int) -> tuple[float, bool]:
        """Aporte de las parcelas libres de la manzana, y si juntas forman un verde válido."""
        if manzana not in self._validez_manzana:
            libres = self._libres_de(manzana)
            aporte = math.fsum(self.aporte(i) for i in libres)
            valida = bool(libres) and self.es_verde(libres)
            self._validez_manzana[manzana] = (aporte, valida)
        return self._validez_manzana[manzana]

    # --- Resolución --------------------------------------------------------------------------

    def aplicar(self, c: Candidata) -> None:
        if c.base is None:
            pieza = len(self.piezas)
            self.piezas.append([])
            self.base.append(None)
        else:
            pieza = self.pieza_de[c.base]
        for i in c.parcelas:
            self.pieza_de[i] = pieza
            self.piezas[pieza].append(i)
        self.verde, self.superficie_lotes = self._tras(c.parcelas)
        self.al_verde = np.minimum(self.al_verde, self._vector(c.parcelas))
        self._validez_manzana.pop(c.manzana, None)
        self.aplicadas.append(c)

    def deshacer(self, c: Candidata) -> None:
        """Vuelve atrás una conversión: sus parcelas dejan de ser verde. Solo se usa con la última
        conversión de su pieza, así lo que queda de la pieza es lo que había antes."""
        pieza = self.pieza_de[c.parcelas[0]]
        for i in c.parcelas:
            self.pieza_de[i] = None
            self.piezas[pieza].remove(i)
        lotes = math.fsum(self.areas[i] for i in c.parcelas if self.tipos[i] is TipoCelda.LOTE)
        libres = math.fsum(self.areas[i] for i in c.parcelas if self.tipos[i] is TipoCelda.ESPACIO_LIBRE)
        self.verde -= lotes + libres
        self.superficie_lotes += lotes
        self.al_verde = np.full(len(self.lotes), math.inf)
        for parcelas in self.piezas:
            if parcelas:
                self.al_verde = np.minimum(self.al_verde, self._vector(parcelas))
        self._validez_manzana.pop(c.manzana, None)
        self.aplicadas.remove(c)

    def podar(self) -> None:
        """Saca, de la más vieja a la más nueva, toda conversión sin la cual igual se cubre la
        cesión (minimalidad, D46). Solo puede salir la última conversión de cada pieza: sacar una
        anterior dejaría sueltas las parcelas que se sumaron después."""
        for c in list(self.aplicadas):
            pieza = self.pieza_de[c.parcelas[0]]
            ultima = next(a for a in reversed(self.aplicadas) if self.pieza_de[a.parcelas[0]] == pieza)
            if ultima is not c:
                continue
            lotes = math.fsum(self.areas[i] for i in c.parcelas if self.tipos[i] is TipoCelda.LOTE)
            libres = math.fsum(self.areas[i] for i in c.parcelas if self.tipos[i] is TipoCelda.ESPACIO_LIBRE)
            if not self.faltante(self.verde - lotes - libres, self.superficie_lotes + lotes):
                self.deshacer(c)

    def vecino_verde(self, i: int) -> int | None:
        """Una parcela del verde de la manzana con el que la parcela `i` comparte más borde, o
        `None` si no linda con ninguno."""
        borde: dict[int, float] = defaultdict(float)
        for j, largo in self.vecinos[i]:
            if self.pieza_de[j] is not None:
                borde[self.pieza_de[j]] += largo
        if not borde:
            return None
        pieza = min(borde, key=lambda k: (-round(borde[k], 6), k))
        return self.piezas[pieza][0]

    def resolver(self) -> tuple[str, str] | None:
        """Convierte parcelas hasta cubrir la cesión, con los pasos del criterio, y poda lo que
        sobre. Devuelve la causa y la sugerencia si no se puede."""
        if self.criterio is CriterioEspacioVerde.CERCANIA:
            motivo = self._resolver_cercania()
        else:
            motivo = self._resolver()
        if motivo is None:
            self.podar()
        return motivo

    def _resolver_cercania(self) -> tuple[str, str] | None:
        """«Más cercanía» (D51): en cada paso compiten juntas todas las candidatas y gana la que deja
        menor distancia media de los lotes al verde, sin prioridad para los lotes grandes ni para
        los verdes que ya existen, y sin preferir pocas piezas grandes:

        - cada lote grande que solo es un verde válido (agranda el verde de su manzana con el que
          linda, si hay uno);
        - cada verde, agrandado con las parcelas vecinas de su manzana lo mínimo para cubrir lo que
          falta, o toda su manzana si no alcanza;
        - cada manzana desde cada punta, lo mínimo para cubrir lo que falta con un verde válido, o
          entera si no alcanza.

        Si la elegida no cubre, se aplica y se vuelve a elegir con lo que falta.
        """
        while self.faltante():
            candidatas = self._candidatas_cercania()
            if not candidatas:
                validas = {}
                for manzana in self.convertibles:
                    aporte, valida = self.manzana_entera(manzana)
                    if valida:
                        validas[manzana] = aporte
                if not validas:
                    return self._sin_piezas()
                if piezas_minimas(list(validas.values()), self.faltante()) is None:
                    return self._no_alcanza(validas)
                return self._sin_lotes()
            self.aplicar(self.elegir(candidatas))
        return None

    def _candidatas_cercania(self) -> list[Candidata]:
        faltante = self.faltante()
        candidatas = []
        for i in self.grandes:
            if self.pieza_de[i] is None and self.es_verde([i]):
                manzana = self.celdas[i].indice_manzana
                candidatas.append(self.candidata(manzana, [i], self.vecino_verde(i), (0, manzana, i)))
        convertible = set(self.convertibles)
        for pieza in range(len(self.piezas)):
            if not self.piezas[pieza] or self.celdas[self.piezas[pieza][0]].indice_manzana not in convertible:
                continue
            orden = self.crecimiento(pieza)
            if not orden:
                continue
            base = self.piezas[pieza][0]
            manzana = self.celdas[base].indice_manzana
            minimo = next((orden[:k] for k in range(1, len(orden) + 1) if self.cubre(orden[:k])), None)
            candidatas.append(self.candidata(manzana, minimo or orden, base, (1, manzana, base)))
        for manzana in self.convertibles:
            aporte, valida = self.manzana_entera(manzana)
            if not valida:
                continue
            puntas = []
            if aporte + TOLERANCIA >= faltante:
                for punta, recorrido in enumerate(self.recorridos(manzana)):
                    minimo = self.minima(recorrido)
                    if minimo is not None:
                        puntas.append(self.candidata(manzana, minimo, None, (2, manzana, punta)))
            candidatas += puntas or [self.candidata(manzana, self._libres_de(manzana), None, (2, manzana, 2))]
        return [c for c in candidatas if c.cubre or self._tras(c.parcelas)[1] > 0]

    def _resolver(self) -> tuple[str, str] | None:
        # Paso 0: los lotes grandes que solos son un verde válido (D46, D47).
        while self.faltante():
            candidatas = []
            for i in self.grandes:
                if self.pieza_de[i] is None and self.es_verde([i]):
                    manzana = self.celdas[i].indice_manzana
                    c = self.candidata(manzana, [i], self.vecino_verde(i), (manzana, i))
                    if c.cubre or self._tras(c.parcelas)[1] > 0:
                        candidatas.append(c)
            if not candidatas:
                break
            cubren = [c for c in candidatas if c.cubre]
            if cubren:
                self.aplicar(self.elegir(cubren))
                return None
            self.aplicar(max(candidatas, key=lambda c: (round(c.aporte, 2), [-x for x in c.clave])))

        # Paso 1: agrandar los verdes que ya existen.
        convertible = set(self.convertibles)
        while self.faltante():
            candidatas = []
            for pieza in range(self.originales):
                if self.celdas[self.piezas[pieza][0]].indice_manzana not in convertible:
                    continue
                orden = self.crecimiento(pieza)
                if not orden:
                    continue
                base = self.piezas[pieza][0]
                manzana = self.celdas[base].indice_manzana
                minimo = next((orden[:k] for k in range(1, len(orden) + 1) if self.cubre(orden[:k])), None)
                elegidas = minimo if minimo is not None else orden
                c = self.candidata(manzana, elegidas, base, (manzana, base))
                if c.cubre or self._tras(c.parcelas)[1] > 0:
                    candidatas.append(c)
            if not candidatas:
                break
            cubren = [c for c in candidatas if c.cubre]
            if cubren:
                self.aplicar(self.elegir(cubren))
                return None
            self.aplicar(max(candidatas, key=lambda c: (round(c.aporte, 2), [-x for x in c.clave])))

        # Paso 2: convertir manzanas, enteras o desde una punta.
        while self.faltante():
            # Lo que falta en m² de verde es lo que hay que cubrir en unidades de aporte (ver arriba).
            faltante = self.faltante()
            validas = {}
            for manzana in self.convertibles:
                aporte, valida = self.manzana_entera(manzana)
                if valida:
                    validas[manzana] = aporte
            if not validas:
                return self._sin_piezas()
            k = piezas_minimas(list(validas.values()), faltante)
            if k is None:
                return self._no_alcanza(validas)
            if k == 1:
                candidatas = []
                for manzana in sorted(validas):
                    if validas[manzana] + TOLERANCIA < faltante:
                        continue
                    for punta, recorrido in enumerate(self.recorridos(manzana)):
                        minimo = self.minima(recorrido)
                        if minimo is not None:
                            candidatas.append(self.candidata(manzana, minimo, None, (manzana, punta)))
                candidatas = [c for c in candidatas if c.cubre]
                if not candidatas:
                    return self._sin_lotes()
                self.aplicar(self.elegir(candidatas))
                return None
            # Con k* ≥ 2, una manzana entera que no obligue a usar más de k* piezas.
            candidatas = []
            for manzana in sorted(validas):
                otras = sorted((a for m, a in validas.items() if m != manzana), reverse=True)
                if validas[manzana] + math.fsum(otras[: k - 1]) + TOLERANCIA >= faltante:
                    libres = self._libres_de(manzana)
                    c = self.candidata(manzana, libres, None, (manzana, 2))
                    if self._tras(c.parcelas)[1] > 0:
                        candidatas.append(c)
            if not candidatas:
                return self._sin_lotes()
            # Una manzana entera que no cubre sola: con «menos lotes», la que más rinde por lote.
            self.aplicar(self.elegir(candidatas, rendimiento=True))
        return None

    # --- Motivos ------------------------------------------------------------------------------

    def _sin_piezas(self) -> tuple[str, str]:
        p = self.p
        return (
            f"Faltan {_numero(self.faltante())} m² de espacio verde y ninguna manzana admite un verde de "
            f"{_numero(p.superficie_minima_verde)} m² y {_numero(p.ancho_minimo_verde)} m de ancho con frente "
            "a una calle.",
            "Revisá los umbrales del verde o la separación de las calles: en un terreno tan chico puede no "
            "haber lugar para una plaza.",
        )

    def _no_alcanza(self, validas: dict[int, float]) -> tuple[str, str]:
        parcelas = [i for m in sorted(validas) for i in self._libres_de(m)]
        verde, lotes = self._tras(parcelas)
        maximo = 100 * verde / lotes if lotes > 0 else 0.0
        return (
            "Aun convirtiendo en verde todas las manzanas que lo admiten, la cesión llegaría al "
            f"{_numero(maximo)} % de la superficie de los lotes.",
            "Probá otra orientación de la grilla o revisá los umbrales del verde.",
        )

    def _sin_lotes(self) -> tuple[str, str]:
        return (
            "Llegar a la cesión dejaría el terreno sin lotes.",
            "El terreno es muy chico para el porcentaje de espacio verde: revisá los parámetros.",
        )

    # --- Resultado ----------------------------------------------------------------------------

    def _cambiadas(self) -> list[int]:
        """Las piezas nuevas o agrandadas, en orden. Una pieza nueva que la poda vació no cuenta."""
        return [k for k, pieza in enumerate(self.piezas) if pieza and (self.base[k] is None or len(pieza) > 1)]

    def celdas_resultantes(self, nombres: Sequence[str] = ()) -> tuple[CeldaGenerada, ...]:
        """Las celdas con las piezas verdes unidas: cada pieza ocupa el lugar de su primera
        parcela en el orden original, y todo se vuelve a numerar por manzana."""
        cambiadas = set(self._cambiadas())
        unidas = {
            min(self.piezas[k]): union_cobertura([self.celdas[i].geometria for i in self.piezas[k]])
            for k in sorted(cambiadas)
        }
        resultado = []
        for i, celda in enumerate(self.celdas):
            if i in unidas:
                verde = replace(celda, geometria=unidas[i], tipo=TipoCelda.ESPACIO_VERDE)
                resultado.append(medida_de(verde, self.circulacion, self.ejes))
            elif self.pieza_de[i] not in cambiadas:
                resultado.append(celda)
        solo = None if len(self.convertibles) == len(self.por_manzana) else frozenset(self.convertibles)
        return tuple(numerar(resultado, nombres, solo))

    def piezas_resultantes(self) -> tuple[PiezaVerde, ...]:
        resultado = []
        for k in self._cambiadas():
            parcelas = self.piezas[k]
            agregadas = parcelas[1:] if self.base[k] is not None else parcelas
            resultado.append(
                PiezaVerde(
                    indice_manzana=self.celdas[parcelas[0]].indice_manzana,
                    parcelas=tuple(self.celdas[i].designacion for i in agregadas),
                    base=None if self.base[k] is None else self.celdas[self.base[k]].designacion,
                )
            )
        return tuple(resultado)


def _numero(valor: float) -> str:
    """Número con dos decimales, coma decimal y punto de miles (RNF01)."""
    return f"{valor:_.2f}".replace(".", ",").replace("_", ".")
