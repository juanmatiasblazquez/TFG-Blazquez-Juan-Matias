from datetime import datetime
from decimal import Decimal
from typing import Literal

from motor_trazados import TipoProyecto
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.alternativa import EstrategiaOut, VersionResumen
from app.schemas.cliente import ClienteOut
from app.schemas.comunes import ENTERO_MAX, Feature, FeatureCollection, PoligonoGeoJSON, PuntoGeoJSON, UsuarioResumen
from app.schemas.parametros import ParametrosIn, ParametrosOut


class AccesoIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ubicacion: PuntoGeoJSON = Field(description="Punto sobre el perímetro del terreno.")
    ancho_m: Decimal | None = Field(None, gt=0, max_digits=6, decimal_places=2)
    via_vinculacion: str | None = Field(None, max_length=120, description="Por ejemplo, «Calle pública».")


class AreaReservadaIn(BaseModel):
    """Un área reservada del terreno (CU04, paso 5; ER `area_reservada`; D59): el director técnico
    la dibuja e indica a qué corresponde. El motor la descuenta del dominio y la rodea con una calle.

    `clase` es texto libre: el documento tipa la clase como `ClaseArea` pero no enumera sus valores
    (D29). La validación geométrica (dentro del terreno, sin superponerse, sin tomar un acceso) es la
    del motor (`contrato.validar_reservadas`)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    geometria: PoligonoGeoJSON = Field(description="Polígono en EPSG:4326 (longitud, latitud), dentro del terreno.")
    denominacion: str = Field(
        min_length=1, max_length=120, description="A qué corresponde (CU04, paso 5).", examples=["Servidumbre de electroducto"]
    )
    clase: str | None = Field(None, max_length=20, description="Texto libre: el documento no enumera ClaseArea.")
    destino: str | None = Field(None, max_length=200)


class AreasReservadasIn(BaseModel):
    """Las áreas reservadas del proyecto, enteras: reemplazan a las que tenía (D59). Las versiones ya
    generadas no cambian: cada una guarda la copia de las áreas con las que se generó."""

    model_config = ConfigDict(extra="forbid")

    areas_reservadas: list[AreaReservadaIn] = Field(max_length=50)


class ProyectoIn(BaseModel):
    """Alta de un proyecto con su cliente, su terreno y sus parámetros iniciales (CU03, que
    ejecuta CU04 y CU05). Sin `parametros`, la versión 1 son los valores de referencia (D23)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id_cliente: int = Field(ge=1, le=ENTERO_MAX, description="Cliente que encarga el proyecto (obligatorio, CU03).")
    codigo: str = Field(min_length=1, max_length=20, examples=["LT-2026-014"])
    nombre: str = Field(min_length=1, max_length=120)
    tipo: TipoProyecto = TipoProyecto.LOTEO
    ubicacion: str | None = Field(None, max_length=200)
    jurisdiccion: str | None = Field(None, max_length=120)
    srid_calculo: int | None = Field(
        None,
        ge=1,
        le=ENTERO_MAX,
        description="EPSG del sistema de cálculo, proyectado y en metros. Si falta, la faja POSGAR 2007 "
        "que corresponde a la longitud del terreno (en la ciudad de Córdoba, 5346).",
    )
    terreno: PoligonoGeoJSON = Field(description="Polígono en EPSG:4326 (longitud, latitud).")
    origen: Literal["dibujado", "importado"] = "dibujado"
    accesos: list[AccesoIn] = Field(min_length=1)
    # CU04, paso 5: las áreas reservadas del interior (D59). Se designan R1, R2… en este orden.
    areas_reservadas: list[AreaReservadaIn] = Field(default_factory=list, max_length=50)
    parametros: ParametrosIn | None = None

    @field_validator("tipo")
    @classmethod
    def _solo_loteos(cls, tipo: TipoProyecto) -> TipoProyecto:
        if tipo != TipoProyecto.LOTEO:
            raise ValueError(
                "Por ahora solo se registran proyectos de loteo: la generación de playas de "
                "estacionamiento todavía no está implementada."
            )
        return tipo


class AlternativaResumen(BaseModel):
    id_alternativa: int
    codigo: str
    # generada, observada o seleccionada (D69).
    estado: str
    fecha_creacion: datetime
    # Las observaciones abiertas de todas sus versiones, y cuántas de ellas son bloqueantes: con alguna
    # bloqueante, la alternativa no se puede compartir (CU14, 2.a; D69).
    observaciones_abiertas: int
    bloqueantes_abiertas: int
    # Lo de la versión vigente que muestra la página del proyecto (D73): si cumple las restricciones y
    # cuántas celdas útiles tiene. La descripción para el cliente (D76).
    cumple_restricciones: bool
    cantidad_celdas: int
    descripcion: str | None
    # Sus versiones, de la primera a la vigente: el selector de versiones y la comparación de
    # versiones del portal (CU09, D57).
    versiones: list[VersionResumen]


class ProyectoResumen(BaseModel):
    """Una fila de la lista de proyectos."""

    id_proyecto: int
    codigo: str
    nombre: str
    tipo: str
    cliente: ClienteOut
    estado: str
    superficie_m2: float
    cantidad_alternativas: int
    fecha_creacion: datetime


class ProyectoOut(BaseModel):
    id_proyecto: int
    codigo: str
    nombre: str
    tipo: str
    ubicacion: str | None
    jurisdiccion: str | None
    srid_calculo: int
    estado: str
    fecha_creacion: datetime
    cliente: ClienteOut
    responsable: UsuarioResumen
    terreno: Feature
    accesos: FeatureCollection
    # R1, R2… con su clase, denominación, destino y superficie (D59).
    areas_reservadas: FeatureCollection
    parametros: ParametrosOut | None
    # La estrategia que la pantalla propone antes de generar (p. 43, paso 1; D36).
    estrategia_sugerida: EstrategiaOut
    alternativas: list[AlternativaResumen]
