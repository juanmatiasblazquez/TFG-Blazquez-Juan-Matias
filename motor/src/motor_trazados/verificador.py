"""Verificador de restricciones (CU07; p. 47; D26).

Mide todo sobre la geometría del resultado: no confía en el frente y el fondo que trae cada
celda, así un error del subdivisor no pasa desapercibido. Devuelve un incumplimiento por cada
restricción que falla; una alternativa con incumplimientos se devuelve igual, marcada (CU06,
6.a). Una diferencia menor a la tolerancia (1 cm, 0,01 m²) no es un incumplimiento.

Copias únicas que viven acá:
- `incumplimientos_de_lote` (y `es_lote`): las restricciones de un lote. La usa este verificador
  y también el clasificador de remanentes, que decide con ella qué pieza es un lote (D41, D43);
- `frente_minimo_de`: el frente mínimo, con el incremento de esquina (Ord. 8060, art. 54; D49);
- `es_lote_grande`: el lote que pasa la superficie máxima, que no es un incumplimiento (D47);
- `faltante_cesion`: la regla de la cesión, que usa también el asignador (D44), y
  `computa_para_cesion` (con `verde_computable`): qué verde cuenta para ella. Las puntas que no
  alcanzan el lado menor del art. 48 son verde, y computan según el criterio: con «menos lotes» sí,
  con «más cercanía» no (D55, D58);
- `faltante_avenidas` (y `es_avenida`): la proporción de avenidas de la Ley 4146, art. 12, que usa
  también el generador de la red para elegirlas (D48);
- `alcanza_lado_menor`, `lado_mayor_manzana` e `incumplimientos_de_manzana`: los lados de la
  manzana de la Ord. 8060, art. 48. El motor no subdivide la manzana que no alcanza el lado menor
  (D50).
"""

import math
from collections.abc import Sequence

from shapely import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

from .contrato import (
    CeldaGenerada,
    CriterioEspacioVerde,
    Incumplimiento,
    JerarquiaCorredor,
    ParametrosLoteo,
    ResultadoGeneracion,
    TipoCelda,
    TipoIncumplimiento,
)
from .geometria import (
    TOLERANCIA,
    TOLERANCIA_AREA,
    IndiceEjes,
    Medida,
    alcanza_ancho,
    ancho,
    medir,
    poligonos,
    union_cobertura,
)
from .red import RedCirculacion


