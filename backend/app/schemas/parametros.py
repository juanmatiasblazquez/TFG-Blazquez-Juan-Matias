"""Parámetros de un loteo (CU05, pantalla de la p. 49), con los nombres del ER (D29).

La entrada solo aplica los límites de las columnas numeric del ER. Si los valores son
coherentes (positivos, mínimo ≤ máximo, cesiones) lo decide el motor, con
`SolicitudGeneracion.validar()` (D36): no hay una copia de esas reglas acá.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _numeric(digitos: int) -> Any:
    """Un campo numeric(digitos, 2) del ER."""
    return Field(max_digits=digitos, decimal_places=2)


# Criterios de la pantalla de parámetros (p. 49). El motor todavía no los usa (D26).
CriterioPrioritario = Literal["superficie_aprovechable", "cantidad_celdas", "longitud_red"]
# Qué prioriza el asignador de espacios verdes (D46, D51): `motor_trazados.CriterioEspacioVerde`. Es
# un criterio de diseño, no una norma.
CriterioEspacioVerde = Literal["menos_lotes", "cercania"]
# Por dónde va la calle de borde (D50, D86): `motor_trazados.CalleBorde`. Es un criterio de diseño: la
# norma pide el lado menor de la manzana (Ord. 8060, art. 48), no una calle perimetral.
CalleBorde = Literal["contorno", "por_lado"]


class LoteoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frente_minimo_m: Decimal = _numeric(6)
    frente_objetivo_m: Decimal = _numeric(6)
    fondo_minimo_m: Decimal = _numeric(6)
    superficie_minima_m2: Decimal = _numeric(8)
    superficie_maxima_m2: Decimal = _numeric(8)
    relacion_fondo_frente_max: Decimal = _numeric(4)
    longitud_maxima_manzana_m: Decimal = _numeric(7)
    porcentaje_equipamiento: Decimal = _numeric(5)
    # Cuándo un remanente es espacio verde (D41) y el criterio de forma del lote (D43); sin
    # columna en el ER (D29). Un conjunto nuevo los lleva siempre.
    superficie_minima_verde_m2: Decimal = _numeric(8)
    ancho_minimo_verde_m: Decimal = _numeric(6)
    ancho_minimo_lote_m: Decimal = _numeric(6)
    factor_union_maximo: Decimal = _numeric(4)
    # Ley 4146, art. 12 (D48), Ord. 8060, art. 54 (D49) y el criterio del asignador (D46); sin
    # columna en el ER.
    porcentaje_minimo_avenidas: Decimal = _numeric(5)
    ancho_minimo_avenida_m: Decimal = _numeric(5)
    ancho_minimo_calle_m: Decimal = _numeric(5)
    ancho_minimo_calzada_m: Decimal = _numeric(5)
    porcentaje_incremento_esquina: Decimal = _numeric(5)
    criterio_espacio_verde: CriterioEspacioVerde
    # Ord. 8060, art. 48 (D50); sin columna en el ER.
    lado_minimo_manzana_m: Decimal = _numeric(7)
    lado_maximo_manzana_m: Decimal = _numeric(7)
    lado_maximo_sin_pasaje_m: Decimal = _numeric(7)
    # La calle de borde (D86); sin columna en el ER.
    calle_borde: CalleBorde


class JerarquiaIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombre: str = Field(min_length=1, max_length=40)
    # smallint del ER; 1 es la mayor.
    orden: int = Field(ge=-32768, le=32767)
    ancho_calzada_m: Decimal = _numeric(5)
    ancho_vereda_m: Decimal = _numeric(5)
    # Largo de la línea de ochava (D24); el nombre es el del ER.
    radio_ochava_m: Decimal = _numeric(5)
    # Calzada + 2 × vereda: lo calcula el motor (D78). Se admite para que lo leído (`JerarquiaValoresOut`)
    # se pueda volver a mandar tal cual, pero no se guarda ni se usa.
    ancho_total_m: Decimal | None = Field(None, exclude=True, description="Se deriva: si llega, se ignora.")
    # Si el motor la usa (D85): igual que el ancho total, se admite y se ignora.
    en_uso: bool | None = Field(None, exclude=True, description="Se deriva: si llega, se ignora.")


class ParametrosIn(BaseModel):
    """Un conjunto de parámetros de loteo. Al guardarlo pasa a ser la versión vigente."""

    model_config = ConfigDict(extra="forbid")

    criterio_prioritario: CriterioPrioritario
    porcentaje_espacio_verde: Decimal = _numeric(5)
    tolerancia_pct: Decimal = _numeric(5)
    loteo: LoteoIn
    jerarquias: list[JerarquiaIn]


class LoteoOut(BaseModel):
    frente_minimo_m: float
    frente_objetivo_m: float
    fondo_minimo_m: float
    superficie_minima_m2: float
    superficie_maxima_m2: float
    relacion_fondo_frente_max: float
    longitud_maxima_manzana_m: float
    porcentaje_equipamiento: float
    # `None` es «no aplica»: el conjunto es anterior al motor que usa el parámetro (D45).
    superficie_minima_verde_m2: float | None
    ancho_minimo_verde_m: float | None
    ancho_minimo_lote_m: float | None
    factor_union_maximo: float | None
    porcentaje_minimo_avenidas: float | None
    ancho_minimo_avenida_m: float | None
    ancho_minimo_calle_m: float | None
    ancho_minimo_calzada_m: float | None
    porcentaje_incremento_esquina: float | None
    criterio_espacio_verde: str | None
    lado_minimo_manzana_m: float | None
    lado_maximo_manzana_m: float | None
    lado_maximo_sin_pasaje_m: float | None
    calle_borde: str | None


class JerarquiaValoresOut(BaseModel):
    nombre: str
    orden: int
    ancho_calzada_m: float
    ancho_vereda_m: float
    # Largo de la línea de ochava (D24); el nombre es el del ER.
    radio_ochava_m: float
    # Calzada + 2 × vereda, la cuenta del motor (`JerarquiaCorredor.ancho_total`; figura 16, D78). Se
    # deriva: no se guarda ni se manda.
    ancho_total_m: float
    # Si el generador la usa (`motor_trazados.jerarquias_en_uso`, D85): sin avenidas, la mayor no. El portal
    # no muestra la que no se usa. Se deriva, como el ancho total.
    en_uso: bool


class JerarquiaOut(JerarquiaValoresOut):
    id_jerarquia: int


class ValoresParametrosOut(BaseModel):
    """Los valores de un conjunto: misma forma que ParametrosIn."""

    criterio_prioritario: str
    porcentaje_espacio_verde: float
    tolerancia_pct: float
    loteo: LoteoOut | None
    jerarquias: list[JerarquiaValoresOut]


class ParametrosOut(ValoresParametrosOut):
    """Una versión guardada del conjunto de parámetros (p. 49: v1, v2 vigente…)."""

    id_conjunto: int
    version: int
    vigente: bool
    fecha_creacion: datetime
    jerarquias: list[JerarquiaOut]


class ConjuntoParametrosOut(ParametrosOut):
    """Una versión del conjunto de parámetros, en la lista de las versiones (figura 16, «Versiones del
    conjunto»; D82): con las alternativas cuya versión vigente se generó con ella. El ER no guarda quién
    la creó (D29)."""

    usada_por: list[str]


class ReglaCoherenciaOut(BaseModel):
    """Una regla de coherencia de la p. 49 o del motor (`motor_trazados.ReglaCoherencia`, D78)."""

    clave: str
    descripcion: str
    cumple: bool
    detalle: str


class ProblemaParametroOut(BaseModel):
    campo: str
    mensaje: str


class CoherenciaOut(BaseModel):
    """La validación en vivo de un conjunto que todavía no se guardó (figura 16, «Validación de
    coherencia»; D78). `problemas` son los mismos, con los mismos campos, que daría guardarlo; `reglas`
    está vacía mientras algún valor no sea un número válido."""

    reglas: list[ReglaCoherenciaOut]
    problemas: list[ProblemaParametroOut]
    # El ancho total de cada jerarquía con lo que se está editando (calzada + 2 × vereda, la cuenta del
    # motor; D78), en el orden del pedido.
    anchos_totales: list[float]
    # Si el generador usaría cada jerarquía con lo que se está editando (D85), en el orden del pedido.
    jerarquias_en_uso: list[bool]


class FuenteOut(BaseModel):
    """De dónde sale un valor de referencia: el artículo de la norma, o «a validar» (D23).
    `criterio_diseno` marca los que no salen de una norma (D46): el portal no los presenta como
    una exigencia legal."""

    texto: str
    a_validar: bool
    criterio_diseno: bool


class ReferenciaParametrosOut(BaseModel):
    """Valores por defecto de un loteo, servidos desde el motor, con la fuente de cada uno."""

    tipo: str
    valores: ValoresParametrosOut
    # Por campo de ParametrosIn: «loteo.frente_minimo_m», «porcentaje_espacio_verde»,
    # «jerarquias.radio_ochava_m» (vale para todas las jerarquías)…
    fuentes: dict[str, FuenteOut]
