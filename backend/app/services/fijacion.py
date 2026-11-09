"""Fijar sectores (CU09; secuencia de la p. 44; D56): de una versión guardada a lo que el motor
conserva al recalcular.

- `resultado_de_version` pasa la versión de la base al sistema de cálculo, como un
  `ResultadoGeneracion` del motor (la red con sus jerarquías, un corredor por tramo, las manzanas
  con su designación y las celdas).
- `armar_fijados` es el `armarFijados(version, ids)` de la p. 47: la regla de qué se fija vive en el
  motor (`MotorGeneracion.fijar`); acá solo se leen la versión y las manzanas pedidas.
- `manzanas_en_contorno` resuelve el contorno dibujado: las manzanas que quedan enteras adentro.
- `vista_previa` es el paso 3 del CU09: lo que se fijaría, con sus indicadores y la estrategia que se
  sugiere para recalcular (la de la versión, D60), sin guardar nada.
"""

import json
import math

import motor_trazados as mt
from geoalchemy2.shape import to_shape
from motor_trazados import coordenadas
from motor_trazados.exportar import geojson_geografico
from motor_trazados.red import RedCirculacion
from shapely import MultiPoint, Polygon
from shapely.geometry import shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorApi
from app.models import Manzana, VersionAlternativa
from app.schemas.alternativa import EstrategiaOut
from app.schemas.recalculo import SectorIn, SectorOut
from app.services.solicitud import areas_de_version

SUGERENCIA_SECTOR = "Elegí manzanas de la versión: un clic en un lote elige su manzana, o dibujá un contorno."


def obtener_version(db: Session, id_version: int) -> VersionAlternativa:
    version = db.get(VersionAlternativa, id_version)
    if version is None:
        raise ErrorApi(404, f"No existe la versión {id_version}.")
    return version


def orientacion_marco(version: VersionAlternativa) -> float:
    """La orientación del marco de la alternativa: la de su versión 1, donde se cerró la partición de
    lo que se conserva (D56)."""
    return float(version.alternativa.versiones[0].orientacion_grados)


def resultado_de_version(version: VersionAlternativa, srid: int) -> mt.ResultadoGeneracion:
    """La versión guardada, en el sistema de cálculo y con los tipos del motor."""
    jerarquias = {
        j.id_jerarquia: mt.JerarquiaCorredor(
            nombre=j.nombre,
            orden=j.orden,
            ancho_calzada=float(j.ancho_calzada_m),
            ancho_vereda=float(j.ancho_vereda_m),
            radio_ochava=float(j.radio_ochava_m),
        )
        for j in version.conjunto.jerarquias
    }
    tramos = version.tramos
    ejes = coordenadas.a_metros_todas([to_shape(t.eje) for t in tramos], srid)
    calles = coordenadas.a_metros_todas(
        [to_shape(t.geom) if t.geom is not None else Polygon() for t in tramos], srid
    )
    red = RedCirculacion()
    corredor_de = {}
    for tramo, eje, calle in zip(tramos, ejes, calles, strict=True):
        agregado = red.agregar_tramo(eje.coords[0], eje.coords[-1], eje, jerarquias[tramo.id_jerarquia])
        if agregado is not None:
            corredor_de[(agregado.origen, agregado.destino)] = calle
    manzanas = version.manzanas
    posicion = {m.id_manzana: k for k, m in enumerate(manzanas, 1)}
    geometrias = coordenadas.a_metros_todas([to_shape(m.geom) for m in manzanas], srid)
    celdas = version.celdas
    celdas_m = coordenadas.a_metros_todas([to_shape(c.geom) for c in celdas], srid)
    return mt.ResultadoGeneracion(
        red=red,
        corredores=tuple(corredor_de[(t.origen, t.destino)] for t in red.tramos()),
        manzanas=tuple(geometrias),
        celdas=tuple(
            mt.CeldaGenerada(
                geometria=g,
                tipo=mt.TipoCelda(c.tipo),
                frente=float(c.frente_m),
                fondo=float(c.fondo_m),
                indice_manzana=posicion[c.id_manzana],
                designacion=c.designacion,
            )
            for c, g in zip(celdas, celdas_m, strict=True)
        ),
        designaciones=tuple(m.designacion for m in manzanas),
    )


