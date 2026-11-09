"""Del proyecto guardado a lo que recibe el motor (D30, D36).

Es la copia única de esa traducción: la usan la generación (`ServicioGeneracion`), la
validación de los parámetros (CU05) y la estrategia que la pantalla sugiere (p. 43, paso 1).
No depende de otros servicios, así ninguno tiene que importar a la generación para usarla.
"""

import motor_trazados as mt
from motor_trazados import coordenadas
from shapely import Point, Polygon

from app.core.errores import ErrorApi
from app.models import ConjuntoParametros, Proyecto
from app.services.conversiones import centesimos, leida

# Las columnas que pueden ser NULL en un conjunto anterior al motor que las usa (D45): las de la
# 0004 y la 0005, las de la 0006 (D46, D48, D49), las de la 0007 (D50) y la de la 0014 (D86). El resto
# es NOT NULL desde la 0002.
OPCIONALES = (
    "superficie_minima_verde_m2",
    "ancho_minimo_verde_m",
    "ancho_minimo_lote_m",
    "factor_union_maximo",
    "porcentaje_minimo_avenidas",
    "ancho_minimo_avenida_m",
    "ancho_minimo_calle_m",
    "ancho_minimo_calzada_m",
    "porcentaje_incremento_esquina",
    "criterio_espacio_verde",
    "lado_minimo_manzana_m",
    "lado_maximo_manzana_m",
    "lado_maximo_sin_pasaje_m",
    "calle_borde",
)


def armar_solicitud(
    proyecto: Proyecto,
    conjunto: ConjuntoParametros,
    estrategia: mt.Estrategia,
    reservadas: tuple[Polygon, ...] | None = None,
) -> mt.SolicitudGeneracion:
    """La solicitud se arma con lo GUARDADO (numeric del ER → float), no con lo que llegó en
    otro pedido: lo que el motor usa es exactamente lo que queda registrado (RNF05).

    Las áreas reservadas son las del proyecto (`areas_reservadas`), salvo que se pasen otras: el
    recálculo usa las de la versión de origen (`areas_de_version`, D59).

    Sirve también para un proyecto o un conjunto que todavía no se guardaron (el alta y CU05
    validan antes de guardar): solo lee sus atributos.
    """
    terreno, accesos = terreno_y_accesos(proyecto)
    parametros, jerarquias = parametros_del_motor(conjunto)
    return mt.SolicitudGeneracion(
        tipo=mt.TipoProyecto(proyecto.tipo),
        terreno=terreno,
        accesos=accesos,
        parametros=parametros,
        jerarquias=jerarquias,
        estrategia=estrategia,
        reservadas=areas_reservadas(proyecto) if reservadas is None else reservadas,
    )


def terreno_y_accesos(proyecto: Proyecto) -> tuple[Polygon, tuple[Point, ...]]:
    """El terreno y los accesos en metros, en el sistema de cálculo del proyecto. Los accesos
    van en el orden de alta: el motor los nombra A1, A2… por su posición."""
    srid = proyecto.srid_calculo
    terreno = coordenadas.a_metros(leida(proyecto.terreno.geom), srid)
    accesos = tuple(coordenadas.a_metros(leida(a.geom), srid) for a in proyecto.terreno.accesos)
    return terreno, accesos


def areas_reservadas(proyecto: Proyecto) -> tuple[Polygon, ...]:
    """Las áreas reservadas del proyecto en metros, en el orden de alta: el motor las nombra R1, R2…
    por su posición (D59)."""
    return _a_metros([a.geom for a in proyecto.terreno.areas_reservadas], proyecto.srid_calculo)


def areas_de_version(version, srid: int) -> tuple[Polygon, ...]:
    """Las áreas reservadas con las que se generó una versión (su copia), en metros: las del recálculo
    de esa versión, aunque el proyecto haya cambiado las suyas (D59)."""
    return _a_metros([a.geom for a in version.areas_reservadas], srid)


def _a_metros(geometrias, srid: int) -> tuple[Polygon, ...]:
    if not geometrias:
        return ()
    return tuple(coordenadas.a_metros_todas([leida(g) for g in geometrias], srid))


