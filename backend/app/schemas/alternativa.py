from datetime import datetime
from decimal import Decimal
from typing import Literal

from motor_trazados import PatronRed
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.comunes import ENTERO_MAX, FeatureCollection, UsuarioResumen

# Hacia dónde es mejor un indicador. `None` es una disyuntiva: se muestra la diferencia sin
# resaltar un mejor (D54).
Sentido = Literal["mayor", "menor"]


class EstrategiaIn(BaseModel):
    """Estrategia confirmada por el proyectista (secuencia de la p. 43, paso 3).

    Los límites son los de las columnas del ER: lo que se guarda es exactamente lo que usó el
    motor, así la versión se puede reproducir (RNF05).
    """

    model_config = ConfigDict(extra="forbid")

    patron_red: PatronRed
    orientacion_grados: Decimal = Field(
        ge=0,
        lt=360,
        max_digits=5,
        decimal_places=2,
        description="Ángulo de las calles longitudinales, antihorario desde el este de cuadrícula del "
        "sistema de cálculo. Hasta 2 decimales (numeric(5,2)).",
        examples=[20.0],
    )
    semilla: int = Field(ge=0, le=ENTERO_MAX, examples=[1042])


class GeneracionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estrategia: EstrategiaIn


class EstrategiaOut(BaseModel):
    patron_red: str
    orientacion_grados: float
    semilla: int


class IndicadoresOut(BaseModel):
    """Indicadores de la versión (CU08), con los nombres del ER."""

    # Celdas útiles: lotes sin incumplimientos (RF11, D26).
    cantidad_celdas: int
    superficie_aprovechable_m2: float
    # Sin columna en el ER: se derivan de lo guardado, igual que los calcula el motor (D29).
    porcentaje_aprovechamiento: float
    cantidad_fracciones_no_conformes: int
    # Todos los incumplimientos de la versión (lotes, cesión, art. 12, art. 48…): la tabla de la
    # comparación (CU13, D54).
    cantidad_incumplimientos: int
    porcentaje_circulacion: float
    porcentaje_espacio_verde: float
    longitud_red_m: float
    distancia_media_acceso_m: float | None
    # Remanentes (D41), sin columna en el ER (D29). Nulos en las versiones anteriores al motor
    # 0.4.0. `superficie_espacio_verde_m2` es todo el verde y `superficie_verde_computable_m2` el que
    # cuenta para la cesión, sin las puntas del art. 48 (D55; nulo antes del motor 0.8.0). La
    # cesión alcanzada es el verde computable sobre la superficie de todos los lotes.
    superficie_espacio_verde_m2: float | None
    superficie_verde_computable_m2: float | None
    superficie_espacio_libre_m2: float | None
    porcentaje_cesion: float | None
    # Los lotes que pasan la superficie máxima (D47) y el % de la red que es avenida (Ley 4146,
    # art. 12; D48). `None` en una versión anterior al motor 0.6.0: «no aplica».
    cantidad_lotes_grandes: int | None
    porcentaje_avenidas: float | None
    # La distancia media y la máxima de los lotes al verde más cercano, por la red (D51). `None` en
    # una versión anterior al motor 0.7.0 («no aplica»), o sin lotes o sin verde.
    distancia_media_verde_m: float | None
    distancia_maxima_verde_m: float | None
    # La superficie aprovechable sobre las celdas útiles (p. 51), derivada como el aprovechamiento.
    # `None` sin celdas útiles.
    superficie_media_celda_m2: float | None
    # La de las áreas reservadas con las que se generó (D59), derivada de su copia: 0 sin áreas. La
    # disponible es el terreno menos las áreas: lo que se lotea.
    superficie_reservada_m2: float
    superficie_disponible_m2: float
    # Sobre qué superficie son los porcentajes del aprovechamiento, la circulación y el verde (D61):
    # «disponible» desde el motor 0.10.0; «terreno» en las versiones anteriores, que se guardaron así
    # (con o sin áreas; sin áreas las dos son lo mismo). La cesión es sobre los lotes, siempre.
    base_porcentajes: Literal["disponible", "terreno"]


class DiferenciaIndicadorOut(BaseModel):
    """Una fila de «Diferencias entre versiones» (p. 50; CU09, D56): el indicador en la versión de
    origen y en esta, y la diferencia (esta menos la de origen). `sentido` es el de la comparación
    (`comparacion.SENTIDOS`, D54)."""

    indicador: str
    sentido: Sentido | None
    origen: int | float | None
    nueva: int | float | None
    diferencia: int | float | None


