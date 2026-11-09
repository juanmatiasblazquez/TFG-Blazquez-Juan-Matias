"""Piezas comunes de los schemas: GeoJSON (RFC 7946, EPSG:4326) y el resumen de un usuario."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator
from shapely import Point, Polygon

# Columnas `integer` del ER (semilla, srid_calculo): PostgreSQL no admite más que esto.
ENTERO_MAX = 2**31 - 1

Longitud = Annotated[float, Field(ge=-180, le=180)]
Latitud = Annotated[float, Field(ge=-90, le=90)]
# GeoJSON en 2D: (longitud, latitud), en ese orden (always_xy, D21).
Posicion = tuple[Longitud, Latitud]


class PuntoGeoJSON(BaseModel):
    type: Literal["Point"]
    coordinates: Posicion

    def a_shapely(self) -> Point:
        return Point(self.coordinates)


class PoligonoGeoJSON(BaseModel):
    """Polígono GeoJSON: el primer anillo es el borde y los demás, huecos."""

    type: Literal["Polygon"]
    coordinates: Annotated[list[Annotated[list[Posicion], Field(min_length=4)]], Field(min_length=1)]

    @field_validator("coordinates")
    @classmethod
    def _anillos_cerrados(cls, anillos: list[list[Posicion]]) -> list[list[Posicion]]:
        if any(anillo[0] != anillo[-1] for anillo in anillos):
            raise ValueError(
                "Cada anillo tiene que cerrarse: la primera y la última posición son la misma (RFC 7946)."
            )
        return anillos

    def a_shapely(self) -> Polygon:
        return Polygon(self.coordinates[0], self.coordinates[1:])


class Feature(BaseModel):
    type: Literal["Feature"] = "Feature"
    # Geometría GeoJSON en EPSG:4326 con 8 decimales (motor_trazados.exportar), o null.
    geometry: dict[str, Any] | None
    properties: dict[str, Any]


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature]


class UsuarioResumen(BaseModel):
    id_usuario: int
    nombre: str
    apellido: str
