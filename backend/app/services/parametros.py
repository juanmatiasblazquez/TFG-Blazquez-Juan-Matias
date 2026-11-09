"""Parámetros de un loteo (CU05; D36): los valores de referencia con su fuente, los conjuntos
que se guardan y su validación.

La coherencia de los valores la decide el motor (`SolicitudGeneracion.validar()`, copia única
de esas reglas): acá se arma la solicitud que recibiría con esos parámetros y se traducen sus
problemas a los nombres del ER.
"""

import re

import motor_trazados as mt
from motor_trazados.valores_referencia import (
    A_VALIDAR,
    CRITERIO_DISENO,
    FUENTES,
    JERARQUIAS_REFERENCIA,
    PARAMETROS_LOTEO_REFERENCIA,
)

from app.core.errores import ErrorApi
from app.models import ConjuntoParametros, JerarquiaCorredor, ParametrosLoteo, Proyecto
from app.schemas.parametros import (
    CoherenciaOut,
    ConjuntoParametrosOut,
    FuenteOut,
    JerarquiaOut,
    JerarquiaValoresOut,
    LoteoOut,
    ParametrosIn,
    ParametrosOut,
    ProblemaParametroOut,
    ReferenciaParametrosOut,
    ReglaCoherenciaOut,
    ValoresParametrosOut,
)
from app.services.conversiones import centesimos
from app.services.solicitud import armar_solicitud, parametros_del_motor

# Valores de la pantalla de parámetros (p. 49) que el motor todavía no usa (D26): no van en
# motor_trazados.valores_referencia, que son los que restringen la generación.
CRITERIO_PRIORITARIO_REFERENCIA = "superficie_aprovechable"
TOLERANCIA_PCT_REFERENCIA = 2.0
FUENTE_SIN_USO_EN_EL_MOTOR = "Pantalla de parámetros (p. 49 del documento). El motor todavía no lo usa (D26)."

# Campo del motor → campo de ParametrosIn, con el nombre del ER (D29). Es la única tabla de
# traducción: la usan las fuentes de los valores de referencia y los problemas de la validación.
CAMPOS_ER = {
    "frente_minimo": "loteo.frente_minimo_m",
    "frente_objetivo": "loteo.frente_objetivo_m",
    "fondo_minimo": "loteo.fondo_minimo_m",
    "superficie_minima": "loteo.superficie_minima_m2",
    "superficie_maxima": "loteo.superficie_maxima_m2",
    "relacion_fondo_frente_max": "loteo.relacion_fondo_frente_max",
    "longitud_maxima_manzana": "loteo.longitud_maxima_manzana_m",
    "porcentaje_espacio_verde": "porcentaje_espacio_verde",
    "porcentaje_equipamiento": "loteo.porcentaje_equipamiento",
    "superficie_minima_verde": "loteo.superficie_minima_verde_m2",
    "ancho_minimo_verde": "loteo.ancho_minimo_verde_m",
    "ancho_minimo_lote": "loteo.ancho_minimo_lote_m",
    "factor_union_maximo": "loteo.factor_union_maximo",
    "porcentaje_minimo_avenidas": "loteo.porcentaje_minimo_avenidas",
    "ancho_minimo_avenida": "loteo.ancho_minimo_avenida_m",
    "ancho_minimo_calle": "loteo.ancho_minimo_calle_m",
    "ancho_minimo_calzada": "loteo.ancho_minimo_calzada_m",
    "porcentaje_incremento_esquina": "loteo.porcentaje_incremento_esquina",
    "criterio_espacio_verde": "loteo.criterio_espacio_verde",
    "lado_minimo_manzana": "loteo.lado_minimo_manzana_m",
    "lado_maximo_manzana": "loteo.lado_maximo_manzana_m",
    "lado_maximo_sin_pasaje": "loteo.lado_maximo_sin_pasaje_m",
    "calle_borde": "loteo.calle_borde",
    # Dentro de cada jerarquía.
    "ancho_calzada": "ancho_calzada_m",
    "ancho_vereda": "ancho_vereda_m",
    "radio_ochava": "radio_ochava_m",
}

