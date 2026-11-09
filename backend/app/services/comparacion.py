"""Comparar alternativas (CU13, RF15; `Indicadores.compararCon(otros)` del diagrama de la p. 46;
D54, D57).

Dos o tres alternativas del mismo proyecto, cada una con su versión vigente, o dos o tres versiones
(por ejemplo, la v1 y la v2 de la misma alternativa, después de un recálculo):
- por indicador, los valores, la diferencia de cada una contra la primera y cuál es la mejor,
  solo donde la dirección no se discute (`SENTIDOS`);
- los parámetros y los datos de la estrategia en los que difieren, comparados por valor: qué
  decisión produjo la diferencia.

Es de solo lectura (postcondición del CU13: ninguna).
"""

from sqlalchemy.orm import Session

from app.core.errores import ErrorApi
from app.models import Terreno, VersionAlternativa
from app.models.observacion import bloqueantes
from app.schemas.alternativa import DiferenciaIndicadorOut, EstrategiaOut
from app.schemas.comparacion import (
    AlternativaComparadaOut,
    ComparacionOut,
    DiferenciaOut,
    IndicadorComparadoOut,
    Sentido,
)
from app.services import fijacion, parametros, proyectos
from app.services.generacion import indicadores_de, obtener_alternativa

# Cuántas alternativas se comparan a la vez (CU13, paso 3; RF15).
MINIMO, MAXIMO = 2, 3

# Los indicadores de la tabla, en su orden, con hacia dónde es mejor cada uno (D54). Es la copia
# única de «qué indicador tiene una dirección clara».
# - Con dirección: sobre el mismo terreno, más lotes y más superficie útil son mejores, y menos
#   distancia y menos incumplimientos también.
# - Disyuntivas (None): la circulación es el precio de la calle de borde y de las avenidas (la
#   tierra ya la cuenta el aprovechamiento); las avenidas y la cesión tienen un mínimo legal, y
#   pasarlo no es ni mejor ni peor (no llegar ya es un incumplimiento).
# - Las de la p. 51 que se suman en la sesión 10 (D57), también disyuntivas: más verde es más para
#   el barrio y menos lotes; menos red es menos calle que construir y menos acceso; lotes más
#   grandes son menos lotes. El verde va total y computable para la cesión (D55).
SENTIDOS: tuple[tuple[str, Sentido | None], ...] = (
    ("cantidad_celdas", "mayor"),
    ("superficie_aprovechable_m2", "mayor"),
    ("porcentaje_aprovechamiento", "mayor"),
    ("superficie_media_celda_m2", None),
    ("porcentaje_circulacion", None),
    ("longitud_red_m", None),
    ("porcentaje_avenidas", None),
    ("porcentaje_espacio_verde", None),
    ("superficie_verde_computable_m2", None),
    ("porcentaje_cesion", None),
    ("distancia_media_verde_m", "menor"),
    ("distancia_maxima_verde_m", "menor"),
    ("distancia_media_acceso_m", "menor"),
    ("cantidad_incumplimientos", "menor"),
)

# La última fila de la p. 51: no es un indicador de la versión sino del estado de la alternativa (lo que
# impide compartirla, D69), así que va solo cuando se comparan alternativas, no versiones (D84).
BLOQUEANTES = "observaciones_bloqueantes_abiertas"

SUGERENCIA = "Elegí dos o tres alternativas del proyecto."


def comparar(
    db: Session, id_proyecto: int, ids: list[int] | None = None, ids_versiones: list[int] | None = None
) -> ComparacionOut:
    """CU13: la tabla de indicadores y lo que difiere entre dos o tres alternativas del proyecto (la
    versión vigente de cada una), o entre dos o tres versiones (D57).

    404 si no existe el proyecto, una alternativa o una versión; 422 en el campo `alternativas` (o
    `versiones`) si no son dos o tres, si se repite una, si una es de otro proyecto, o si llegan las
    dos cosas o ninguna.
    """
    proyecto = proyectos.obtener(db, id_proyecto)
    if (ids is None) == (ids_versiones is None):
        raise ErrorApi(
            422,
            "Se comparan alternativas o versiones, no las dos cosas a la vez.",
            SUGERENCIA,
            [("alternativas", "Mandá `alternativas` o `versiones`.")],
        )
    campo, pedidos = ("alternativas", ids) if ids is not None else ("versiones", ids_versiones)
    nombre = "alternativa" if campo == "alternativas" else "versión"
    if not MINIMO <= len(pedidos) <= MAXIMO:
        raise ErrorApi(
            422,
            f"Se comparan dos o tres {campo} (CU13).",
            SUGERENCIA,
            [(campo, f"Llegaron {len(pedidos)}.")],
        )
    repetidas = sorted({i for i in pedidos if pedidos.count(i) > 1})
    if repetidas:
        raise ErrorApi(
            422,
            f"Una {nombre} no se compara consigo misma.",
            SUGERENCIA,
            [(campo, f"La {nombre} {i} está repetida.") for i in repetidas],
        )
    if ids is not None:
        versiones = [obtener_alternativa(db, i).version_vigente() for i in pedidos]
    else:
        versiones = [fijacion.obtener_version(db, i) for i in pedidos]
    ajenas = [(i, v) for i, v in zip(pedidos, versiones, strict=True) if v.alternativa.id_proyecto != id_proyecto]
    if ajenas:
        raise ErrorApi(
            422,
            f"Solo se comparan {campo} del mismo proyecto.",
            SUGERENCIA,
            [(campo, f"La {nombre} {i} es de otro proyecto.") for i, _ in ajenas],
        )
    alternativas = [v.alternativa for v in versiones]
    indicadores = [indicadores_de(v, proyecto.terreno) for v in versiones]
    filas = [_fila(campo, sentido, [getattr(i, campo) for i in indicadores]) for campo, sentido in SENTIDOS]
    pendientes = [len(bloqueantes(a)) for a in alternativas]
    if ids is not None:
        filas.append(_fila(BLOQUEANTES, "menor", pendientes))
    return ComparacionOut(
        id_proyecto=id_proyecto,
        alternativas=[
            AlternativaComparadaOut(
                id_alternativa=a.id_alternativa,
                codigo=a.codigo,
                id_version=v.id_version,
                numero=v.numero,
                cumple_restricciones=v.cumple_restricciones,
                version_parametros=v.conjunto.version,
                version_motor=v.version_motor,
                estrategia=EstrategiaOut(
                    patron_red=v.patron_red, orientacion_grados=float(v.orientacion_grados), semilla=v.semilla
                ),
                estado=a.estado,
                bloqueantes_abiertas=p,
                criterio_espacio_verde=None if v.conjunto.loteo is None else v.conjunto.loteo.criterio_espacio_verde,
            )
            for a, v, p in zip(alternativas, versiones, pendientes, strict=True)
        ],
        indicadores=filas,
        diferencias=diferencias([_datos(v) for v in versiones]),
    )


