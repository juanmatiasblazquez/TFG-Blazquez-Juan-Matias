"""Observaciones y respuestas (CU11, CU12, RF17; pantalla de la p. 50; D69)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.alternativa import EstrategiaIn
from app.schemas.comunes import PoligonoGeoJSON, UsuarioResumen
from app.schemas.recalculo import Designacion

# Los valores del documento (`app.models.observacion`): el tipo y la criticidad del acta (Anexo 1.5).
TipoIn = Literal["normativa", "dimensional", "conectividad", "comercial", "grafica"]
CriticidadIn = Literal["bloqueante", "sugerida"]
AccionIn = Literal["recalculo_parcial", "justificacion", "aclaracion"]


class ObservacionIn(BaseModel):
    """CU11, paso 3: los datos de la observación y, si se dibujó, el sector afectado."""

    model_config = ConfigDict(extra="forbid")

    tipo: TipoIn
    criticidad: CriticidadIn
    descripcion: str = Field(min_length=1, max_length=4000)
    sector: PoligonoGeoJSON | None = Field(None, description="Polígono en EPSG:4326 (longitud, latitud).")


class SectorIn(BaseModel):
    """El sector que se está dibujando en una observación (CU11, paso 3)."""

    model_config = ConfigDict(extra="forbid")

    sector: PoligonoGeoJSON = Field(description="Polígono en EPSG:4326 (longitud, latitud).")


class SectorMedidoOut(BaseModel):
    """La vista previa del sector de una observación (figura 19; D79): su superficie y, si sale del
    terreno, cuánto y dónde (CU11, 3.a), antes de registrarla. `problema` es el mismo mensaje que daría
    registrarla; None si el sector sirve."""

    superficie_m2: float | None
    afuera_m2: float
    # GeoJSON (EPSG:4326) de la parte de afuera, para marcarla en el mapa.
    afuera: dict | None
    problema: str | None


class RecalculoRespuestaIn(BaseModel):
    """El recálculo de la respuesta (CU12, 3.a, que ejecuta el CU09): sobre la versión vigente, que se
    nombra para no recalcular sobre una pantalla desactualizada."""

    model_config = ConfigDict(extra="forbid")

    id_version: int
    estrategia: EstrategiaIn
    manzanas: list[Designacion] = Field(max_length=500, examples=[["M6", "M7"]])


class RespuestaIn(BaseModel):
    """CU12, pasos 3 y 4: la acción y el comentario. Con `recalculo_parcial`, el recálculo."""

    model_config = ConfigDict(extra="forbid")

    accion: AccionIn
    descripcion: str = Field(min_length=1, max_length=4000)
    recalculo: RecalculoRespuestaIn | None = None


class EstadoObservacionIn(BaseModel):
    """Cerrar una observación respondida (`cerrar()`, p. 46: la conformidad del emisor) o reabrirla
    (`reabrir()`)."""

    model_config = ConfigDict(extra="forbid")

    estado: Literal["cerrada", "abierta"]


class RespuestaOut(BaseModel):
    id_respuesta: int
    accion: str
    descripcion: str
    usuario: UsuarioResumen
    fecha: datetime
    # La versión que resultó del recálculo (CU12, paso 5), con su número; nulas sin recálculo.
    id_version_resultante: int | None
    numero_version_resultante: int | None


class ObservacionOut(BaseModel):
    id_observacion: int
    # O-1, O-2… por alternativa, en el orden en que se registraron (p. 50).
    designacion: str
    id_version: int
    numero_version: int
    tipo: str
    criticidad: str
    descripcion: str
    # El sector afectado en GeoJSON (EPSG:4326), o null.
    sector: dict | None
    estado: str
    emisor: UsuarioResumen
    fecha_emision: datetime
    fecha_cierre: datetime | None
    respuestas: list[RespuestaOut]