# La solicitud que se valida necesita una estrategia, que recién se elige al generar. Esta es
# válida, así que no agrega problemas.
ESTRATEGIA_NEUTRA = mt.Estrategia(mt.PatronRed.GRILLA, 0.0, 0)


def campo_er(campo: str) -> str:
    """'parametros.frente_minimo' → 'loteo.frente_minimo_m'; 'jerarquias[1].radio_ochava' →
    'jerarquias[1].radio_ochava_m'; 'reservadas[0]' → 'areas_reservadas[0]' (el campo del pedido,
    D59). Lo demás queda igual."""
    if campo.startswith("reservadas"):
        return "areas_reservadas" + campo.removeprefix("reservadas")
    if campo.startswith("parametros."):
        return CAMPOS_ER.get(campo.removeprefix("parametros."), campo)
    if coincidencia := re.fullmatch(r"(jerarquias\[\d+\])\.(\w+)", campo):
        return f"{coincidencia[1]}.{CAMPOS_ER.get(coincidencia[2], coincidencia[2])}"
    return campo


def validar(proyecto: Proyecto, conjunto: ConjuntoParametros, prefijo: str = "") -> None:
    """422 si el motor no aceptaría generar con estos parámetros sobre este terreno (CU05, 3.a).

    Se valida el conjunto tal como se guarda (numeric(…, 2)), que es lo que va a usar el motor.
    `prefijo` ubica los campos en el cuerpo del pedido («parametros.» en el alta del proyecto).
    """
    problemas = armar_solicitud(proyecto, conjunto, ESTRATEGIA_NEUTRA).validar()
    if problemas:
        raise ErrorApi(
            422,
            "Los parámetros no son coherentes.",
            "Corregí los valores señalados (CU05, 3.a).",
            [(prefijo + campo_er(problema.campo), problema.mensaje) for problema in problemas],
        )


def coherencia(datos: ParametrosIn) -> CoherenciaOut:
    """`POST /parametros/validacion`: las reglas de coherencia de un conjunto que se está editando, y sus
    problemas por campo, sin guardarlo (figura 16; D78). Las decide el motor
    (`coherencia_de_loteo`), con los mismos valores que se guardarían (numeric(…, 2)); no hace falta un
    terreno, así que sirve también en el paso 3 del alta."""
    parametros, jerarquias = parametros_del_motor(conjunto_desde(datos, version=0))
    problemas, reglas = mt.coherencia_de_loteo(parametros, jerarquias)
    return CoherenciaOut(
        reglas=[
            ReglaCoherenciaOut(clave=r.clave, descripcion=r.descripcion, cumple=r.cumple, detalle=r.detalle)
            for r in reglas
        ],
        problemas=[ProblemaParametroOut(campo=campo_er(p.campo), mensaje=p.mensaje) for p in problemas],
        anchos_totales=[round(j.ancho_total, 2) for j in jerarquias],
        jerarquias_en_uso=list(mt.jerarquias_en_uso(jerarquias, parametros.porcentaje_minimo_avenidas)),
    )


def versiones(proyecto: Proyecto) -> list[ConjuntoParametrosOut]:
    """`GET /proyectos/{id}/parametros`: las versiones del conjunto, de la última a la primera, cada una
    con las alternativas cuya versión vigente se generó con ella (figura 16; D82)."""
    usada_por: dict[int, list[str]] = {}
    for alternativa in proyecto.alternativas:
        usada_por.setdefault(alternativa.version_vigente().id_conjunto, []).append(alternativa.codigo)
    return [
        ConjuntoParametrosOut(
            **presentar_parametros(conjunto).model_dump(),
            usada_por=sorted(usada_por.get(conjunto.id_conjunto, []), key=lambda c: (len(c), c)),
        )
        for conjunto in sorted(proyecto.conjuntos, key=lambda c: c.version, reverse=True)
    ]