def _fila(campo: str, sentido: Sentido | None, valores: list[int | float | None]) -> IndicadorComparadoOut:
    return IndicadorComparadoOut(
        indicador=campo,
        sentido=sentido,
        valores=valores,
        diferencias=[None] + [_diferencia(v, valores[0]) for v in valores[1:]],
        mejores=mejores(valores, sentido),
    )


def diferencias_entre(origen: VersionAlternativa, version: VersionAlternativa, terreno: Terreno) -> list[DiferenciaIndicadorOut]:
    """La tabla «Diferencias entre versiones» de la p. 50 (CU09, D56): cada indicador en la versión
    de origen y en la nueva, y la diferencia, con los sentidos de la comparación (copia única)."""
    antes, despues = indicadores_de(origen, terreno), indicadores_de(version, terreno)
    return [
        DiferenciaIndicadorOut(
            indicador=campo,
            sentido=sentido,
            origen=getattr(antes, campo),
            nueva=getattr(despues, campo),
            diferencia=_diferencia(getattr(despues, campo), getattr(antes, campo)),
        )
        for campo, sentido in SENTIDOS
    ]


def mejores(valores: list[int | float | None], sentido: Sentido | None) -> list[int]:
    """Los índices con el mejor valor. Una disyuntiva no tiene mejor; un nulo no compite; si todas
    las que compiten empatan, no hay nada que resaltar."""
    if sentido is None:
        return []
    compiten = [(k, v) for k, v in enumerate(valores) if v is not None]
    if not compiten:
        return []
    mejor = (max if sentido == "mayor" else min)(v for _, v in compiten)
    ganadoras = [k for k, v in compiten if v == mejor]
    return [] if len(ganadoras) == len(compiten) else ganadoras


def diferencias(datos: list[dict]) -> list[DiferenciaOut]:
    """Los campos en los que no todas las alternativas tienen el mismo valor, en el orden en que
    aparecen. Uno que falta en una (por ejemplo, otra cantidad de jerarquías) cuenta como nulo."""
    campos = list(dict.fromkeys(campo for d in datos for campo in d))
    resultado = []
    for campo in campos:
        valores = [d.get(campo) for d in datos]
        if any(v != valores[0] for v in valores[1:]):
            resultado.append(DiferenciaOut(campo=campo, valores=valores))
    return resultado


def _datos(version: VersionAlternativa) -> dict:
    """La estrategia, la versión del motor, las áreas reservadas y los parámetros de una versión, como
    un diccionario plano con los nombres de `ParametrosIn` (los de `parametros.fuentes`). Las áreas son
    un dato de entrada, como los parámetros (D59): las de su copia, comparadas por designación,
    denominación y superficie."""
    valores = parametros.valores_de(version.conjunto)
    datos = {
        "estrategia.patron_red": version.patron_red,
        "estrategia.orientacion_grados": float(version.orientacion_grados),
        "estrategia.semilla": version.semilla,
        "version_motor": version.version_motor,
        "areas_reservadas": "; ".join(
            f"{a.designacion} {a.denominacion} ({float(a.superficie_m2):.2f} m²)" for a in version.areas_reservadas
        )
        or None,
    }
    datos |= valores.model_dump(exclude={"loteo", "jerarquias"})
    if valores.loteo is not None:
        datos |= {f"loteo.{campo}": valor for campo, valor in valores.loteo.model_dump().items()}
    for k, jerarquia in enumerate(valores.jerarquias):
        # El ancho total se deriva de la calzada y la vereda (D78), y el uso, del porcentaje de avenidas (D85):
        # no son decisiones aparte.
        datos |= {
            f"jerarquias[{k}].{campo}": valor
            for campo, valor in jerarquia.model_dump(exclude={"ancho_total_m", "en_uso"}).items()
        }
    return datos


def _diferencia(valor: int | float | None, primero: int | float | None) -> int | float | None:
    if valor is None or primero is None:
        return None
    # Los valores tienen dos decimales (numeric(…, 2)): la resta se redondea igual.
    return round(valor - primero, 2)
