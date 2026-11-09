"""Exportación de una alternativa a GeoJSON, una capa por elemento (RF14).

Las coordenadas salen en EPSG:4326 (longitud, latitud), como exige RFC 7946, con 8 decimales
(cerca de 1 mm). Así cualquier visor (Leaflet, QGIS) las ubica sin configuración. Los números
de los atributos se redondean al centímetro (dos decimales), como en el ER.
"""

import json
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from .contrato import ResultadoGeneracion, SolicitudGeneracion, TipoCelda
from .coordenadas import a_geograficas_todas

DECIMALES_GRADOS = 8


def capas_geojson(solicitud: SolicitudGeneracion, resultado: ResultadoGeneracion, srid: int) -> dict[str, dict]:
    """FeatureCollections por capa: calles, manzanas, lotes, espacios verdes y libres (D41), áreas
    reservadas (D59), incumplimientos y, de apoyo, terreno, ejes y accesos."""
    marcadas: dict[str, list[str]] = {}
    for incumplimiento in resultado.incumplimientos:
        marcadas.setdefault(incumplimiento.elemento, []).append(str(incumplimiento.tipo))
    tramos = resultado.red.tramos()

    def capa(elementos):
        return [(geometria, propiedades) for geometria, propiedades in elementos if not geometria.is_empty]

    def celdas(tipo):
        return (
            (
                celda.geometria,
                {
                    "designacion": celda.designacion,
                    "manzana": f"M{celda.indice_manzana}",
                    "tipo": str(celda.tipo),
                    "frente": _m(celda.frente),
                    "fondo": _m(celda.fondo),
                    "superficie": _m(celda.geometria.area),
                    "cumple": celda.designacion not in marcadas,
                    "motivos": ", ".join(marcadas.get(celda.designacion, [])),
                },
            )
            for celda in resultado.celdas
            if celda.tipo is tipo
        )

    capas = {
        "terreno": capa([(solicitud.terreno, {"superficie": _m(solicitud.terreno.area)})]),
        "accesos": capa(
            (acceso, {"designacion": f"A{k}"}) for k, acceso in enumerate(solicitud.accesos, 1)
        ),
        "ejes": capa(
            (t.eje, {"jerarquia": t.jerarquia.nombre, "orden": t.jerarquia.orden, "longitud": _m(t.longitud)})
            for t in tramos
        ),
        "calles": capa(
            (
                corredor,
                {
                    "jerarquia": t.jerarquia.nombre,
                    "orden": t.jerarquia.orden,
                    "ancho": _m(t.jerarquia.ancho_total),
                    "superficie": _m(corredor.area),
                },
            )
            for t, corredor in zip(tramos, resultado.corredores, strict=True)
        ),
        "manzanas": capa(
            (manzana, {"designacion": f"M{i}", "superficie": _m(manzana.area)})
            for i, manzana in enumerate(resultado.manzanas, 1)
        ),
        "lotes": capa(celdas(TipoCelda.LOTE)),
        "espacios_verdes": capa(celdas(TipoCelda.ESPACIO_VERDE)),
        "espacios_libres": capa(celdas(TipoCelda.ESPACIO_LIBRE)),
        "reservadas": capa(
            (area, {"designacion": f"R{k}", "superficie": _m(area.area)})
            for k, area in enumerate(resultado.reservadas, 1)
        ),
        "incumplimientos": capa(
            (i.geometria, {"tipo": str(i.tipo), "elemento": i.elemento, "detalle": i.detalle})
            for i in resultado.incumplimientos
        ),
    }
    # Todas las geometrías a 4326 con un solo Transformer: de a una, cada capa tardaba segundos.
    geograficas = iter(a_geograficas_todas([g for elementos in capas.values() for g, _ in elementos], srid))
    return {
        nombre: {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": propiedades, "geometry": geojson_geografico(next(geograficas))}
                for _, propiedades in elementos
            ],
        }
        for nombre, elementos in capas.items()
    }


def escribir(capas: dict[str, dict], carpeta: Path) -> list[Path]:
    """Escribe cada capa como `<capa>.geojson` en `carpeta` (UTF-8, LF)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for nombre, coleccion in capas.items():
        ruta = carpeta / f"{nombre}.geojson"
        ruta.write_text(json.dumps(coleccion, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        rutas.append(ruta)
    return rutas


def geojson_geografico(geometria: BaseGeometry) -> dict:
    """Geometría GeoJSON de una geometría que YA está en EPSG:4326, con DECIMALES_GRADOS.

    Es la copia única del redondeo de salida: la usan estas capas y la API, que lee las
    geometrías de la base (guardadas en 4326 con precisión completa).
    """
    redondeada = shapely.transform(geometria, lambda xy: np.round(xy, DECIMALES_GRADOS))
    return json.loads(shapely.to_geojson(redondeada))


def _m(valor: float) -> float:
    return round(float(valor), 2)
