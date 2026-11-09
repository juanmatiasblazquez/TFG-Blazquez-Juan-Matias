"""El terreno del alta antes de registrarlo (CU04; figura 15): su medición y la importación de sus vértices.

- **La medición (D79):** la superficie, el perímetro, los vértices y los lados de lo dibujado, en el sistema
  de cálculo, y las reglas de la geometría con las del motor (`contrato.validar_terreno`, `validar_accesos`
  y `validar_reservadas`): las mismas que aplica el alta. El portal no mide ni valida nada (D37).
- **La importación (D80):** el texto de una planilla de vértices, en POSGAR 2007 (como las planillas de
  mensura del Anexo 1.2) o en latitud y longitud, al polígono en EPSG:4326 con la precisión completa.
"""

import csv
import math
import unicodedata

from motor_trazados import coordenadas
from motor_trazados.contrato import validar_accesos, validar_reservadas, validar_terreno
from shapely import Point, Polygon
from shapely.geometry.base import BaseGeometry

from app.core.errores import ErrorApi
from app.schemas.comunes import PoligonoGeoJSON
from app.schemas.errores import ProblemaOut
from app.schemas.terrenos import (
    AreaMedidaOut,
    ImportacionIn,
    ImportacionOut,
    LadoOut,
    MedicionIn,
    MedicionOut,
    ReglaGeometriaOut,
    VerticeOut,
)
from app.services import parametros
from app.services.conversiones import centesimos
from app.services.verificaciones import texto


def sistema_de_calculo(srid_calculo: int | None, terreno_4326: BaseGeometry) -> int:
    """El sistema de cálculo del proyecto: el elegido o, si falta, la faja POSGAR 2007 del terreno (RF04).
    422 si no es un sistema proyectado en metros. Lo usan el alta, la medición y la importación."""
    srid = srid_calculo if srid_calculo is not None else coordenadas.srid_sugerido(terreno_4326)
    try:
        return coordenadas.validar_srid_calculo(srid)
    except ValueError as error:
        raise ErrorApi(
            422,
            "El sistema de coordenadas de cálculo no sirve.",
            "Dejá el campo vacío para usar la faja POSGAR 2007 que corresponde al terreno.",
            [("srid_calculo", str(error))],
        ) from error


# --- Medición (D79) -----------------------------------------------------------------------------------


def medir(datos: MedicionIn) -> MedicionOut:
    """`POST /terrenos/medicion`: lo dibujado en el paso 2 del alta, medido y validado en el sistema de
    cálculo. Siempre 200 (salvo un sistema que no sirve): lo que está mal va en `reglas` y `problemas`, con
    el campo del pedido del alta, mientras se dibuja."""
    terreno_4326 = datos.terreno.a_shapely()
    srid = sistema_de_calculo(datos.srid_calculo, terreno_4326)
    terreno = coordenadas.a_metros(terreno_4326, srid)
    accesos = _a_metros([acceso.a_shapely() for acceso in datos.accesos], srid)
    areas = _a_metros([area.a_shapely() for area in datos.areas_reservadas], srid)

    del_terreno = validar_terreno(terreno)
    de_accesos = validar_accesos(accesos, terreno)
    # Las áreas se miden contra un terreno válido; los accesos se cruzan con ellas solo si están bien.
    de_areas = [] if del_terreno else validar_reservadas(areas, terreno, () if de_accesos else accesos)

    # V1, V2… en el orden del dibujo; el lado k va de Vk a Vk+1, y el último cierra en V1.
    posiciones = datos.terreno.coordinates[0][:-1]
    cantidad = len(posiciones)
    esquinas = list(terreno.exterior.coords)[:-1]
    lados = [(esquinas[k], esquinas[(k + 1) % cantidad]) for k in range(cantidad)]
    medios = _a_geograficas([Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in lados], srid)
    reglas = [
        ReglaGeometriaOut(
            clave="poligono",
            descripcion="Polígono simple y cerrado",
            cumple=not del_terreno,
            detalle=_detalle(del_terreno, f"{cantidad} vértices, sin cruces"),
        ),
        ReglaGeometriaOut(
            clave="accesos",
            descripcion=f"Accesos sobre el perímetro ({len(accesos)})",
            cumple=not de_accesos,
            detalle=_detalle(de_accesos, "Todos sobre el borde del terreno"),
        ),
    ]
    if areas and not del_terreno:
        reglas.append(
            ReglaGeometriaOut(
                clave="areas",
                descripcion="Área reservada contenida en el terreno"
                if len(areas) == 1
                else "Áreas reservadas contenidas en el terreno",
                cumple=not de_areas,
                detalle=_detalle(de_areas, "Dentro del polígono, sin superponerse ni tomar un acceso"),
            )
        )
    return MedicionOut(
        srid_calculo=srid,
        sistema=coordenadas.nombre_sistema(srid),
        # Redondeadas como las guarda el alta (numeric(…, 2)).
        superficie_m2=None if del_terreno else float(centesimos(terreno.area)),
        perimetro_m=None if del_terreno else float(centesimos(terreno.length)),
        vertices=[VerticeOut(designacion=f"V{k + 1}", posicion=list(posiciones[k])) for k in range(cantidad)],
        lados=[
            LadoOut(
                desde=f"V{k + 1}",
                hasta=f"V{(k + 1) % cantidad + 1}",
                largo_m=round(math.dist(*lados[k]), 2),
                punto_medio=[medios[k].x, medios[k].y],
            )
            for k in range(cantidad)
        ],
        areas=[
            AreaMedidaOut(designacion=f"R{k + 1}", superficie_m2=round(area.area, 2) if area.is_valid else None)
            for k, area in enumerate(areas)
        ],
        reglas=reglas,
        problemas=[
            ProblemaOut(campo=parametros.campo_er(problema.campo), mensaje=problema.mensaje)
            for problema in del_terreno + de_accesos + de_areas
        ],
    )