class VerificadorRestricciones:
    def verificar(
        self,
        resultado: ResultadoGeneracion,
        parametros: ParametrosLoteo,
        accesos: Sequence[Point],
        motivo_cesion: tuple[str, str] | None = None,
        motivo_avenidas: tuple[str, str] | None = None,
    ) -> list[Incumplimiento]:
        """`motivo_cesion` es la causa y la sugerencia que da el asignador cuando no se puede
        llegar a la cesión (D44), y `motivo_avenidas`, las que da el generador de la red cuando no
        se llega a la proporción de avenidas (D48): se suman al detalle del incumplimiento."""
        # La partición está cerrada (D39): la unión de cobertura no vuelve a ajustar vértices.
        corredores = union_cobertura(resultado.corredores)
        ejes = IndiceEjes([tramo.eje for tramo in resultado.red.tramos()])
        lotes = list(resultado.lotes)
        evaluaciones = [
            incumplimientos_de_lote(lote.geometria, medir(lote.geometria, corredores, ejes), parametros)
            for lote in lotes
        ]
        return (
            self._verificar_conectividad(resultado.red, corredores, accesos)
            + self._verificar_anchos_calle(resultado.red, parametros)
            + self._verificar_avenidas(resultado.red, parametros, motivo_avenidas)
            + self._verificar_manzanas(resultado, parametros)
            + self._verificar_frentes(lotes, evaluaciones)
            + self._verificar_dimensiones(lotes, evaluaciones)
            + self._verificar_cesiones(resultado, lotes, parametros, motivo_cesion)
        )

    def _verificar_manzanas(self, resultado: ResultadoGeneracion, p: ParametrosLoteo) -> list[Incumplimiento]:
        """Toda manzana con lotes cumple el art. 48 de la Ord. 8060 (`incumplimientos_de_manzana`,
        D50). Una manzana sin lotes (una punta que quedó como remanente, o una manzana que el
        asignador convirtió entera en verde) no se verifica: no es una manzana de lotes."""
        con_lotes = sorted({lote.indice_manzana for lote in resultado.lotes})
        return [
            _incumplimiento(tipo, resultado.designacion_manzana(indice), detalle, resultado.manzanas[indice - 1])
            for indice in con_lotes
            for tipo, detalle in incumplimientos_de_manzana(resultado.manzanas[indice - 1], p)
        ]

    def _verificar_anchos_calle(self, red: RedCirculacion, p: ParametrosLoteo) -> list[Incumplimiento]:
        """Toda calle mide al menos 12 m, con 6 m de calzada (Ley 4146, art. 12; D48).

        Se verifica sobre la jerarquía de cada tramo: el corredor es un solo polígono del ancho
        total, sin la calzada dibujada aparte. Un incumplimiento por jerarquía, con sus ejes."""
        incumplimientos = []
        por_orden: dict[int, list] = {}
        for tramo in red.tramos():
            por_orden.setdefault(tramo.jerarquia.orden, []).append(tramo)
        for orden in sorted(por_orden):
            tramos = por_orden[orden]
            j = tramos[0].jerarquia
            faltas = []
            if j.ancho_total + TOLERANCIA < p.ancho_minimo_calle:
                faltas.append(f"{_numero(j.ancho_total)} m de ancho < {_numero(p.ancho_minimo_calle)} m")
            if j.ancho_calzada + TOLERANCIA < p.ancho_minimo_calzada:
                faltas.append(f"calzada de {_numero(j.ancho_calzada)} m < {_numero(p.ancho_minimo_calzada)} m")
            if faltas:
                incumplimientos.append(
                    _incumplimiento(
                        TipoIncumplimiento.ANCHO_CALLE,
                        "red",
                        f"«{j.nombre}»: {' y '.join(faltas)} (Ley 4146, art. 12)",
                        MultiLineString([t.eje for t in tramos]),
                    )
                )
        return incumplimientos

    def _verificar_avenidas(
        self, red: RedCirculacion, p: ParametrosLoteo, motivo: tuple[str, str] | None = None
    ) -> list[Incumplimiento]:
        """No menos del porcentaje de la longitud de calles son avenidas (Ley 4146, art. 12;
        `faltante_avenidas`)."""
        if not red.tramos() or not faltante_avenidas(red, p):
            return []
        avenidas = longitud_avenidas(red, p)
        total = red.longitud_total()
        detalle = (
            f"avenidas {_numero(avenidas)} m ({_numero(100 * avenidas / total)} %) < "
            f"{_numero(p.porcentaje_minimo_avenidas)} % de la longitud de calles ({_numero(total)} m)"
        )
        if motivo is not None:
            causa, sugerencia = motivo
            detalle += f". Causa: {causa} Sugerencia: {sugerencia}"
        return [
            _incumplimiento(
                TipoIncumplimiento.PROPORCION_AVENIDAS, "red", detalle, MultiLineString([t.eje for t in red.tramos()])
            )
        ]

    def _verificar_conectividad(
        self, red: RedCirculacion, corredores: BaseGeometry, accesos: Sequence[Point]
    ) -> list[Incumplimiento]:
        """La red es conexa y todos los accesos abren a una de sus calles (p. 10).

        Se mira el grafo y también la superficie de calle que se materializó (D34): un tramo
        cuyo corredor quedó vacío o partido no puede dar por conectado lo que en el terreno no
        lo está. Un acceso está servido si abre a una calle del grafo y toca su superficie.
        """
        if not red.tramos():
            vacia = "La red de circulación está vacía."
            return [_incumplimiento(TipoIncumplimiento.CONECTIVIDAD, "red", vacia, MultiPoint(list(accesos)))]
        incumplimientos = []
        for nodos in red.componentes_aisladas():
            tramos = red.tramos_de(nodos)
            incumplimientos.append(
                _incumplimiento(
                    TipoIncumplimiento.CONECTIVIDAD,
                    "red",
                    f"{len(tramos)} tramo(s) ({_numero(math.fsum(t.longitud for t in tramos))} m) "
                    "no se conectan con el resto de la red.",
                    MultiLineString([t.eje for t in tramos]),
                )
            )
        if not incumplimientos:
            # Con el grafo partido, la superficie también lo está: se informa una sola vez.
            piezas = poligonos(corredores)
            if len(piezas) > 1:
                # La principal es la de mayor superficie; el orden de `poligonos` es estable.
                principal = max(range(len(piezas)), key=lambda i: (round(piezas[i].area, 6), -i))
                aisladas = [pieza for i, pieza in enumerate(piezas) if i != principal]
                incumplimientos.append(
                    _incumplimiento(
                        TipoIncumplimiento.CONECTIVIDAD,
                        "red",
                        f"La superficie de calle quedó partida: {len(aisladas)} parte(s) "
                        f"({_numero(math.fsum(p.area for p in aisladas))} m²) no se conectan con el resto.",
                        MultiPolygon(aisladas),
                    )
                )
        for k, acceso in enumerate(accesos, 1):
            if not (red.servido(acceso) and corredores.distance(acceso) <= TOLERANCIA):
                incumplimientos.append(
                    _incumplimiento(
                        TipoIncumplimiento.CONECTIVIDAD,
                        f"A{k}",
                        f"El acceso A{k} no abre a ninguna calle de la red.",
                        acceso,
                    )
                )
        return incumplimientos

    def _verificar_frentes(self, lotes: list[CeldaGenerada], evaluaciones) -> list[Incumplimiento]:
        """Toda celda útil comparte con un corredor un frente de longitud mínima (p. 10)."""
        return self._de_tipos(lotes, evaluaciones, FRENTES)

    def _verificar_dimensiones(self, lotes: list[CeldaGenerada], evaluaciones) -> list[Incumplimiento]:
        """Fondo, superficie mínima, relación fondo/frente y ancho útil. La superficie máxima no
        es una restricción: un lote grande se informa en los indicadores (D47)."""
        return self._de_tipos(lotes, evaluaciones, DIMENSIONES)

    def _de_tipos(self, lotes, evaluaciones, tipos) -> list[Incumplimiento]:
        return [
            _incumplimiento(tipo, lote.designacion, detalle, lote.geometria)
            for lote, evaluacion in zip(lotes, evaluaciones, strict=True)
            for tipo, detalle in evaluacion
            if tipo in tipos
        ]

    def _verificar_cesiones(
        self,
        resultado: ResultadoGeneracion,
        lotes: list[CeldaGenerada],
        p: ParametrosLoteo,
        motivo: tuple[str, str] | None = None,
    ) -> list[Incumplimiento]:
        """Espacio verde computable ≥ porcentaje de la superficie total de los lotes
        (`faltante_cesion`). Las puntas verdes no computan (`computa_para_cesion`, D55)."""
        base = math.fsum(lote.geometria.area for lote in lotes)
        exigido = exigido_cesion(base, p)
        verde = verde_computable(resultado.celdas, resultado.manzanas, p)
        if not faltante_cesion(verde, base, p):
            return []
        detalle = (
            f"espacio verde computable {_numero(verde)} m² < {_numero(p.porcentaje_espacio_verde)} % de la "
            f"superficie de lotes ({_numero(exigido)} m²)"
        )
        if motivo is not None:
            causa, sugerencia = motivo
            detalle += f". Causa: {causa} Sugerencia: {sugerencia}"
        # El incumplimiento es del terreno entero: su geometría es el borde exterior, sin los
        # anillos interiores que dejaría cualquier hueco entre piezas.
        todo = union_cobertura([*resultado.corredores, *resultado.manzanas])
        contorno = MultiLineString([LineString(parte.exterior.coords) for parte in poligonos(todo)])
        return [
            _incumplimiento(TipoIncumplimiento.CESION_ESPACIO_VERDE, "terreno", detalle, contorno)
        ]


