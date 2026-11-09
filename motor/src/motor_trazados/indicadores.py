"""Calculador de indicadores (CU08; p. 47; D26).

Todas las alternativas se evalúan con los mismos indicadores, así son comparables (CU08).
"""

import math
from collections.abc import Sequence

from shapely import Point

from .contrato import Indicadores, ParametrosLoteo, ResultadoGeneracion
from .geometria import IndiceEjes, medir, union_cobertura
from .remanentes import distancias_al_verde
from .verificador import es_lote_grande, porcentaje_avenidas, verde_computable


class CalculadorIndicadores:
    def calcular(
        self,
        resultado: ResultadoGeneracion,
        superficie_terreno: float,
        accesos: Sequence[Point],
        parametros: ParametrosLoteo,
    ) -> Indicadores:
        """Indicadores de una alternativa ya verificada.

        - Celda útil: un lote sin incumplimientos. Un lote grande (pasa la superficie máxima) es
          útil: no es un incumplimiento, y se cuenta aparte (D47).
        - Distancia media al acceso: para cada celda útil, la distancia por caminos mínimos
          sobre la red desde el acceso más cercano hasta la proyección del punto medio de su
          frente sobre el eje más cercano (CU08, paso 3).
        - Cesión alcanzada: el espacio verde computable sobre la superficie de todos los lotes,
          cumplan o no, que es la base de la cesión (Ley 4146, art. 7; D41). El espacio libre no
          cuenta, y una punta verde tampoco (`verificador.computa_para_cesion`, D55): el verde
          total y el computable se informan por separado.
        - Distancia al verde: la media y la máxima, sobre todos los lotes, de la distancia por la
          red de cada uno al espacio verde más cercano (`remanentes.distancias_al_verde`, D51). Es
          la medida que optimiza el asignador con «más cercanía».
        - Superficie reservada: la de las áreas reservadas (D59). Los porcentajes del aprovechamiento,
          la circulación y el verde son sobre la superficie disponible, el terreno menos las áreas
          (D61): lo que se lotea. Sin áreas la disponible es el terreno, bit a bit (`x - 0.0`).
        """
        marcadas = {incumplimiento.elemento for incumplimiento in resultado.incumplimientos}
        lotes = resultado.lotes
        utiles = [lote for lote in lotes if lote.designacion not in marcadas]
        superficie_aprovechable = math.fsum(lote.geometria.area for lote in utiles)
        superficie_lotes = math.fsum(lote.geometria.area for lote in lotes)
        # Los corredores son una partición sin solapes: la suma es exacta.
        circulacion = math.fsum(corredor.area for corredor in resultado.corredores)
        verde = math.fsum(espacio.area for espacio in resultado.espacios_verdes)
        computable = verde_computable(resultado.celdas, resultado.manzanas, parametros)
        libre = math.fsum(espacio.area for espacio in resultado.espacios_libres)
        media_verde, maxima_verde = self._distancias_al_verde(resultado)
        reservada = math.fsum(area.area for area in resultado.reservadas)
        disponible = superficie_terreno - reservada
        return Indicadores(
            cantidad_celdas=len(utiles),
            cantidad_fracciones_no_conformes=len(lotes) - len(utiles),
            superficie_terreno=superficie_terreno,
            superficie_aprovechable=superficie_aprovechable,
            porcentaje_aprovechamiento=100 * superficie_aprovechable / disponible,
            porcentaje_circulacion=100 * circulacion / disponible,
            porcentaje_espacio_verde=100 * verde / disponible,
            longitud_red=resultado.red.longitud_total(),
            distancia_media_acceso=self._distancia_media(resultado, utiles, accesos),
            superficie_espacio_verde=verde,
            superficie_espacio_libre=libre,
            porcentaje_cesion=100 * computable / superficie_lotes if superficie_lotes > 0 else None,
            cantidad_lotes_grandes=sum(1 for lote in lotes if es_lote_grande(lote.geometria, parametros)),
            porcentaje_avenidas=porcentaje_avenidas(resultado.red, parametros),
            distancia_media_verde=media_verde,
            distancia_maxima_verde=maxima_verde,
            superficie_verde_computable=computable,
            superficie_disponible=disponible,
            superficie_reservada=reservada,
        )

    def _distancias_al_verde(self, resultado) -> tuple[float | None, float | None]:
        lotes, verdes = resultado.lotes, resultado.espacios_verdes
        if not lotes or not verdes:
            return None, None
        corredores = union_cobertura(resultado.corredores)
        ejes = IndiceEjes([tramo.eje for tramo in resultado.red.tramos()])
        distancias = [
            d
            for d in distancias_al_verde([l.geometria for l in lotes], verdes, corredores, ejes, resultado.red)
            if math.isfinite(d)
        ]
        if not distancias:
            return None, None
        return math.fsum(distancias) / len(distancias), max(distancias)

    def _distancia_media(self, resultado, utiles, accesos) -> float | None:
        if not utiles:
            return None
        corredores = union_cobertura(resultado.corredores)
        ejes = IndiceEjes([tramo.eje for tramo in resultado.red.tramos()])
        destinos = []
        for lote in utiles:
            linea = medir(lote.geometria, corredores, ejes).linea_frente
            destinos.append(linea.interpolate(0.5, normalized=True))
        distancias = [d for d in resultado.red.distancias_por_red(accesos, destinos) if d is not None]
        if not distancias:
            return None
        return math.fsum(distancias) / len(distancias)
