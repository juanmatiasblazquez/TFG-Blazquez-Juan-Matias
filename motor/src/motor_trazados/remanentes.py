"""Remanentes: las fracciones de una manzana donde no entra un lote válido (D41, D43).

Después de subdividir y cerrar la partición, cada pieza se mide como la mide el verificador:

- si es un lote (tiene frente, alcanza el frente, el fondo y la superficie mínimos, y cumple el
  criterio de forma: la relación fondo/frente y el ancho útil; `verificador.es_lote`), es un
  lote;
- si no, se suma a un lote vecino de la misma manzana, con el que comparte un lado, siempre que
  el lote que resulta cumpla todas las restricciones, no pase la superficie máxima ni el tope de
  unión: `factor_union_maximo` veces el lote típico de la manzana (D43);
- si tampoco, las fracciones vecinas de una manzana que quedaron sin lote forman una sola zona.
  Si la zona cumple todas las restricciones y no pasa la superficie máxima, es un lote válido.
  Si no, es un remanente: **espacio verde** si alcanza la superficie y el ancho mínimos del verde
  y da a una calle, y **espacio libre** si no.

Así ningún remanente es un lote válido. Un lote del subdivisor que pasa la superficie máxima es
un lote grande (`verificador.es_lote_grande`, D47): no es un incumplimiento. El motor intenta
subdividirlo antes de cerrar la partición, y el asignador lo convierte en verde antes que a
cualquier otro lote.

Nada se descarta: los remanentes son parte de la partición. El verde cuenta para la cesión
(Ley 4146, art. 7) y el libre no; el verde de una punta que no alcanza el lado menor del art. 48
tampoco (`verificador.computa_para_cesion`, D55).
"""

import math
import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from shapely import Point, Polygon
from shapely.geometry.base import BaseGeometry

from .contrato import CeldaGenerada, ParametrosLoteo, TipoCelda
from .geometria import (
    TOLERANCIA,
    TOLERANCIA_AREA,
    IndiceEjes,
    alcanza_ancho,
    clave_punto,
    lados,
    medir,
    union_cobertura,
)
from .verificador import es_lote, es_lote_grande, incumplimientos_de_lote

if TYPE_CHECKING:
    from .red import RedCirculacion

# Prefijo de la designación de cada tipo de celda: «M3-L07», «M3-EV01», «M3-EL01».
PREFIJOS = {TipoCelda.LOTE: "L", TipoCelda.ESPACIO_VERDE: "EV", TipoCelda.ESPACIO_LIBRE: "EL"}


def toca_la_red(poligono: Polygon, circulacion: BaseGeometry) -> bool:
    """Algún lado del polígono da a un corredor: el mismo criterio que un frente."""
    return any(lado.toca for lado in lados(poligono, circulacion))


def es_espacio_verde(poligono: Polygon, circulacion: BaseGeometry, p: ParametrosLoteo) -> bool:
    """Un remanente es espacio verde si alcanza la superficie y el ancho mínimos del verde y da
    a una calle: un verde sin acceso público no tiene la «ubicación adecuada» del art. 7 de la
    Ley 4146 (decisión del autor, D41). Una diferencia menor a la tolerancia no lo excluye.

    Es la copia única de esta regla: la usan el clasificador y el asignador de espacios verdes.
    """
    return (
        poligono.area + TOLERANCIA_AREA >= p.superficie_minima_verde
        and toca_la_red(poligono, circulacion)
        and alcanza_ancho(poligono, p.ancho_minimo_verde)
    )