# Las restricciones de un lote, en el orden en que se informan. Las MINIMAS y las de FORMA
# deciden si una pieza es un lote: la que no las cumple es un remanente (D41, D43). Desde el motor
# 0.6.0 la superficie máxima no es una restricción: es el tope de diseño de la unión y de la
# subdivisión, y un lote que la pasa es un lote grande (`es_lote_grande`, D47).
FRENTES = (TipoIncumplimiento.SIN_FRENTE, TipoIncumplimiento.FRENTE_MINIMO)
DIMENSIONES = (
    TipoIncumplimiento.FONDO_MINIMO,
    TipoIncumplimiento.SUPERFICIE_MINIMA,
    TipoIncumplimiento.RELACION_FONDO_FRENTE,
    TipoIncumplimiento.ANCHO_UTIL,
)
MINIMAS = frozenset(
    {
        TipoIncumplimiento.SIN_FRENTE,
        TipoIncumplimiento.FRENTE_MINIMO,
        TipoIncumplimiento.FONDO_MINIMO,
        TipoIncumplimiento.SUPERFICIE_MINIMA,
    }
)
FORMA = frozenset({TipoIncumplimiento.RELACION_FONDO_FRENTE, TipoIncumplimiento.ANCHO_UTIL})
DEFINEN_LOTE = MINIMAS | FORMA


