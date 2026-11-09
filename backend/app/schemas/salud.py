from typing import Literal

from pydantic import BaseModel


# El frontend tiene su espejo en frontend/src/api/salud.ts (tipo Salud): si cambia uno,
# cambia el otro.
class SaludOut(BaseModel):
    estado: Literal["ok", "degradado"]
    base: Literal["ok", "caida"]
    # Versión de la extensión postgis; None si la base no responde o si la migración 0001
    # no corrió.
    postgis: str | None
    # Versión del paquete motor-trazados instalado en el contenedor api.
    motor: str
