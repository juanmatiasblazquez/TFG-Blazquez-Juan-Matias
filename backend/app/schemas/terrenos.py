"""Entrada y salida de la medición del terreno y de la importación de vértices (CU04; figura 15; D79, D80)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.comunes import ENTERO_MAX, PoligonoGeoJSON, PuntoGeoJSON
from app.schemas.errores import ProblemaOut

# [longitud, latitud], con la precisión completa.
Posicion = list[float]


def _srid():
    return Field(
        None,
        ge=1,
        le=ENTERO_MAX,
        description="EPSG del sistema de cálculo. Si falta, la faja POSGAR 2007 que corresponde al terreno.",
    )


class MedicionIn(BaseModel):
    """Lo dibujado hasta ahora en el paso 2 del alta: el terreno, los accesos y las áreas, en EPSG:4326."""

    model_config = ConfigDict(extra="forbid")

    terreno: PoligonoGeoJSON
    accesos: list[PuntoGeoJSON] = Field(default_factory=list, max_length=50)
    areas_reservadas: list[PoligonoGeoJSON] = Field(default_factory=list, max_length=50)
    srid_calculo: int | None = _srid()


class VerticeOut(BaseModel):
    designacion: str
    posicion: Posicion


class LadoOut(BaseModel):
    """El lado que va de `desde` a `hasta`, medido en el sistema de cálculo."""

    desde: str
    hasta: str
    largo_m: float
    punto_medio: Posicion


class AreaMedidaOut(BaseModel):
    designacion: str
    superficie_m2: float | None


class ReglaGeometriaOut(BaseModel):
    """Una regla de la geometría (CU04, 3.a y 6.a), cumplida o no, con su detalle en español."""

    clave: str
    descripcion: str
    cumple: bool
    detalle: str


class MedicionOut(BaseModel):
    """La medición del terreno (figura 15, «Terreno» y «Validación de la geometría»; D79). La hace la API
    en el sistema de cálculo, con las reglas del motor: el portal no mide ni valida nada (D37).
    `superficie_m2` y `perimetro_m` son None si el polígono no es válido."""

    srid_calculo: int
    sistema: str
    superficie_m2: float | None
    perimetro_m: float | None
    vertices: list[VerticeOut]
    lados: list[LadoOut]
    areas: list[AreaMedidaOut]
    reglas: list[ReglaGeometriaOut]
    problemas: list[ProblemaOut]


class ImportacionIn(BaseModel):
    """El texto de una planilla de vértices (CSV, D80)."""

    model_config = ConfigDict(extra="forbid")

    contenido: str = Field(min_length=1, max_length=200_000)
    srid_calculo: int | None = _srid()


class ImportacionOut(BaseModel):
    """El terreno leído, en EPSG:4326 con la precisión completa (D37), y en qué sistema venía."""

    terreno: PoligonoGeoJSON
    formato: Literal["posgar", "geograficas"]
    sistema: str
    # El sistema de cálculo que corresponde: el de la faja de las coordenadas (POSGAR) o el pedido.
    srid_calculo: int
    cantidad_vertices: int

