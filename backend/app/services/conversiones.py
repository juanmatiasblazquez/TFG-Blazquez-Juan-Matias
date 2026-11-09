"""Conversiones del borde de la base: geometrías (shapely ↔ PostGIS ↔ GeoJSON) y números.

Las geometrías se guardan en EPSG:4326 con la precisión completa que da pyproj, sin redondear:
así PostGIS mide las mismas superficies que informó el motor (D30). El redondeo a 8 decimales
es solo de salida, y su copia única está en `motor_trazados.exportar`.
"""

from decimal import ROUND_HALF_EVEN, Decimal

from geoalchemy2 import WKBElement
from geoalchemy2.shape import from_shape, to_shape
from motor_trazados.exportar import geojson_geografico
from shapely.geometry.base import BaseGeometry

from app.models.tipos import SRID_GUARDADO
from app.schemas.comunes import Feature, FeatureCollection

CENTESIMO = Decimal("0.01")


def guardable(geometria_4326: BaseGeometry) -> WKBElement:
    return from_shape(geometria_4326, srid=SRID_GUARDADO)


def leida(elemento: WKBElement) -> BaseGeometry:
    return to_shape(elemento)


def geojson(elemento: WKBElement | None) -> dict | None:
    return None if elemento is None else geojson_geografico(to_shape(elemento))


def feature(elemento: WKBElement | None, propiedades: dict) -> Feature:
    return Feature(geometry=geojson(elemento), properties=propiedades)


def coleccion(features: list[Feature]) -> FeatureCollection:
    return FeatureCollection(features=features)


def centesimos(valor: float) -> Decimal:
    """Un valor del motor llevado a las columnas numeric(…, 2) del ER. Se redondea acá, con una
    regla explícita, y no en la conversión implícita de PostgreSQL."""
    return Decimal(valor).quantize(CENTESIMO, rounding=ROUND_HALF_EVEN)


def numero(valor: Decimal | None) -> float | None:
    return None if valor is None else float(valor)
