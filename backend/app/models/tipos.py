"""Tipos de columna compartidos por los modelos (D28)."""

from datetime import datetime
from typing import Annotated

from geoalchemy2 import Geometry
from motor_trazados.coordenadas import EPSG_GEOGRAFICAS
from sqlalchemy import DateTime, func
from sqlalchemy.orm import mapped_column

# Todas las geometrías se guardan en EPSG:4326 (ER, p. 47); el motor calcula en metros y la
# conversión la hace motor_trazados.coordenadas en el borde (D21).
SRID_GUARDADO = EPSG_GEOGRAFICAS

# El ER dice «timestamp»; se usa timestamp with time zone para que una fecha no cambie de
# sentido con la zona horaria del servidor (D28).
Fecha = Annotated[datetime, mapped_column(DateTime(timezone=True), server_default=func.now())]


def geometria(tipo: str) -> Geometry:
    """Columna geometry(<tipo>, 4326). Sin índice GiST por ahora: no hay consultas espaciales
    y todas las lecturas son por versión (D28)."""
    return Geometry(geometry_type=tipo, srid=SRID_GUARDADO, spatial_index=False)