def incumplimientos_de_lote(
    poligono: Polygon, medida: Medida, p: ParametrosLoteo
) -> list[tuple[TipoIncumplimiento, str]]:
    """Las restricciones que no cumple un lote con esta geometría y esta medida, con su detalle
    (p. 10). Una diferencia menor a la tolerancia no cuenta.

    Lo que depende del frente (fondo, relación y ancho útil) solo se mide si la pieza da a una
    calle: sin frente ya no es un lote.
    """
    superficie = poligono.area
    resultado = []
    frente_minimo = frente_minimo_de(medida, p)
    if medida.linea_frente is None:
        resultado.append((TipoIncumplimiento.SIN_FRENTE, "La celda no da a ninguna calle."))
    elif medida.frente + TOLERANCIA < frente_minimo:
        en_esquina = " en esquina" if medida.esquina else ""
        norma = " (Ord. 8060, art. 54)" if medida.esquina and frente_minimo > p.frente_minimo else ""
        resultado.append(
            (
                TipoIncumplimiento.FRENTE_MINIMO,
                f"frente {_numero(medida.frente)} m < mínimo{en_esquina} {_numero(frente_minimo)} m{norma}",
            )
        )
    if medida.linea_frente is not None and medida.fondo + TOLERANCIA < p.fondo_minimo:
        resultado.append(
            (
                TipoIncumplimiento.FONDO_MINIMO,
                f"fondo {_numero(medida.fondo)} m < mínimo {_numero(p.fondo_minimo)} m",
            )
        )
    if superficie + TOLERANCIA_AREA < p.superficie_minima:
        resultado.append(
            (
                TipoIncumplimiento.SUPERFICIE_MINIMA,
                f"superficie {_numero(superficie)} m² < mínima {_numero(p.superficie_minima)} m²",
            )
        )
    if medida.frente > 0 and medida.fondo > p.relacion_fondo_frente_max * medida.frente + TOLERANCIA:
        resultado.append(
            (
                TipoIncumplimiento.RELACION_FONDO_FRENTE,
                f"relación fondo/frente {_numero(medida.fondo / medida.frente)} > máxima "
                f"{_numero(p.relacion_fondo_frente_max)}",
            )
        )
    if medida.linea_frente is not None and not alcanza_ancho(poligono, p.ancho_minimo_lote):
        resultado.append(
            (
                TipoIncumplimiento.ANCHO_UTIL,
                f"ancho útil {_numero(ancho(poligono))} m < mínimo {_numero(p.ancho_minimo_lote)} m",
            )
        )
    return resultado


def frente_minimo_en_esquina(p: ParametrosLoteo) -> float:
    """El frente mínimo de un lote en esquina: el mínimo más su incremento (Ord. 8060, art. 54:
    «Las parcelas esquinas deberán incrementar la medida de su frente mínimo en un 20%»; D49)."""
    return p.frente_minimo * (1 + p.porcentaje_incremento_esquina / 100)


def frente_minimo_de(medida: Medida, p: ParametrosLoteo) -> float:
    """El frente mínimo que le corresponde a un lote con esta medida: el de esquina si tiene
    frente sobre dos calles (`Medida.esquina`). Es la copia única de esta regla: la usan el
    verificador, el clasificador (por `es_lote`) y el subdivisor, que les da ese frente a los lotes
    de las puntas de cada franja (D49)."""
    return frente_minimo_en_esquina(p) if medida.esquina else p.frente_minimo


def es_lote(poligono: Polygon, medida: Medida, p: ParametrosLoteo) -> bool:
    """La pieza es un lote: tiene frente, alcanza el frente, el fondo y la superficie mínimos, y
    cumple el criterio de forma (relación fondo/frente y ancho útil; D41, D43). Puede pasar la
    superficie máxima: entonces es un lote grande (`es_lote_grande`, D47)."""
    return not any(tipo in DEFINEN_LOTE for tipo, _ in incumplimientos_de_lote(poligono, medida, p))