class VerificacionOut(BaseModel):
    """Una restricción que verificó el motor en la versión, cumpla o no (pantalla de la p. 49;
    `services.verificaciones`, D74). `cantidad` es la de sus incumplimientos; `detalle`, lo que dice el
    portal: «Todos los lotes tienen al menos 10,00 m de frente» o «3 lotes con menos de 250,00 m², en
    las manzanas M1 y M3»."""

    tipo: str
    nombre: str
    cumple: bool
    cantidad: int
    detalle: str


class FijacionOut(BaseModel):
    """Qué se conservó de la versión de origen en un recálculo (CU09, p. 50; D56), leído de la base.

    `sector` es `geom_fijada`. Donde la red fijada se une a la nueva (D60):
    - `cantidad_anclajes`: los de la vista previa (`SectorOut.cantidad_anclajes`), los nodos de la red
      fijada donde una calle fijada seguía hacia lo que se recalcula;
    - `cantidad_anclajes_unidos`: los de esos anclajes a los que llegó una calle nueva;
    - `cantidad_empalmes`: los nodos nuevos donde una calle nueva desemboca en el costado de una
      fijada, que se parte ahí. Dependen de la grilla nueva: no existen antes de recalcular.
    """

    id_version_origen: int
    numero_origen: int
    manzanas: list[str]
    cantidad_celdas: int
    cantidad_lotes: int
    superficie_m2: float
    cantidad_anclajes: int
    cantidad_anclajes_unidos: int
    cantidad_empalmes: int
    sector: dict


class CapasOut(BaseModel):
    """Una FeatureCollection por capa (RF14), en EPSG:4326."""

    ejes: FeatureCollection
    calles: FeatureCollection
    nodos: FeatureCollection
    manzanas: FeatureCollection
    celdas: FeatureCollection
    incumplimientos: FeatureCollection
    # Las áreas reservadas con las que se generó la versión (su copia, D59): R1, R2…
    areas_reservadas: FeatureCollection


# Generada, recalculada o copia: `models.alternativa.TipoVersion` (D62).
TipoVersionOut = Literal["generada", "recalculada", "copia"]


class VersionOut(BaseModel):
    id_version: int
    numero: int
    id_version_origen: int | None
    id_conjunto: int
    version_parametros: int
    estrategia: EstrategiaOut
    generada_por: UsuarioResumen
    fecha_generacion: datetime
    duracion_ms: int
    version_motor: str
    cumple_restricciones: bool
    indicadores: IndicadoresOut
    capas: CapasOut
    # Solo en una versión que sale de un recálculo (CU09): lo fijado y la tabla de la p. 50.
    fijacion: FijacionOut | None = None
    diferencias_con_origen: list[DiferenciaIndicadorOut] | None = None
    # Cómo nació (D62): «generada» (la v1), «recalculada» (CU09: con fijación y diferencias) o «copia»
    # (volver a una versión anterior, D60: sin fijación ni diferencias, es igual a su origen).
    tipo: TipoVersionOut
    # Las restricciones que verificó el motor, con ✓ o ✗ y su detalle (p. 49; D74).
    verificaciones: list[VerificacionOut]
    # Las observaciones cuya respuesta con un recálculo creó esta versión: «Responde a O-1» (p. 50;
    # CU12, 3.a; D74).
    responde_a: list[str]


class VersionResumen(BaseModel):
    id_version: int
    numero: int
    id_version_origen: int | None
    fecha_generacion: datetime
    tipo: TipoVersionOut


class AlternativaOut(BaseModel):
    id_alternativa: int
    id_proyecto: int
    codigo: str
    estado: str
    fecha_creacion: datetime
    # Lo que el estudio le cuenta al cliente de este trazado (p. 51; D76), o null.
    descripcion: str | None
    versiones: list[VersionResumen]
    # La versión vigente (la de mayor número), o la pedida en `GET /versiones/{id}`.
    version: VersionOut


class DescripcionIn(BaseModel):
    """La descripción de la alternativa para el cliente (p. 51; D76). Vacía o null la borra. Se copia en el
    enlace al compartir: cambiarla después no cambia lo que ya ve el cliente."""

    model_config = ConfigDict(extra="forbid")

    descripcion: str | None = Field(max_length=2000)
