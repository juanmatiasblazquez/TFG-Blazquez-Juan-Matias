"""Fijar sectores y recalcular (CU09, RF12; secuencia de la p. 44; pantalla de la p. 50; D56)."""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.alternativa import EstrategiaIn, EstrategiaOut
from app.schemas.comunes import PoligonoGeoJSON

# Una designación de manzana, como las guarda la base («M6»).
Designacion = str


class SectorIn(BaseModel):
    """Lo que el proyectista eligió en el mapa (CU09, paso 2): manzanas por un clic en sus celdas,
    un contorno dibujado, o los dos. El contorno suma las manzanas que quedan enteras adentro."""

    model_config = ConfigDict(extra="forbid")

    manzanas: list[Designacion] = Field(default_factory=list, max_length=500, examples=[["M6", "M7"]])
    contorno: PoligonoGeoJSON | None = Field(None, description="Polígono en EPSG:4326 (longitud, latitud).")


class SectorOut(BaseModel):
    """Lo que se fijaría, resaltado antes de confirmar (CU09, paso 3): las manzanas, el sector con
    sus calles y los anclajes, con sus indicadores. No guarda nada. Los anclajes son los nodos de la
    red fijada donde una calle seguía hacia lo que se recalcula (`MotorGeneracion.fijar`, p. 44)."""

    id_version: int
    manzanas: list[Designacion]
    sector: dict
    anclajes: dict
    cantidad_anclajes: int
    superficie_m2: float
    # El sector sobre la superficie disponible: el terreno menos las áreas reservadas (D61).
    porcentaje_disponible: float
    cantidad_celdas: int
    cantidad_lotes: int
    cantidad_celdas_utiles: int
    superficie_espacio_verde_m2: float
    # La estrategia que se propone para recalcular: la de la versión de origen (D60). Con otra
    # orientación, la grilla nueva se cruza con la fijada y se pierden lotes junto al sector.
    estrategia_sugerida: EstrategiaOut


class RecalculoIn(BaseModel):
    """La confirmación del recálculo (CU09, paso 4): las manzanas que se conservan y la estrategia,
    la vigente o una modificada. Se recalcula con los parámetros vigentes del proyecto."""

    model_config = ConfigDict(extra="forbid")

    estrategia: EstrategiaIn
    manzanas: list[Designacion] = Field(max_length=500, examples=[["M6", "M7"]])