def es_lote_grande(poligono: Polygon, p: ParametrosLoteo) -> bool:
    """El lote pasa la superficie máxima (D47). No es un incumplimiento: un lote grande no es
    ilegal, y la máxima es un criterio de diseño (p. 49). Es la copia única de esta regla:

    - el clasificador no une una fracción a su vecino ni toma como lote una zona si el resultado
      sería grande (D41, D43);
    - el motor intenta subdividir cada lote grande (`MotorGeneracion._subdividir_grandes`);
    - el asignador convierte primero en verde los que no se pudieron subdividir (D46);
    - los indicadores cuentan los que quedan (`cantidad_lotes_grandes`).

    Una diferencia menor a la tolerancia no cuenta."""
    return poligono.area - TOLERANCIA_AREA > p.superficie_maxima


def alcanza_lado_menor(manzana: Polygon, p: ParametrosLoteo) -> bool:
    """La manzana alcanza el lado menor del art. 48 de la Ord. 8060 (42 m; D50).

    El lado menor de una manzana irregular es su **ancho**: el diámetro del mayor círculo que
    entra en ella, la misma medida que el ancho útil del lote y el del verde (`geometria.ancho`,
    D41, D43). En un rectángulo es exactamente el lado menor; en un trapecio o un triángulo, el
    ancho en su parte más ancha, que nunca pasa la distancia entre sus lados. Se decide con la
    erosión (`alcanza_ancho`), con la tolerancia de 1 cm.

    Es la copia única: el motor no subdivide la manzana que no lo alcanza (sus piezas son
    remanentes) y el verificador la marca si tiene lotes."""
    return alcanza_ancho(manzana, p.lado_minimo_manzana)


def computa_para_cesion(celda: CeldaGenerada, manzana: Polygon, p: ParametrosLoteo) -> bool:
    """El verde de esta celda cuenta para la cesión (Ley 4146, art. 7; D55, D58).

    Todo espacio verde computa, salvo, con «más cercanía», el de una manzana que no alcanza el lado
    menor del art. 48 (una punta, D50):
    - con «menos lotes», la punta que califica como verde cuenta: es lo que menos lotes cuesta;
    - con «más cercanía» (el criterio por defecto) no cuenta, y la cesión se completa con verde que
      ubica el asignador cerca de los lotes (D55).
    Así cada criterio hace lo que promete, y la comparación muestra el costo de cada uno (D58).

    Una punta no puede llevar lotes y queda entera como remanente: verde si cumple los criterios
    del verde (D41) y libre si no. Siempre es verde para la distancia de los lotes al verde. Una
    manzana que el asignador convierte entera tenía lotes, así que alcanzó el lado menor y computa.

    Es la copia única de esta regla: la usan el verificador, el asignador y los indicadores."""
    if celda.tipo is not TipoCelda.ESPACIO_VERDE:
        return False
    return p.criterio_espacio_verde is CriterioEspacioVerde.MENOS_LOTES or alcanza_lado_menor(manzana, p)


def computables(celdas: Sequence[CeldaGenerada], manzanas: Sequence[Polygon], p: ParametrosLoteo) -> list[bool]:
    """`computa_para_cesion` de cada celda. `manzanas[k]` es la manzana `k + 1`; el lado menor se
    mide una vez por manzana."""
    alcanza: dict[int, bool] = {}
    resultado = []
    for celda in celdas:
        if celda.tipo is not TipoCelda.ESPACIO_VERDE:
            resultado.append(False)
            continue
        indice = celda.indice_manzana
        if indice not in alcanza:
            alcanza[indice] = computa_para_cesion(celda, manzanas[indice - 1], p)
        resultado.append(alcanza[indice])
    return resultado


def verde_computable(celdas: Sequence[CeldaGenerada], manzanas: Sequence[Polygon], p: ParametrosLoteo) -> float:
    """Los m² de espacio verde que cuentan para la cesión (`computa_para_cesion`, D55)."""
    return math.fsum(c.geometria.area for c, computa in zip(celdas, computables(celdas, manzanas, p)) if computa)


def lado_mayor_manzana(manzana: Polygon) -> float:
    """El lado mayor de una manzana (Ord. 8060, art. 48; D50): el lado largo del rectángulo
    mínimo que la envuelve. En un rectángulo es el lado mayor; en una manzana irregular, el largo
    que hay que recorrer para rodearla."""
    vertices = list(manzana.minimum_rotated_rectangle.exterior.coords)
    return max(math.dist(a, b) for a, b in zip(vertices, vertices[1:]))