def _detalle(problemas, si_cumple: str) -> str:
    return " ".join(problema.mensaje for problema in problemas) if problemas else si_cumple


def _a_metros(geometrias: list[BaseGeometry], srid: int) -> list[BaseGeometry]:
    return coordenadas.a_metros_todas(geometrias, srid) if geometrias else []


def _a_geograficas(geometrias: list[BaseGeometry], srid: int) -> list[BaseGeometry]:
    return coordenadas.a_geograficas_todas(geometrias, srid) if geometrias else []


# --- Importación de vértices (D80) --------------------------------------------------------------------

MAXIMO_VERTICES = 1000
# Las columnas que se leen, sin tildes ni mayúsculas («Vértice» es «vertice»).
POSGAR = ("este", "norte")
GEOGRAFICAS = ("latitud", "longitud")
VERTICE = "vertice"
# Cuántos problemas se informan, como mucho: el resto se cuenta.
PROBLEMAS_INFORMADOS = 20
FORMATO = (
    "Una cabecera «este;norte» (POSGAR 2007, en metros) o «latitud;longitud» (en grados decimales), con "
    "«vertice» opcional, y un vértice por línea. El separador es «;», «,» o el tabulador; con «;» o el "
    "tabulador, la coma decimal."
)


class _Planilla(Exception):
    """Un problema de la planilla, con su línea."""


def importar(datos: ImportacionIn) -> ImportacionOut:
    """`POST /terrenos/importacion`: el polígono de una planilla de vértices (D80). En POSGAR 2007, la faja
    sale del este (el millón: 4.xxx.xxx es la faja 4) y tiene que coincidir con el sistema de cálculo, si se
    eligió uno. El polígono se valida con la regla del motor. 422 con los problemas por línea en
    `contenido`."""
    lineas = [
        (numero, linea.strip())
        for numero, linea in enumerate(datos.contenido.lstrip("﻿").splitlines(), start=1)
        if linea.strip() and not linea.strip().startswith("#")
    ]
    if not lineas:
        raise _error(["La planilla no tiene datos: solo líneas vacías o comentarios."])
    try:
        separador, columnas = _cabecera(*lineas[0])
    except _Planilla as problema:
        raise _error([str(problema)]) from None
    formato = "posgar" if POSGAR[0] in columnas else "geograficas"

    problemas: list[str] = []
    puntos: list[tuple[int, float, float]] = []
    for numero, linea in lineas[1:]:
        try:
            puntos.append((numero, *_vertice(numero, linea, separador, columnas, formato)))
        except _Planilla as problema:
            problemas.append(str(problema))
    if problemas:
        raise _error(problemas)
    # El cierre repetido es opcional.
    if len(puntos) > 1 and puntos[0][1:] == puntos[-1][1:]:
        puntos.pop()
    if len(puntos) < 3:
        raise _error([f"Hay {len(puntos)} vértice(s): un polígono necesita al menos 3."])
    if len(puntos) > MAXIMO_VERTICES:
        raise _error([f"Hay {len(puntos)} vértices: el máximo es {MAXIMO_VERTICES}."])

    if formato == "posgar":
        srid = _srid_de_la_faja(puntos, datos.srid_calculo)
        metros = Polygon([(x, y) for _, x, y in puntos])
        terreno_4326 = coordenadas.a_geograficas(metros, srid) if metros.is_valid else None
        sistema = coordenadas.nombre_sistema(srid)
    else:
        terreno_4326 = Polygon([(x, y) for _, x, y in puntos])
        srid = sistema_de_calculo(datos.srid_calculo, terreno_4326)
        metros = coordenadas.a_metros(terreno_4326, srid)
        sistema = "Latitud y longitud (WGS 84)"
    problemas = [problema.mensaje for problema in validar_terreno(metros)]
    if problemas or terreno_4326 is None:
        raise _error(problemas)
    return ImportacionOut(
        terreno=PoligonoGeoJSON(type="Polygon", coordinates=[[list(xy) for xy in terreno_4326.exterior.coords]]),
        formato=formato,
        sistema=sistema,
        srid_calculo=srid,
        cantidad_vertices=len(puntos),
    )


