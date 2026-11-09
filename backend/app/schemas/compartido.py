"""Lo que ve el cliente por un enlace (CU15, RF16; prototipo de la p. 51; D70).

Son schemas propios, y nunca los del estudio (`AlternativaOut`, `ProyectoOut`): cada campo está acá
porque el CU15 lo menciona («los datos del proyecto y las alternativas compartidas»; «su trazado sobre
cartografía y sus indicadores principales»). No hay ids, ni versiones, ni estrategia, ni parámetros, ni
observaciones, ni incumplimientos. Del estudio, solo su nombre y quién compartió, con la inicial del
nombre y el rol, como en el prototipo («Compartido por L. Ferreyra, director técnico.»; validado por el
autor, D75). `tests/test_enlaces.py` fija el conjunto exacto de claves: sumar un campo es una decisión,
no un descuido.
"""

from datetime import datetime

from pydantic import BaseModel

from app.schemas.comunes import Feature, FeatureCollection


class ProyectoCompartidoOut(BaseModel):
    nombre: str
    ubicacion: str | None
    # La razón social del cliente: «Propuesta de trazado para …» (p. 51).
    cliente: str
    superficie_terreno_m2: float


class CompartidoPorOut(BaseModel):
    # «L. Ferreyra»: la inicial del nombre y el apellido.
    nombre: str
    # El código del rol (`director_tecnico`, `proyectista`): el portal lo nombra.
    rol: str


class CompartidoOut(BaseModel):
    """CU15, paso 3: los datos del proyecto, las alternativas compartidas (por su código), quién compartió
    y hasta cuándo vale el enlace («Compartido por …», «Enlace vigente hasta el …», p. 51). `estudio` es el
    nombre del estudio (`NOMBRE_ESTUDIO`), o null."""

    estudio: str | None
    proyecto: ProyectoCompartidoOut
    alternativas: list[str]
    compartido_por: CompartidoPorOut
    vence: datetime


class IndicadoresCompartidosOut(BaseModel):
    """Los indicadores principales de la vista del cliente (p. 51). Los porcentajes son los del estudio,
    sobre la superficie disponible (D61)."""

    cantidad_lotes: int
    superficie_media_lote_m2: float | None
    superficie_aprovechable_m2: float
    porcentaje_aprovechamiento: float
    superficie_espacio_verde_m2: float | None
    porcentaje_espacio_verde: float
    longitud_red_m: float
    superficie_terreno_m2: float


class CapasCompartidasOut(BaseModel):
    """El trazado (RF14: celdas, calles, espacios verdes y áreas reservadas), con lo justo para dibujarlo."""

    terreno: Feature
    # Cada acceso con su designación (A1, A2…).
    accesos: FeatureCollection
    # Cada calle con el nombre de su jerarquía.
    calles: FeatureCollection
    manzanas: FeatureCollection
    # Cada celda con su designación y su tipo (lote, espacio verde, espacio libre).
    celdas: FeatureCollection
    # Cada área con su designación y su denominación.
    areas_reservadas: FeatureCollection


class AlternativaCompartidaOut(BaseModel):
    """CU15, paso 5: el trazado de la versión compartida y sus indicadores principales."""

    codigo: str
    # La descripción que tenía la alternativa al compartir (p. 51; D76), o null.
    descripcion: str | None
    indicadores: IndicadoresCompartidosOut
    capas: CapasCompartidasOut
