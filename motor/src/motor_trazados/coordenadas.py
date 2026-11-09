"""Conversión entre coordenadas geográficas (EPSG:4326) y el sistema de cálculo (D21).

Es el ÚNICO módulo del motor que importa pyproj (lo ata tests/test_independencia.py): el
núcleo trabaja solo en metros y no sabe nada de coordenadas geográficas. La API llama a este
módulo antes y después de generar: guarda en 4326 (ER) y el motor calcula en metros.

El sistema de cálculo es un dato del proyecto (RF04, `proyecto.srid_calculo`). Por defecto se
sugiere la faja de POSGAR 2007 (Gauss-Krüger) que corresponde a la longitud del terreno: en
la ciudad de Córdoba, la faja 4 (EPSG:5346). Las superficies que resultan son planimétricas
en esa faja; difieren de las elipsoidales en menos de un 0,06 % dentro de la faja.

Los ejes van siempre en orden (x, y) = (longitud, latitud): `always_xy=True`.
"""

import math
from collections.abc import Sequence

import numpy as np
import shapely
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError
from shapely.geometry.base import BaseGeometry

EPSG_GEOGRAFICAS = 4326
# POSGAR 2007 / Argentina 1..7 son EPSG:5343..5349; meridiano central de la faja n: −72 + 3(n−1).
_EPSG_POSGAR2007_FAJA_1 = 5343
FAJAS_POSGAR2007 = range(1, 8)


def faja_posgar2007(longitud: float) -> int:
    """Faja Gauss-Krüger de POSGAR 2007 para una longitud (cada faja abarca ±1,5° de su meridiano).

    En el límite exacto entre dos fajas se elige la del este. Fuera del país se usa la faja
    extrema más cercana.
    """
    faja = math.floor((longitud + 73.5) / 3) + 1
    return min(max(faja, FAJAS_POSGAR2007[0]), FAJAS_POSGAR2007[-1])


def srid_posgar2007(faja: int) -> int:
    if faja not in FAJAS_POSGAR2007:
        raise ValueError(f"Las fajas de POSGAR 2007 van de 1 a 7; se recibió {faja}.")
    return _EPSG_POSGAR2007_FAJA_1 + faja - 1


def faja_del_este(este: float) -> int | None:
    """La faja de POSGAR 2007 de una coordenada este de Gauss-Krüger, o None si no es de ninguna.

    El falso este de la faja n es n × 1.000.000 + 500.000 m (EPSG:5343 a 5349; en la faja 4,
    4.500.000): el millón dice la faja. Lo usa la importación de vértices (D80)."""
    if not math.isfinite(este):
        return None
    faja = math.floor(este / 1_000_000)
    return faja if faja in FAJAS_POSGAR2007 else None


def nombre_sistema(srid: int) -> str:
    """El nombre del sistema de cálculo, para mostrarlo: «POSGAR 2007 / Argentina 4» (D79)."""
    return CRS.from_epsg(validar_srid_calculo(srid)).name


def srid_sugerido(terreno_geografico: BaseGeometry) -> int:
    """Sistema de cálculo por defecto para un terreno en EPSG:4326: la faja de su centroide."""
    return srid_posgar2007(faja_posgar2007(terreno_geografico.centroid.x))


def a_metros(geometria: BaseGeometry, srid: int) -> BaseGeometry:
    """De EPSG:4326 (longitud, latitud) al sistema de cálculo, en metros."""
    return _transformar(geometria, EPSG_GEOGRAFICAS, validar_srid_calculo(srid))


def a_geograficas(geometria: BaseGeometry, srid: int) -> BaseGeometry:
    """Del sistema de cálculo a EPSG:4326 (longitud, latitud)."""
    return _transformar(geometria, validar_srid_calculo(srid), EPSG_GEOGRAFICAS)


def a_geograficas_todas(geometrias: Sequence[BaseGeometry], srid: int) -> list[BaseGeometry]:
    """`a_geograficas` para muchas geometrías, con un solo Transformer.

    Crear un Transformer lleva milisegundos y una alternativa tiene cientos de geometrías: de
    a una, guardar el caso de referencia tardaba segundos. El resultado es el mismo que
    convertirlas de a una.
    """
    lote = np.empty(len(geometrias), dtype=object)
    lote[:] = list(geometrias)
    return list(_transformar(lote, validar_srid_calculo(srid), EPSG_GEOGRAFICAS))


def a_metros_todas(geometrias: Sequence[BaseGeometry], srid: int) -> list[BaseGeometry]:
    """`a_metros` para muchas geometrías, con un solo Transformer: la vuelta de una versión
    guardada al motor, para recalcular (CU09, D56)."""
    lote = np.empty(len(geometrias), dtype=object)
    lote[:] = list(geometrias)
    return list(_transformar(lote, EPSG_GEOGRAFICAS, validar_srid_calculo(srid)))


def validar_srid_calculo(srid: int) -> int:
    """El sistema de cálculo tiene que ser proyectado y en metros: el motor opera en metros.

    Todo rechazo es `ValueError`, también un código que no existe: así la API lo informa
    como un dato inválido (422) sin conocer las excepciones de pyproj.
    """
    try:
        crs = CRS.from_epsg(srid)
    except CRSError as error:
        raise ValueError(f"EPSG:{srid} no es un sistema de coordenadas conocido.") from error
    if not crs.is_projected or any(eje.unit_name not in ("metre", "meter") for eje in crs.axis_info):
        raise ValueError(f"EPSG:{srid} no es un sistema proyectado en metros; no sirve para calcular.")
    return srid


def _transformar(geometria: BaseGeometry, origen: int, destino: int) -> BaseGeometry:
    # Un Transformer por llamada: compartirlo entre los hilos de la API no es seguro.
    transformador = Transformer.from_crs(origen, destino, always_xy=True)

    def convertir(xy: np.ndarray) -> np.ndarray:
        x, y = transformador.transform(xy[:, 0], xy[:, 1], errcheck=True)
        return np.column_stack((x, y))

    return shapely.transform(geometria, convertir)
