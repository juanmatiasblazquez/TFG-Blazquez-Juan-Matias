"""Comparación de alternativas (CU13, RF15; pantalla de la p. 51; D54).

Es de solo lectura: lee las versiones vigentes y no guarda nada (postcondición del CU13).
"""

from pydantic import BaseModel

from app.schemas.alternativa import EstrategiaOut, Sentido


class AlternativaComparadaOut(BaseModel):
    """Una de las alternativas comparadas, con su versión vigente (la de mayor número), o la versión
    pedida cuando se comparan versiones (D57)."""

    id_alternativa: int
    codigo: str
    id_version: int
    numero: int
    cumple_restricciones: bool
    version_parametros: int
    version_motor: str
    estrategia: EstrategiaOut
    # El estado de la alternativa (generada, observada, seleccionada) y sus observaciones bloqueantes sin
    # responder: la casilla «Seleccionada» de cada mapa y su «Obs. bloqueante» (figura 20; D84).
    estado: str
    bloqueantes_abiertas: int
    # El criterio del verde de la versión, para la insignia de la barra (D83); None si no aplica (D45).
    criterio_espacio_verde: str | None


class IndicadorComparadoOut(BaseModel):
    """Una fila de la tabla de indicadores.

    `indicador` es el campo de `IndicadoresOut`, o «observaciones_bloqueantes_abiertas» (la última fila
    de la p. 51, solo entre alternativas; D84). `valores` va en el orden de las alternativas.
    `diferencias[k]` es `valores[k] − valores[0]`: nula para la primera, o si falta alguno de los
    dos («no aplica», sin verde). `mejores` son los índices de las alternativas con el mejor valor,
    solo si el indicador tiene `sentido`; vacía si todas las que compiten empatan.
    """

    indicador: str
    sentido: Sentido | None
    # Los conteos van como enteros; el resto, con dos decimales.
    valores: list[int | float | None]
    diferencias: list[int | float | None]
    mejores: list[int]


class DiferenciaOut(BaseModel):
    """Un parámetro o un dato de la estrategia en el que difieren las alternativas.

    `campo` es el de `ParametrosIn` («loteo.criterio_espacio_verde», «porcentaje_espacio_verde»,
    «jerarquias[0].ancho_calzada_m»), o «estrategia.orientacion_grados», «estrategia.semilla»,
    «estrategia.patron_red» y «version_motor». `valores` va en el orden de las alternativas; nulo
    es «no aplica» (D45).
    """

    campo: str
    valores: list[int | float | str | None]


class ComparacionOut(BaseModel):
    id_proyecto: int
    alternativas: list[AlternativaComparadaOut]
    indicadores: list[IndicadorComparadoOut]
    # Solo lo que difiere: qué decisión separa a las alternativas.
    diferencias: list[DiferenciaOut]