def puntos_de_acceso(poligono: Polygon, circulacion: BaseGeometry) -> list[Point]:
    """Por dónde se entra a una pieza desde la calle: los extremos y el punto medio de cada
    segmento de su borde que da a un corredor, en orden estable (D51).

    Es la copia única de esta regla, con `punto_de_frente` y `distancias_al_verde`. Una pieza
    verde que el asignador arma uniendo parcelas tiene exactamente los puntos de sus parcelas: la
    unión de cobertura no mueve ni saca vértices, y los segmentos sobre la calle de cada parcela
    siguen siendo segmentos de la pieza. Así la distancia que optimiza el asignador es la que
    informan los indicadores.
    """
    puntos: dict = {}
    for lado in lados(poligono, circulacion):
        if not lado.toca:
            continue
        for a, b in zip(lado.puntos, lado.puntos[1:]):
            for punto in (a, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), b):
                puntos.setdefault(clave_punto(*punto), punto)
    return [Point(puntos[clave]) for clave in sorted(puntos)]


def punto_de_frente(poligono: Polygon, circulacion: BaseGeometry, ejes: IndiceEjes) -> Point | None:
    """Desde dónde se mide la distancia de un lote: el punto medio de su frente, como lo mide el
    verificador (D26). `None` si la pieza no da a ninguna calle."""
    linea = medir(poligono, circulacion, ejes).linea_frente
    return None if linea is None else Point(linea.interpolate(0.5, normalized=True))


def distancias_al_verde(
    lotes: Sequence[Polygon],
    verdes: Sequence[Polygon],
    circulacion: BaseGeometry,
    ejes: IndiceEjes,
    red: "RedCirculacion",
) -> list[float]:
    """La distancia por la red de cada lote al espacio verde más cercano (D51): desde el punto
    medio de su frente hasta el punto de acceso más cercano de algún verde
    (`RedCirculacion.matriz_distancias`, la copia única de la distancia por la red). `inf` si no
    hay verde, si el lote no da a una calle o si no hay camino."""
    origenes = [punto for verde in verdes for punto in puntos_de_acceso(verde, circulacion)]
    destinos = [punto_de_frente(lote, circulacion, ejes) for lote in lotes]
    validos = [k for k, destino in enumerate(destinos) if destino is not None]
    resultado = [math.inf] * len(lotes)
    if not origenes or not validos:
        return resultado
    minimas = red.matriz_distancias(origenes, [destinos[k] for k in validos]).min(axis=0)
    for k, distancia in zip(validos, minimas, strict=True):
        resultado[k] = float(distancia)
    return resultado


def numerar(
    celdas: list[CeldaGenerada], nombres: Sequence[str] = (), solo: frozenset[int] | None = None
) -> list[CeldaGenerada]:
    """Designa las celdas por manzana y por tipo, en el orden de la lista: «M3-L07», «M3-EV01».

    `nombres[k]` es el nombre de la manzana `k + 1` («M1» … si no se da). En un recálculo (D56) las
    manzanas fijadas conservan el suyo, y `solo` dice qué manzanas se designan: las celdas fijadas
    conservan su designación de origen."""
    contadores: dict[tuple[int, TipoCelda], int] = defaultdict(int)
    resultado = []
    for celda in celdas:
        if solo is not None and celda.indice_manzana not in solo:
            resultado.append(celda)
            continue
        contadores[(celda.indice_manzana, celda.tipo)] += 1
        numero = contadores[(celda.indice_manzana, celda.tipo)]
        manzana = nombres[celda.indice_manzana - 1] if nombres else f"M{celda.indice_manzana}"
        resultado.append(replace(celda, designacion=f"{manzana}-{PREFIJOS[celda.tipo]}{numero:02d}"))
    return resultado


def medida_de(celda: CeldaGenerada, circulacion: BaseGeometry, ejes: IndiceEjes) -> CeldaGenerada:
    """La celda con el frente y el fondo que mide el verificador (D26)."""
    medida = medir(celda.geometria, circulacion, ejes)
    return replace(celda, frente=medida.frente, fondo=medida.fondo)