def conjunto_de_referencia() -> ConjuntoParametros:
    """Conjunto v1 con los valores de referencia del motor, que citan su fuente normativa (D23)."""
    p = PARAMETROS_LOTEO_REFERENCIA
    return ConjuntoParametros(
        version=1,
        vigente=True,
        criterio_prioritario=CRITERIO_PRIORITARIO_REFERENCIA,
        porcentaje_espacio_verde=centesimos(p.porcentaje_espacio_verde),
        tolerancia_pct=centesimos(TOLERANCIA_PCT_REFERENCIA),
        loteo=ParametrosLoteo(
            frente_minimo_m=centesimos(p.frente_minimo),
            frente_objetivo_m=centesimos(p.frente_objetivo),
            fondo_minimo_m=centesimos(p.fondo_minimo),
            superficie_minima_m2=centesimos(p.superficie_minima),
            superficie_maxima_m2=centesimos(p.superficie_maxima),
            relacion_fondo_frente_max=centesimos(p.relacion_fondo_frente_max),
            longitud_maxima_manzana_m=centesimos(p.longitud_maxima_manzana),
            porcentaje_equipamiento=centesimos(p.porcentaje_equipamiento),
            superficie_minima_verde_m2=centesimos(p.superficie_minima_verde),
            ancho_minimo_verde_m=centesimos(p.ancho_minimo_verde),
            ancho_minimo_lote_m=centesimos(p.ancho_minimo_lote),
            factor_union_maximo=centesimos(p.factor_union_maximo),
            porcentaje_minimo_avenidas=centesimos(p.porcentaje_minimo_avenidas),
            ancho_minimo_avenida_m=centesimos(p.ancho_minimo_avenida),
            ancho_minimo_calle_m=centesimos(p.ancho_minimo_calle),
            ancho_minimo_calzada_m=centesimos(p.ancho_minimo_calzada),
            porcentaje_incremento_esquina=centesimos(p.porcentaje_incremento_esquina),
            criterio_espacio_verde=str(p.criterio_espacio_verde),
            lado_minimo_manzana_m=centesimos(p.lado_minimo_manzana),
            lado_maximo_manzana_m=centesimos(p.lado_maximo_manzana),
            lado_maximo_sin_pasaje_m=centesimos(p.lado_maximo_sin_pasaje),
            calle_borde=str(p.calle_borde),
        ),
        jerarquias=[
            JerarquiaCorredor(
                nombre=j.nombre,
                orden=j.orden,
                ancho_calzada_m=centesimos(j.ancho_calzada),
                ancho_vereda_m=centesimos(j.ancho_vereda),
                radio_ochava_m=centesimos(j.radio_ochava),
            )
            for j in JERARQUIAS_REFERENCIA
        ],
    )