def incumplimientos_de_manzana(manzana: Polygon, p: ParametrosLoteo) -> list[tuple[TipoIncumplimiento, str]]:
    """Lo que una manzana con lotes no cumple del art. 48 de la Ord. 8060 (D50): «La dimensión del
    lado menor de cada manzana deberá ser de 42,00 m. como mínimo. La dimensión del lado mayor no
    podrá exceder de 250,00 m. [...] si excediere los 200,00 m, deberá proyectarse un pasaje
    peatonal». El motor no traza pasajes: un lado mayor de más de 200 m es un incumplimiento."""
    resultado = []
    if not alcanza_lado_menor(manzana, p):
        resultado.append(
            (
                TipoIncumplimiento.LADO_MENOR_MANZANA,
                f"lado menor {_numero(ancho(manzana))} m < mínimo {_numero(p.lado_minimo_manzana)} m "
                "(Ord. 8060, art. 48)",
            )
        )
    mayor = lado_mayor_manzana(manzana)
    if mayor > p.lado_maximo_manzana + TOLERANCIA:
        resultado.append(
            (
                TipoIncumplimiento.LADO_MAYOR_MANZANA,
                f"lado mayor {_numero(mayor)} m > máximo {_numero(p.lado_maximo_manzana)} m (Ord. 8060, art. 48)",
            )
        )
    elif mayor > p.lado_maximo_sin_pasaje + TOLERANCIA:
        resultado.append(
            (
                TipoIncumplimiento.LADO_MAYOR_MANZANA,
                f"lado mayor {_numero(mayor)} m > {_numero(p.lado_maximo_sin_pasaje)} m: hace falta un pasaje "
                "peatonal (Ord. 8060, art. 48), y el motor no los traza",
            )
        )
    return resultado


def exigido_cesion(superficie_lotes: float, p: ParametrosLoteo) -> float:
    """El verde que exige la cesión: el porcentaje de la superficie de TODOS los lotes, cumplan
    o no (Ley 4146, art. 7; Ord. 8060, art. 67). La base no es el terreno."""
    return p.porcentaje_espacio_verde / 100 * superficie_lotes


def faltante_cesion(verde: float, superficie_lotes: float, p: ParametrosLoteo) -> float:
    """Los m² de verde que faltan para la cesión; 0 si se cumple. Una diferencia menor a la
    tolerancia no falta."""
    faltante = exigido_cesion(superficie_lotes, p) - verde
    return faltante if faltante > TOLERANCIA_AREA else 0.0


def es_avenida(jerarquia: JerarquiaCorredor, p: ParametrosLoteo) -> bool:
    """Una calle de esta jerarquía es una avenida: mide al menos el ancho de avenida entre
    líneas municipales (Ley 4146, art. 12; D48). Una diferencia menor a la tolerancia no cuenta."""
    return jerarquia.ancho_total + TOLERANCIA >= p.ancho_minimo_avenida


def longitud_avenidas(red: RedCirculacion, p: ParametrosLoteo) -> float:
    return math.fsum(t.longitud for t in red.tramos() if es_avenida(t.jerarquia, p))


def faltante_avenidas(red: RedCirculacion, p: ParametrosLoteo) -> float:
    """Los metros de avenida que faltan para la proporción del art. 12 de la Ley 4146: el
    porcentaje de la longitud de los ejes de todas las calles; 0 si se cumple.

    Es la copia única de esta regla (D48): la usan el generador de la red, que elige las avenidas
    mínimas para llegar, y este verificador."""
    faltante = p.porcentaje_minimo_avenidas / 100 * red.longitud_total() - longitud_avenidas(red, p)
    return faltante if faltante > TOLERANCIA else 0.0


def porcentaje_avenidas(red: RedCirculacion, p: ParametrosLoteo) -> float:
    """La longitud de las avenidas sobre la de toda la red, en %. 0 sin calles."""
    total = red.longitud_total()
    return 100 * longitud_avenidas(red, p) / total if total > 0 else 0.0


def _incumplimiento(tipo, elemento, detalle, geometria) -> Incumplimiento:
    return Incumplimiento(tipo=tipo, elemento=elemento, detalle=detalle, geometria=geometria)


def _numero(valor: float) -> str:
    """Número con dos decimales, coma decimal y punto de miles (RNF01)."""
    return f"{valor:_.2f}".replace(".", ",").replace("_", ".")