def armar_fijados(motor: mt.MotorGeneracion, version: VersionAlternativa, manzanas: list[str]) -> mt.ElementosFijados:
    """`armarFijados(version, ids)` (p. 47): las manzanas pedidas con sus celdas y sus calles, el
    sector y los anclajes (`MotorGeneracion.fijar`). 422 si no se eligió ninguna o alguna no existe."""
    srid = version.alternativa.proyecto.srid_calculo
    try:
        return motor.fijar(resultado_de_version(version, srid), manzanas, orientacion_marco(version))
    except mt.SolicitudInvalida as error:
        raise ErrorApi(
            422,
            "No se puede fijar ese sector.",
            SUGERENCIA_SECTOR,
            [(problema.campo, problema.mensaje) for problema in error.problemas],
        ) from error


def manzanas_en_contorno(db: Session, version: VersionAlternativa, contorno: dict) -> list[str]:
    """Las manzanas de la versión que quedan enteras dentro del contorno dibujado, en su orden. Lo
    resuelve PostGIS en EPSG:4326: el portal no lleva reglas del dominio (D37)."""
    poligono = func.ST_SetSRID(func.ST_GeomFromGeoJSON(_json(contorno)), 4326)
    return list(
        db.scalars(
            select(Manzana.designacion)
            .where(Manzana.id_version == version.id_version, func.ST_CoveredBy(Manzana.geom, poligono))
            .order_by(Manzana.id_manzana)
        )
    )


def elegidas(db: Session, version: VersionAlternativa, entrada: SectorIn) -> list[str]:
    """Las manzanas de un clic más las del contorno, sin repetir, en el orden de la versión."""
    pedidas = set(entrada.manzanas)
    if entrada.contorno is not None:
        pedidas |= set(manzanas_en_contorno(db, version, entrada.contorno.model_dump()))
    orden = [m.designacion for m in version.manzanas]
    conocidas = [d for d in orden if d in pedidas]
    # Las desconocidas van al final: el motor las rechaza con su nombre.
    return conocidas + sorted(pedidas - set(orden))


def vista_previa(db: Session, id_version: int, entrada: SectorIn) -> SectorOut:
    """El paso 3 del CU09: lo que se fijaría, resaltado, con sus indicadores. No guarda nada.

    422 si no hay ninguna manzana, si alguna no existe, o si lo fijado abarca todo el terreno
    (3.a)."""
    version = obtener_version(db, id_version)
    proyecto = version.alternativa.proyecto
    srid = proyecto.srid_calculo
    motor = mt.MotorGeneracion()
    manzanas = elegidas(db, version, entrada)
    fijados = armar_fijados(motor, version, manzanas)
    terreno = coordenadas.a_metros(to_shape(proyecto.terreno.geom), srid)
    areas = areas_de_version(version, srid)
    try:
        motor.exigir_dominio_restante(terreno, fijados, areas)
    except mt.SinDominioRestante as error:
        raise ErrorApi(422, error.causa, error.sugerencia) from error
    designaciones = {m.designacion for m in fijados.manzanas}
    filas = [c for c in version.celdas if c.manzana is not None and c.manzana.designacion in designaciones]
    lotes = [c for c in filas if c.tipo == str(mt.TipoCelda.LOTE)]
    verde = math.fsum(c.geometria.area for c in fijados.celdas if c.tipo is mt.TipoCelda.ESPACIO_VERDE)
    sector, anclajes = coordenadas.a_geograficas_todas([fijados.sector, MultiPoint(list(fijados.anclajes))], srid)
    return SectorOut(
        id_version=version.id_version,
        manzanas=[m.designacion for m in fijados.manzanas],
        sector=geojson_geografico(sector),
        anclajes=geojson_geografico(anclajes),
        cantidad_anclajes=len(fijados.anclajes),
        superficie_m2=round(fijados.sector.area, 2),
        # Sobre la superficie disponible, el terreno menos las áreas de la versión (D61).
        porcentaje_disponible=round(100 * fijados.sector.area / (terreno.area - math.fsum(a.area for a in areas)), 2),
        cantidad_celdas=len(filas),
        cantidad_lotes=len(lotes),
        cantidad_celdas_utiles=sum(1 for c in lotes if c.cumple),
        superficie_espacio_verde_m2=round(verde, 2),
        # La de la versión de origen (D60): la grilla nueva sigue a la fijada.
        estrategia_sugerida=EstrategiaOut(
            patron_red=version.patron_red,
            orientacion_grados=float(version.orientacion_grados),
            semilla=version.semilla,
        ),
    )


def _json(geometria: dict) -> str:
    return json.dumps(shape(geometria).__geo_interface__)