def conjunto_desde(datos: ParametrosIn, version: int) -> ConjuntoParametros:
    """El conjunto que se va a guardar como versión vigente. Los valores ya vienen con hasta 2
    decimales (lo exige ParametrosIn), así que se guardan tal cual."""
    loteo = datos.loteo
    return ConjuntoParametros(
        version=version,
        vigente=True,
        criterio_prioritario=datos.criterio_prioritario,
        porcentaje_espacio_verde=datos.porcentaje_espacio_verde,
        tolerancia_pct=datos.tolerancia_pct,
        loteo=ParametrosLoteo(
            frente_minimo_m=loteo.frente_minimo_m,
            frente_objetivo_m=loteo.frente_objetivo_m,
            fondo_minimo_m=loteo.fondo_minimo_m,
            superficie_minima_m2=loteo.superficie_minima_m2,
            superficie_maxima_m2=loteo.superficie_maxima_m2,
            relacion_fondo_frente_max=loteo.relacion_fondo_frente_max,
            longitud_maxima_manzana_m=loteo.longitud_maxima_manzana_m,
            porcentaje_equipamiento=loteo.porcentaje_equipamiento,
            superficie_minima_verde_m2=loteo.superficie_minima_verde_m2,
            ancho_minimo_verde_m=loteo.ancho_minimo_verde_m,
            ancho_minimo_lote_m=loteo.ancho_minimo_lote_m,
            factor_union_maximo=loteo.factor_union_maximo,
            porcentaje_minimo_avenidas=loteo.porcentaje_minimo_avenidas,
            ancho_minimo_avenida_m=loteo.ancho_minimo_avenida_m,
            ancho_minimo_calle_m=loteo.ancho_minimo_calle_m,
            ancho_minimo_calzada_m=loteo.ancho_minimo_calzada_m,
            porcentaje_incremento_esquina=loteo.porcentaje_incremento_esquina,
            criterio_espacio_verde=loteo.criterio_espacio_verde,
            lado_minimo_manzana_m=loteo.lado_minimo_manzana_m,
            lado_maximo_manzana_m=loteo.lado_maximo_manzana_m,
            lado_maximo_sin_pasaje_m=loteo.lado_maximo_sin_pasaje_m,
            calle_borde=loteo.calle_borde,
        ),
        jerarquias=[
            JerarquiaCorredor(
                nombre=j.nombre,
                orden=j.orden,
                ancho_calzada_m=j.ancho_calzada_m,
                ancho_vereda_m=j.ancho_vereda_m,
                radio_ochava_m=j.radio_ochava_m,
            )
            for j in datos.jerarquias
        ],
    )


def referencia() -> ReferenciaParametrosOut:
    """Los valores por defecto de un loteo y de dónde sale cada uno (D23, D36). Salen del motor:
    el frontend no tiene una copia."""
    return ReferenciaParametrosOut(tipo=str(mt.TipoProyecto.LOTEO), valores=valores_de(conjunto_de_referencia()), fuentes=fuentes())


def fuentes() -> dict[str, FuenteOut]:
    """`FUENTES` del motor, por campo de ParametrosIn. Las de las jerarquías valen para todas."""
    resultado = {}
    for clave, texto in FUENTES.items():
        if clave == "jerarquias.anchos":
            campos = ["jerarquias.ancho_calzada_m", "jerarquias.ancho_vereda_m"]
        elif clave.startswith("jerarquias."):
            campos = [f"jerarquias.{CAMPOS_ER[clave.removeprefix('jerarquias.')]}"]
        else:
            campos = [CAMPOS_ER[clave]]
        a_validar = texto.startswith(A_VALIDAR)
        sin_marca = texto.removeprefix(f"{A_VALIDAR}: ")
        # Un criterio de diseño no sale de una norma (D46): el portal lo marca así.
        criterio_diseno = sin_marca.lower().startswith(CRITERIO_DISENO.lower())
        fuente = FuenteOut(texto=sin_marca, a_validar=a_validar, criterio_diseno=criterio_diseno)
        resultado |= {campo: fuente for campo in campos}
    sin_uso = FuenteOut(texto=FUENTE_SIN_USO_EN_EL_MOTOR, a_validar=False, criterio_diseno=False)
    return resultado | {"criterio_prioritario": sin_uso, "tolerancia_pct": sin_uso}


def presentar_parametros(conjunto: ConjuntoParametros) -> ParametrosOut:
    valores = valores_de(conjunto)
    return ParametrosOut(
        **valores.model_dump(exclude={"jerarquias"}),
        id_conjunto=conjunto.id_conjunto,
        version=conjunto.version,
        vigente=conjunto.vigente,
        fecha_creacion=conjunto.fecha_creacion,
        jerarquias=[
            JerarquiaOut(**valores_jerarquia.model_dump(), id_jerarquia=j.id_jerarquia)
            for valores_jerarquia, j in zip(valores.jerarquias, conjunto.jerarquias, strict=True)
        ],
    )