def parametros_del_motor(
    conjunto: ConjuntoParametros,
) -> tuple[mt.ParametrosLoteo, tuple[mt.JerarquiaCorredor, ...]]:
    """Los parámetros del motor, desde lo guardado.

    Un conjunto anterior al motor que usa un parámetro lo tiene en NULL («no aplica», D45). No se
    completa con el valor de referencia: la versión diría que se generó con un valor que nadie
    configuró. Se responde 422 y se pide configurar los parámetros (CU05), que crea una versión
    nueva del conjunto.
    """
    loteo = conjunto.loteo
    faltan = [columna for columna in OPCIONALES if getattr(loteo, columna) is None]
    if faltan:
        raise ErrorApi(
            422,
            f"El conjunto de parámetros v{conjunto.version} es anterior al motor {mt.__version__}: no tiene "
            "valores para los parámetros que ese motor usa.",
            "Configurá los parámetros del proyecto (CU05): se crea una versión nueva del conjunto, con los "
            "valores de referencia propuestos para los que faltan.",
            [(f"loteo.{columna}", "No aplica en este conjunto: hace falta un valor.") for columna in faltan],
        )
    parametros = mt.ParametrosLoteo(
        frente_minimo=float(loteo.frente_minimo_m),
        frente_objetivo=float(loteo.frente_objetivo_m),
        fondo_minimo=float(loteo.fondo_minimo_m),
        superficie_minima=float(loteo.superficie_minima_m2),
        superficie_maxima=float(loteo.superficie_maxima_m2),
        relacion_fondo_frente_max=float(loteo.relacion_fondo_frente_max),
        longitud_maxima_manzana=float(loteo.longitud_maxima_manzana_m),
        # En el ER el porcentaje de verde es del conjunto (común a loteos y playas).
        porcentaje_espacio_verde=float(conjunto.porcentaje_espacio_verde),
        porcentaje_equipamiento=float(loteo.porcentaje_equipamiento),
        superficie_minima_verde=float(loteo.superficie_minima_verde_m2),
        ancho_minimo_verde=float(loteo.ancho_minimo_verde_m),
        ancho_minimo_lote=float(loteo.ancho_minimo_lote_m),
        factor_union_maximo=float(loteo.factor_union_maximo),
        porcentaje_minimo_avenidas=float(loteo.porcentaje_minimo_avenidas),
        ancho_minimo_avenida=float(loteo.ancho_minimo_avenida_m),
        ancho_minimo_calle=float(loteo.ancho_minimo_calle_m),
        ancho_minimo_calzada=float(loteo.ancho_minimo_calzada_m),
        porcentaje_incremento_esquina=float(loteo.porcentaje_incremento_esquina),
        criterio_espacio_verde=mt.CriterioEspacioVerde(loteo.criterio_espacio_verde),
        lado_minimo_manzana=float(loteo.lado_minimo_manzana_m),
        lado_maximo_manzana=float(loteo.lado_maximo_manzana_m),
        lado_maximo_sin_pasaje=float(loteo.lado_maximo_sin_pasaje_m),
        calle_borde=mt.CalleBorde(loteo.calle_borde),
    )
    jerarquias = tuple(
        mt.JerarquiaCorredor(j.nombre, j.orden, float(j.ancho_calzada_m), float(j.ancho_vereda_m), float(j.radio_ochava_m))
        for j in conjunto.jerarquias
    )
    return parametros, jerarquias


def estrategia_sugerida(proyecto: Proyecto) -> mt.Estrategia:
    """La estrategia que la pantalla propone antes de generar (p. 43, paso 1).

    La cuenta es del motor (`MotorGeneracion.sugerir_estrategia`, D42), sobre el terreno en el
    sistema de cálculo. Acá solo se lleva la orientación a las 2 decimales de su columna
    (`numeric(5,2)`), en [0, 180): una orientación con más decimales se rechazaría al generar
    (D30).
    """
    terreno, _ = terreno_y_accesos(proyecto)
    sugerida = mt.MotorGeneracion().sugerir_estrategia(terreno)
    orientacion = float(centesimos(sugerida.orientacion)) % 180
    return mt.Estrategia(sugerida.patron_red, orientacion, sugerida.semilla)
