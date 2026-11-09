from pydantic import BaseModel


class ProblemaOut(BaseModel):
    """Un dato que no es válido, con el campo al que se refiere (RNF01)."""

    campo: str
    mensaje: str


class ErrorOut(BaseModel):
    """Cuerpo de toda respuesta de error de la API (D32)."""

    causa: str
    sugerencia: str | None = None
    problemas: list[ProblemaOut] = []
    # GeoJSON (EPSG:4326) de lo que falló, por ejemplo la parte de la red que no se conecta.
    geometria: dict | None = None