def valores_de(conjunto: ConjuntoParametros) -> ValoresParametrosOut:
    """Los valores de un conjunto, con los nombres de ParametrosIn. Los usan la lectura de los
    parámetros, los valores de referencia y la comparación de alternativas (D54)."""
    loteo = conjunto.loteo
    # Qué jerarquías usa el generador lo decide el motor (D85). Sin el porcentaje (un conjunto anterior a la
    # 0006) cuenta como que se exigen: el motor de entonces usaba la mayor en las transversales (D24).
    porcentaje_avenidas = None if loteo is None else _opcional(loteo.porcentaje_minimo_avenidas)
    en_uso = mt.jerarquias_en_uso(conjunto.jerarquias, porcentaje_avenidas)
    return ValoresParametrosOut(
        criterio_prioritario=conjunto.criterio_prioritario,
        porcentaje_espacio_verde=float(conjunto.porcentaje_espacio_verde),
        tolerancia_pct=float(conjunto.tolerancia_pct),
        loteo=None
        if loteo is None
        else LoteoOut(
            frente_minimo_m=float(loteo.frente_minimo_m),
            frente_objetivo_m=float(loteo.frente_objetivo_m),
            fondo_minimo_m=float(loteo.fondo_minimo_m),
            superficie_minima_m2=float(loteo.superficie_minima_m2),
            superficie_maxima_m2=float(loteo.superficie_maxima_m2),
            relacion_fondo_frente_max=float(loteo.relacion_fondo_frente_max),
            longitud_maxima_manzana_m=float(loteo.longitud_maxima_manzana_m),
            porcentaje_equipamiento=float(loteo.porcentaje_equipamiento),
            superficie_minima_verde_m2=_opcional(loteo.superficie_minima_verde_m2),
            ancho_minimo_verde_m=_opcional(loteo.ancho_minimo_verde_m),
            ancho_minimo_lote_m=_opcional(loteo.ancho_minimo_lote_m),
            factor_union_maximo=_opcional(loteo.factor_union_maximo),
            porcentaje_minimo_avenidas=_opcional(loteo.porcentaje_minimo_avenidas),
            ancho_minimo_avenida_m=_opcional(loteo.ancho_minimo_avenida_m),
            ancho_minimo_calle_m=_opcional(loteo.ancho_minimo_calle_m),
            ancho_minimo_calzada_m=_opcional(loteo.ancho_minimo_calzada_m),
            porcentaje_incremento_esquina=_opcional(loteo.porcentaje_incremento_esquina),
            criterio_espacio_verde=loteo.criterio_espacio_verde,
            lado_minimo_manzana_m=_opcional(loteo.lado_minimo_manzana_m),
            lado_maximo_manzana_m=_opcional(loteo.lado_maximo_manzana_m),
            lado_maximo_sin_pasaje_m=_opcional(loteo.lado_maximo_sin_pasaje_m),
            calle_borde=loteo.calle_borde,
        ),
        jerarquias=[
            JerarquiaValoresOut(
                nombre=j.nombre,
                orden=j.orden,
                ancho_calzada_m=float(j.ancho_calzada_m),
                ancho_vereda_m=float(j.ancho_vereda_m),
                radio_ochava_m=float(j.radio_ochava_m),
                ancho_total_m=ancho_total(j),
                en_uso=usa,
            )
            for j, usa in zip(conjunto.jerarquias, en_uso, strict=True)
        ],
    )


def ancho_total(jerarquia: JerarquiaCorredor) -> float:
    """Calzada + 2 × vereda: la cuenta es del motor (`JerarquiaCorredor.ancho_total`), no del portal."""
    motor = mt.JerarquiaCorredor(
        jerarquia.nombre,
        jerarquia.orden,
        float(jerarquia.ancho_calzada_m),
        float(jerarquia.ancho_vereda_m),
        float(jerarquia.radio_ochava_m),
    )
    return round(motor.ancho_total, 2)


def _opcional(valor) -> float | None:
    """Un parámetro que puede ser NULL: «no aplica» en un conjunto anterior al motor que lo usa
    (D45)."""
    return None if valor is None else float(valor)