def _cabecera(numero: int, linea: str) -> tuple[str, tuple[str, ...]]:
    separador = next((s for s in ("\t", ";", ",") if s in linea), None)
    if separador is None:
        raise _Planilla(
            f"Línea {numero}: la primera línea es la cabecera, con las columnas separadas por «;», «,» o el "
            "tabulador."
        )
    columnas = tuple(_columna(nombre) for nombre in next(csv.reader([linea], delimiter=separador)))
    for esperadas in (POSGAR, GEOGRAFICAS):
        if sorted(columnas) in (sorted(esperadas), sorted((VERTICE, *esperadas))):
            return separador, columnas
    raise _Planilla(
        f"Línea {numero}: la cabecera tiene las columnas {', '.join(f'«{c}»' for c in columnas)}; se esperan "
        "«este» y «norte», o «latitud» y «longitud», con «vertice» opcional."
    )


def _columna(nombre: str) -> str:
    sin_tildes = unicodedata.normalize("NFD", nombre.strip().lower())
    return "".join(letra for letra in sin_tildes if not unicodedata.combining(letra))


def _vertice(
    numero: int, linea: str, separador: str, columnas: tuple[str, ...], formato: str
) -> tuple[float, float]:
    campos = next(csv.reader([linea], delimiter=separador))
    if len(campos) != len(columnas):
        raise _Planilla(f"Línea {numero}: tiene {len(campos)} valores y la cabecera, {len(columnas)} columnas.")
    valores = {
        columna: _numero(numero, columna, campo, separador)
        for columna, campo in zip(columnas, campos, strict=True)
        if columna != VERTICE
    }
    if formato == "posgar":
        este, norte = valores["este"], valores["norte"]
        if coordenadas.faja_del_este(este) is None:
            raise _Planilla(
                f"Línea {numero}: el este {texto(este)} no es de ninguna faja de POSGAR 2007 (el millón es la "
                "faja: en Córdoba, 4.xxx.xxx). ¿Están invertidas las columnas?"
            )
        return este, norte
    latitud, longitud = valores["latitud"], valores["longitud"]
    if not -90 <= latitud <= 90:
        raise _Planilla(f"Línea {numero}: la latitud {texto(latitud)} está fuera de −90 a 90.")
    if not -180 <= longitud <= 180:
        raise _Planilla(f"Línea {numero}: la longitud {texto(longitud)} está fuera de −180 a 180.")
    return longitud, latitud


def _numero(numero: int, columna: str, campo: str, separador: str) -> float:
    valor = campo.strip()
    # Con «;» o el tabulador, la coma decimal; sin separador de miles.
    if separador != "," and "," in valor and "." not in valor:
        valor = valor.replace(",", ".")
    try:
        resultado = float(valor)
    except ValueError:
        resultado = math.nan
    if not math.isfinite(resultado):
        raise _Planilla(
            f"Línea {numero}: «{campo.strip()}» no es un número en la columna «{columna}» (sin separador de "
            "miles; la coma decimal, solo con «;» o el tabulador)."
        )
    return resultado


def _srid_de_la_faja(puntos: list[tuple[int, float, float]], srid_calculo: int | None) -> int:
    fajas = sorted({coordenadas.faja_del_este(x) for _, x, _ in puntos})
    if len(fajas) > 1:
        raise _error([f"Los vértices son de distintas fajas de POSGAR 2007 ({', '.join(map(str, fajas))})."])
    srid = coordenadas.srid_posgar2007(fajas[0])
    if srid_calculo is not None and srid_calculo != srid:
        raise _error(
            [
                f"Las coordenadas son de la faja {fajas[0]} (EPSG:{srid}) y el sistema de cálculo elegido es "
                f"EPSG:{srid_calculo}. Elegí el de la faja de la planilla, o dejalo vacío."
            ]
        )
    return srid


def _error(problemas: list[str]) -> ErrorApi:
    informados = problemas[:PROBLEMAS_INFORMADOS]
    if len(problemas) > PROBLEMAS_INFORMADOS:
        informados.append(f"Y {len(problemas) - PROBLEMAS_INFORMADOS} problema(s) más.")
    return ErrorApi(
        422,
        "La planilla de vértices no se pudo importar.",
        f"Corregí lo señalado. El formato: {FORMATO}",
        [("contenido", problema) for problema in informados],
    )
