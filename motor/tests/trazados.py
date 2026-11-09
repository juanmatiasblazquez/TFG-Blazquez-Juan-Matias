"""Trazados armados a mano, para probar el verificador y los indicadores sin pasar por el motor.

Una calle local de 12 m (eje de (0, 0) a (120, 0), corredor de y = −6 a y = 6) con los lotes
al norte, desde y = 6. Al sur, un espacio verde de 120 × 30 m, que es una celda más (D41). El
acceso A1 está en el extremo oeste del eje.
"""

from dataclasses import replace

from shapely import Point, Polygon, box

from motor_trazados import CeldaGenerada, JerarquiaCorredor, ResultadoGeneracion, TipoCelda
from motor_trazados.red import RedCirculacion
from motor_trazados.valores_referencia import PARAMETROS_LOTEO_REFERENCIA

# Los trazados tienen una sola calle local y una manzana de una fila de lotes de 30 m de fondo:
# para aislar las demás restricciones, sus parámetros no piden avenidas ni el lado menor de 42 m.
# La proporción del art. 12 de la Ley 4146 (D48) y el art. 48 de la Ord. 8060 (D50) se prueban
# con sus propios trazados.
P_TRAZADOS = replace(PARAMETROS_LOTEO_REFERENCIA, porcentaje_minimo_avenidas=0.0, lado_minimo_manzana=30.0)

LOCAL = JerarquiaCorredor("Local", 2, ancho_calzada=7.0, ancho_vereda=2.5, radio_ochava=4.0)
COLECTORA = JerarquiaCorredor("Colectora", 1, ancho_calzada=12.0, ancho_vereda=4.0, radio_ochava=6.0)
CORREDOR = box(0, -6, 120, 6)
VERDE = box(0, -36, 120, -6)
ACCESO = Point(0, 0)


def red_simple() -> RedCirculacion:
    red = RedCirculacion()
    red.agregar_tramo((0, 0), (120, 0), None, LOCAL)
    return red


def lote(geometria: Polygon, numero: int = 1, *, frente: float = 0.0, fondo: float = 0.0) -> CeldaGenerada:
    return CeldaGenerada(geometria, TipoCelda.LOTE, frente, fondo, 1, f"M1-L{numero:02d}")


def verde(geometria: Polygon, numero: int = 1) -> CeldaGenerada:
    return CeldaGenerada(geometria, TipoCelda.ESPACIO_VERDE, 0.0, 0.0, 1, f"M1-EV{numero:02d}")


def libre(geometria: Polygon, numero: int = 1) -> CeldaGenerada:
    return CeldaGenerada(geometria, TipoCelda.ESPACIO_LIBRE, 0.0, 0.0, 1, f"M1-EL{numero:02d}")


def lote_frente_a_la_calle(x: float, ancho: float, fondo: float, numero: int = 1) -> CeldaGenerada:
    return lote(box(x, 6, x + ancho, 6 + fondo), numero)


def trazado(
    celdas, *, red: RedCirculacion | None = None, verdes=(VERDE,), corredores=(CORREDOR,)
) -> ResultadoGeneracion:
    red = red or red_simple()
    return ResultadoGeneracion(
        red=red,
        corredores=tuple(corredores),
        manzanas=(box(0, 6, 120, 36),),
        celdas=(*celdas, *(verde(g, k) for k, g in enumerate(verdes, 1))),
    )
