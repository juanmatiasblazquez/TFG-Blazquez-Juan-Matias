"""Las verificaciones de una versión, restricción por restricción (pantalla de la p. 49; D74).

El motor verifica cada alternativa y guarda solo lo que falla (`incumplimiento`, D26). El prototipo de
la p. 49 muestra además lo que cumple, con su detalle («Todas las celdas tienen al menos 10,00 m de
frente»). Este módulo es la copia única de esa lista: qué restricciones verificó el motor en una
versión, si cada una se cumple y cómo se dice en español. El portal solo la muestra (D37).

- **Qué restricciones aplican:** las de `TipoIncumplimiento`, en el orden del prototipo. Una restricción
  que depende de un parámetro que la versión no tiene (NULL: el motor de esa versión no lo usaba, D45)
  no aplica y no se lista.
- **El detalle:** con los valores del conjunto de parámetros de la versión, no los vigentes, y con los
  indicadores que guardó la versión.
- Un tipo que ya no existe (`superficie_maxima`, anterior al motor 0.6.0, D47) se lista igual si la
  versión lo tiene, con su nombre.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

import motor_trazados as mt

from app.models import VersionAlternativa
from app.models.parametros import ConjuntoParametros, ParametrosLoteo
from app.schemas.alternativa import IndicadoresOut, VerificacionOut
from app.services import proyectos


def texto(valor: Decimal | float) -> str:
    """Un número como lo escribe el portal (`formato.numero`): coma decimal, punto de miles y dos decimales."""
    return f"{float(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


@dataclass(frozen=True)
class _Restriccion:
    tipo: str
    nombre: str
    # El parámetro del que depende (si es NULL en la versión, no aplica); None si aplica siempre.
    parametro: str | None
    # Qué dice cuando cumple, con los parámetros y los indicadores de la versión.
    cumple: Callable[["_Contexto"], str]
    # Qué tienen los elementos que no cumplen: «menos de 10,00 m de frente». None: se usa el detalle
    # del primer incumplimiento, que escribió el motor.
    falta: Callable[["_Contexto"], str] | None = None
    # Si los elementos son lotes (M3-L07) o manzanas (M3).
    de_lotes: bool = True


@dataclass(frozen=True)
class _Contexto:
    loteo: ParametrosLoteo
    conjunto: ConjuntoParametros
    indicadores: IndicadoresOut
    accesos: list[str]


def _lista(cosas: list[str]) -> str:
    """«M1», «M1 y M3», «M1, M2 y M3»."""
    return cosas[0] if len(cosas) == 1 else f"{', '.join(cosas[:-1])} y {cosas[-1]}"


def _accesos(c: _Contexto) -> str:
    if not c.accesos:
        return "La red es conexa"
    if len(c.accesos) == 1:
        return f"Red conexa que incluye el acceso {c.accesos[0]}"
    return f"Red conexa que incluye los accesos {_lista(c.accesos)}"


def _frente(c: _Contexto) -> str:
    frase = f"Todos los lotes tienen al menos {texto(c.loteo.frente_minimo_m)} m de frente"
    incremento = c.loteo.porcentaje_incremento_esquina
    if incremento:
        esquina = c.loteo.frente_minimo_m * (1 + incremento / 100)
        frase += f" ({texto(esquina)} m en esquina)"
    return frase


def _cesion(c: _Contexto) -> str:
    exigido = texto(c.conjunto.porcentaje_espacio_verde)
    if c.indicadores.porcentaje_cesion is None:
        return f"Se alcanza el {exigido} % de la superficie de los lotes"
    return f"{texto(c.indicadores.porcentaje_cesion)} % ≥ {exigido} % requerido"


def _avenidas(c: _Contexto) -> str:
    # La casilla «Exigir avenidas» desmarcada (D85): que se vea que el conjunto se aparta de la norma.
    if not mt.exige_avenidas(float(c.loteo.porcentaje_minimo_avenidas)):
        return "No se exigen avenidas: todas las calles son locales. El conjunto se aparta de la Ley 4146, art. 12"
    exigido = texto(c.loteo.porcentaje_minimo_avenidas)
    if c.indicadores.porcentaje_avenidas is None:
        return f"Al menos el {exigido} % de la red son avenidas"
    return f"{texto(c.indicadores.porcentaje_avenidas)} % de la red ≥ {exigido} % requerido"


RESTRICCIONES: tuple[_Restriccion, ...] = (
    _Restriccion("conectividad", "Conectividad", None, _accesos, de_lotes=False),
    _Restriccion(
        "sin_frente", "Frente a una calle", None, lambda c: "Todos los lotes dan a una calle", lambda c: "sin frente a una calle"
    ),
    _Restriccion(
        "frente_minimo",
        "Frente mínimo",
        None,
        _frente,
        lambda c: f"menos de {texto(c.loteo.frente_minimo_m)} m de frente",
    ),
    _Restriccion(
        "fondo_minimo",
        "Fondo mínimo",
        None,
        lambda c: f"Todos los lotes tienen al menos {texto(c.loteo.fondo_minimo_m)} m de fondo",
        lambda c: f"menos de {texto(c.loteo.fondo_minimo_m)} m de fondo",
    ),
    _Restriccion(
        "superficie_minima",
        "Superficie mínima",
        None,
        lambda c: f"Todos los lotes tienen al menos {texto(c.loteo.superficie_minima_m2)} m²",
        lambda c: f"menos de {texto(c.loteo.superficie_minima_m2)} m²",
    ),
    _Restriccion(
        "relacion_fondo_frente",
        "Relación fondo/frente",
        None,
        lambda c: f"Ningún lote tiene más de {texto(c.loteo.relacion_fondo_frente_max)} m de fondo por metro de frente",
        lambda c: f"más de {texto(c.loteo.relacion_fondo_frente_max)} m de fondo por metro de frente",
    ),
    _Restriccion(
        "ancho_util",
        "Ancho útil",
        "ancho_minimo_lote_m",
        lambda c: f"Todos los lotes tienen al menos {texto(c.loteo.ancho_minimo_lote_m)} m de ancho útil",
        lambda c: f"menos de {texto(c.loteo.ancho_minimo_lote_m)} m de ancho útil",
    ),
    _Restriccion("cesion_espacio_verde", "Cesión para espacio verde", None, _cesion, de_lotes=False),
    _Restriccion(
        "ancho_calle",
        "Ancho de calle",
        "ancho_minimo_calle_m",
        lambda c: (
            f"Todas las calles miden al menos {texto(c.loteo.ancho_minimo_calle_m)} m, "
            f"con {texto(c.loteo.ancho_minimo_calzada_m)} m de calzada"
        ),
        de_lotes=False,
    ),
    _Restriccion("proporcion_avenidas", "Proporción de avenidas", "porcentaje_minimo_avenidas", _avenidas, de_lotes=False),
    _Restriccion(
        "lado_menor_manzana",
        "Lado menor de manzana",
        "lado_minimo_manzana_m",
        lambda c: f"Todas las manzanas con lotes miden al menos {texto(c.loteo.lado_minimo_manzana_m)} m de ancho",
        lambda c: f"menos de {texto(c.loteo.lado_minimo_manzana_m)} m de ancho",
        de_lotes=False,
    ),
    _Restriccion(
        "lado_mayor_manzana",
        "Lado mayor de manzana",
        "lado_maximo_manzana_m",
        lambda c: (
            f"Ninguna manzana pasa de {texto(c.loteo.lado_maximo_manzana_m)} m de largo "
            f"({texto(c.loteo.lado_maximo_sin_pasaje_m)} m sin pasaje)"
        ),
        lambda c: f"más de {texto(c.loteo.lado_maximo_sin_pasaje_m)} m de largo",
        de_lotes=False,
    ),
)

# Un tipo que el motor ya no marca, para nombrarlo en las versiones que lo tienen (D47).
NOMBRES_ANTERIORES = {"superficie_maxima": "Superficie máxima"}


def _manzana(elemento: str) -> str:
    """La manzana de un lote («M3-L07» → «M3»), o el elemento tal cual."""
    return elemento.split("-", 1)[0]


def _con_orden(designaciones: set[str]) -> list[str]:
    return sorted(designaciones, key=lambda d: (len(d), d))


def _falla(r: _Restriccion, c: _Contexto, incumplimientos: list) -> str:
    n = len(incumplimientos)
    if r.falta is None:
        primero = incumplimientos[0].detalle
        return primero if n == 1 else f"{primero} (y {n - 1} más)"
    if r.de_lotes:
        manzanas = _con_orden({_manzana(i.elemento) for i in incumplimientos})
        sujeto = "1 lote con" if n == 1 else f"{n} lotes con"
        donde = "en la manzana" if len(manzanas) == 1 else "en las manzanas"
        return f"{sujeto} {r.falta(c)}, {donde} {_lista(manzanas)}"
    elementos = _con_orden({i.elemento for i in incumplimientos})
    sujeto = "1 manzana con" if n == 1 else f"{n} manzanas con"
    return f"{sujeto} {r.falta(c)}: {_lista(elementos)}"


def verificaciones_de(version: VersionAlternativa, indicadores: IndicadoresOut) -> list[VerificacionOut]:
    """Las restricciones que verificó el motor en esta versión, en el orden de la p. 49."""
    conjunto = version.conjunto
    loteo = conjunto.loteo
    por_tipo: dict[str, list] = {}
    for incumplimiento in version.incumplimientos:
        por_tipo.setdefault(incumplimiento.tipo, []).append(incumplimiento)
    contexto = _Contexto(
        loteo=loteo,
        conjunto=conjunto,
        indicadores=indicadores,
        accesos=[d for d, _ in proyectos.designaciones_de_accesos(version.alternativa.proyecto)],
    )
    resultado = []
    for r in RESTRICCIONES:
        if r.parametro is not None and getattr(loteo, r.parametro) is None:
            continue
        fallas = por_tipo.pop(r.tipo, [])
        resultado.append(
            VerificacionOut(
                tipo=r.tipo,
                nombre=r.nombre,
                cumple=not fallas,
                cantidad=len(fallas),
                detalle=_falla(r, contexto, fallas) if fallas else r.cumple(contexto),
            )
        )
    # Lo que quede es de un tipo que ya no existe: se lista con su nombre.
    for tipo, fallas in sorted(por_tipo.items()):
        resultado.append(
            VerificacionOut(
                tipo=tipo,
                nombre=NOMBRES_ANTERIORES.get(tipo, tipo),
                cumple=False,
                cantidad=len(fallas),
                detalle=fallas[0].detalle if len(fallas) == 1 else f"{fallas[0].detalle} (y {len(fallas) - 1} más)",
            )
        )
    return resultado