class ClasificadorRemanentes:
    def clasificar(
        self,
        piezas: list[CeldaGenerada],
        circulacion: BaseGeometry,
        ejes: IndiceEjes,
        p: ParametrosLoteo,
        nombres: Sequence[str] = (),
    ) -> list[CeldaGenerada]:
        """Clasifica las piezas (lote, espacio verde o espacio libre), suma a sus vecinos las
        fracciones que pueden ser parte de un lote, y designa cada celda por manzana.

        `piezas` son las celdas que dejó el subdivisor, ya cerradas y en el sistema de cálculo;
        `circulacion` es la unión de los corredores. `nombres` son los de las manzanas (`numerar`). Una pieza que no llega como lote candidato
        (la de una manzana que no alcanza el lado menor del art. 48, D50) es remanente siempre:
        no se vuelve lote ni sola, ni unida a un vecino, ni como zona.
        """
        geometrias = [pieza.geometria for pieza in piezas]
        candidata = [pieza.tipo is TipoCelda.LOTE for pieza in piezas]
        lote = [c and es_lote(g, medir(g, circulacion, ejes), p) for c, g in zip(candidata, geometrias)]
        vivas = [True] * len(piezas)
        por_manzana = defaultdict(list)
        for i, pieza in enumerate(piezas):
            por_manzana[pieza.indice_manzana].append(i)
        # El lote típico de cada manzana, antes de las uniones: la mediana de sus lotes (D43).
        tipico = {
            manzana: statistics.median(geometrias[i].area for i in indices if lote[i])
            for manzana, indices in sorted(por_manzana.items())
            if any(lote[i] for i in indices)
        }

        for i in range(len(piezas)):
            if lote[i]:
                continue
            manzana = piezas[i].indice_manzana
            if manzana not in tipico:
                continue
            tope = p.factor_union_maximo * tipico[manzana]
            # Los lotes vecinos de la misma manzana, primero el que comparte más borde.
            vecinos = []
            for j in por_manzana[manzana]:
                if j != i and vivas[j] and lote[j]:
                    largo = geometrias[i].boundary.intersection(geometrias[j].boundary).length
                    if largo > TOLERANCIA:
                        vecinos.append((-round(largo, 6), j))
            for _, j in sorted(vecinos):
                unida = union_cobertura([geometrias[j], geometrias[i]])
                if (
                    isinstance(unida, Polygon)
                    and unida.area <= tope + TOLERANCIA_AREA
                    and not es_lote_grande(unida, p)
                    and not incumplimientos_de_lote(unida, medir(unida, circulacion, ejes), p)
                ):
                    geometrias[j] = unida
                    vivas[i] = False
                    break

        # Las fracciones vecinas de una misma manzana que quedaron sin lote son una sola zona:
        # se unen antes de clasificarla, así el verde se mide sobre la zona entera.
        for i in range(len(piezas)):
            if lote[i] or not vivas[i]:
                continue
            pendientes = [i]
            while pendientes:
                k = pendientes.pop()
                for j in por_manzana[piezas[i].indice_manzana]:
                    if j != i and vivas[j] and not lote[j]:
                        largo = geometrias[k].boundary.intersection(geometrias[j].boundary).length
                        if largo > TOLERANCIA:
                            geometrias[i] = union_cobertura([geometrias[i], geometrias[j]])
                            vivas[j] = False
                            pendientes.append(j)
            # Una zona que cumple todas las restricciones, también la forma, y no pasa la
            # superficie máxima es un lote válido aunque ninguna de sus fracciones lo fuera. Si
            # solo alcanza los mínimos (una franja angosta medida por su punta, por ejemplo), es
            # remanente.
            if (
                candidata[i]
                and not es_lote_grande(geometrias[i], p)
                and not incumplimientos_de_lote(geometrias[i], medir(geometrias[i], circulacion, ejes), p)
            ):
                lote[i] = True

        celdas = []
        for i, pieza in enumerate(piezas):
            if not vivas[i]:
                continue
            geometria = geometrias[i]
            if lote[i]:
                tipo = TipoCelda.LOTE
            elif es_espacio_verde(geometria, circulacion, p):
                tipo = TipoCelda.ESPACIO_VERDE
            else:
                tipo = TipoCelda.ESPACIO_LIBRE
            celdas.append(medida_de(replace(pieza, geometria=geometria, tipo=tipo), circulacion, ejes))
        return numerar(celdas, nombres)
