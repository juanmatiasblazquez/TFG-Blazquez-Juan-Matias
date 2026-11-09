"""Casos de referencia del motor: loteos en grilla sobre terrenos de distintas formas en Córdoba.

Sirven para mirar el resultado en QGIS, como terrenos de la prueba de rendimiento (RNF03, D27)
y como terrenos de la verificación del portal:

    docker compose run --rm motor python -m motor_trazados.referencia             # el rectangular
    docker compose run --rm motor python -m motor_trazados.referencia --caso l    # uno por nombre
    docker compose run --rm motor python -m motor_trazados.referencia --todos     # todos

Cada caso escribe en `salida/<caso>/` (en el host, `motor/salida/<caso>/`) un GeoJSON por capa
en EPSG:4326 y `indicadores.json`. Las ubicaciones son ilustrativas: los terrenos no
corresponden a ninguna parcela real.

- `referencia`: el rectángulo de 480 × 270 m de las sesiones anteriores (D27).
- `irregular`: el segundo caso de RNF03 (D40), con una esquina de unos 28° y una entrante.
- `l`, `u` y `triangulo`: formas de la verificación visual (D40).
- `reservada_centro` y `reservada_borde`: los casos con áreas reservadas (D59). El rectangular con un
  área de 120 × 50 m en el medio, alineada con la grilla (ocupa el lugar de una manzana), y el
  irregular con una franja de servidumbre de 20 m contra su lado oblicuo, como la de la p. 48.
"""

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from shapely import Point, Polygon, box
from shapely.affinity import rotate, translate

from . import __version__
from .contrato import Estrategia, PatronRed, ResultadoGeneracion, SolicitudGeneracion, TipoProyecto
from .coordenadas import a_metros, faja_posgar2007, srid_posgar2007
from .exportar import capas_geojson, escribir
from .motor import MotorGeneracion
from .valores_referencia import JERARQUIAS_REFERENCIA, PARAMETROS_LOTEO_REFERENCIA

# Centro de los terrenos (longitud, latitud): campo abierto en la periferia sudeste de la ciudad
# de Córdoba, en la faja 4. Ni el terreno rectangular ni unos 300 m alrededor tienen calles,
# caminos ni otros elementos en OpenStreetMap (consultado el 29/10/2026, D27). Los demás casos
# caben en esa misma zona.
CENTRO = (-64.1168, -31.5080)
LARGO, ANCHO = 480.0, 270.0
ROTACION = 20.0  # grados, antihorario desde el este de cuadrícula
SEMILLA = 1042

SALIDA = Path("salida")


@dataclass(frozen=True)
class Caso:
    """Un terreno dibujado en metros alrededor de (0, 0), con sus accesos sobre el borde y sus
    áreas reservadas (D59). Se rota `ROTACION` y se lleva al centro; la grilla se orienta igual."""

    nombre: str
    descripcion: str
    terreno: Polygon
    accesos: tuple[Point, ...]
    reservadas: tuple[Polygon, ...] = ()


def _franja(a, b, ancho: float, terreno: Polygon) -> Polygon:
    """Una franja de `ancho` contra el lado a → b de un terreno en sentido antihorario, hacia adentro."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    direccion = (b - a) / np.linalg.norm(b - a)
    normal = np.array([-direccion[1], direccion[0]])
    return Polygon([a, b, b + normal * ancho, a + normal * ancho]).intersection(terreno)


IRREGULAR = Polygon([(-320, -120), (240, -120), (240, 150), (120, 150), (120, 60), (20, 60)])


CASOS: dict[str, Caso] = {
    caso.nombre: caso
    for caso in (
        Caso(
            "referencia",
            "Rectángulo de 480 × 270 m (12,96 ha). A1, sobre el lado sur, cae en medio de una "
            "manzana y necesita un conector; A2, sobre el lado este, coincide con el eje de una "
            "calle longitudinal (a 33,75 m del centro) y se une directo.",
            box(-LARGO / 2, -ANCHO / 2, LARGO / 2, ANCHO / 2),
            (Point(-60.0, -ANCHO / 2), Point(LARGO / 2, 33.75)),
        ),
        Caso(
            "irregular",
            "Hexágono de unas 11 ha con una esquina de unos 28° al oeste y una entrante al norte.",
            IRREGULAR,
            (Point(-40, -120), Point(240, 30)),
        ),
        Caso(
            "l",
            "L de 460 × 300 m (unas 8,7 ha): un brazo de 130 m al sur y otro de 160 m al oeste.",
            Polygon([(-230, -150), (230, -150), (230, -20), (-70, -20), (-70, 150), (-230, 150)]),
            (Point(0, -150), Point(-230, 60)),
        ),
        Caso(
            "u",
            "U de 480 × 300 m (11,9 ha), abierta al norte, con brazos de 140 m y una entrante de "
            "200 × 125 m.",
            Polygon(
                [(-240, -150), (240, -150), (240, 150), (100, 150), (100, 25), (-100, 25), (-100, 150), (-240, 150)]
            ),
            (Point(0, -150),),
        ),
        Caso(
            "triangulo",
            "Triángulo de 640 m de base (8,64 ha) con un ángulo de unos 24° al este.",
            Polygon([(-300, -130), (340, -130), (-260, 140)]),
            (Point(0, -130), Point(-280, 5)),
        ),
        Caso(
            "reservada_centro",
            "El rectangular con un área reservada de 120 × 50 m (0,6 ha) en el medio, alineada con la "
            "grilla: ocupa el lugar de una manzana, y su calle sigue como calle de la grilla.",
            box(-LARGO / 2, -ANCHO / 2, LARGO / 2, ANCHO / 2),
            (Point(-60.0, -ANCHO / 2), Point(LARGO / 2, 33.75)),
            (box(-60, -51, 60, -1),),
        ),
        Caso(
            "reservada_borde",
            "El irregular con una franja de servidumbre de 20 m de ancho contra su lado oblicuo (unos "
            "7.300 m², como la de la p. 48): la calle de borde corre por el lado de adentro de la franja.",
            IRREGULAR,
            (Point(-40, -120), Point(240, 30)),
            (_franja((20, 60), (-320, -120), 20.0, IRREGULAR),),
        ),
    )
}


def srid_referencia() -> int:
    return srid_posgar2007(faja_posgar2007(CENTRO[0]))


def solicitud_caso(nombre: str) -> SolicitudGeneracion:
    """La solicitud de un caso, en metros, en el sistema de cálculo de la faja del centro."""
    caso = CASOS[nombre]
    centro = a_metros(Point(CENTRO), srid_referencia())

    def ubicar(geometria):
        return translate(rotate(geometria, ROTACION, origin=(0, 0)), centro.x, centro.y)

    return SolicitudGeneracion(
        tipo=TipoProyecto.LOTEO,
        terreno=ubicar(caso.terreno),
        accesos=tuple(ubicar(acceso) for acceso in caso.accesos),
        parametros=PARAMETROS_LOTEO_REFERENCIA,
        jerarquias=JERARQUIAS_REFERENCIA,
        estrategia=Estrategia(PatronRed.GRILLA, orientacion=ROTACION, semilla=SEMILLA),
        reservadas=tuple(ubicar(area) for area in caso.reservadas),
    )


def solicitud_referencia() -> SolicitudGeneracion:
    """El caso rectangular de RNF03 (D27)."""
    return solicitud_caso("referencia")


def solicitud_irregular() -> SolicitudGeneracion:
    """El caso irregular de RNF03 (D40)."""
    return solicitud_caso("irregular")


def resumen(solicitud: SolicitudGeneracion, resultado: ResultadoGeneracion, srid: int) -> dict:
    """Lo que se guarda en indicadores.json: con qué se generó y qué salió."""
    por_tipo: dict[str, int] = {}
    for incumplimiento in resultado.incumplimientos:
        por_tipo[str(incumplimiento.tipo)] = por_tipo.get(str(incumplimiento.tipo), 0) + 1
    celdas: dict[str, int] = {}
    for celda in resultado.celdas:
        celdas[str(celda.tipo)] = celdas.get(str(celda.tipo), 0) + 1
    return {
        "motor": __version__,
        "srid_calculo": srid,
        "estrategia": {
            "patron_red": str(solicitud.estrategia.patron_red),
            "orientacion": solicitud.estrategia.orientacion,
            "semilla": solicitud.estrategia.semilla,
        },
        "parametros": asdict(solicitud.parametros),
        "jerarquias": [asdict(j) | {"ancho_total": j.ancho_total} for j in solicitud.jerarquias],
        "indicadores": {
            clave: (round(valor, 2) if isinstance(valor, float) else valor)
            for clave, valor in asdict(resultado.indicadores).items()
        },
        "cumple": resultado.cumple(),
        "incumplimientos": dict(sorted(por_tipo.items())),
        "cantidad": {
            "tramos": len(resultado.red.tramos()),
            "manzanas": len(resultado.manzanas),
            "celdas": dict(sorted(celdas.items())),
        },
    }


def generar_caso(nombre: str, carpeta: Path) -> dict:
    """Genera un caso y escribe sus capas y su resumen en `carpeta`."""
    srid = srid_referencia()
    solicitud = solicitud_caso(nombre)
    resultado = MotorGeneracion().generar(solicitud)
    rutas = escribir(capas_geojson(solicitud, resultado, srid), carpeta)
    datos = resumen(solicitud, resultado, srid)
    ruta_indicadores = carpeta / "indicadores.json"
    ruta_indicadores.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Caso «{nombre}» generado en {carpeta}/ (sistema de cálculo EPSG:{srid})")
    for ruta in [*rutas, ruta_indicadores]:
        print(f"  {ruta.name}")
    print(json.dumps(datos["indicadores"], ensure_ascii=False, indent=2))
    print(f"Celdas: {datos['cantidad']['celdas']}")
    print(f"Incumplimientos: {datos['incumplimientos'] or 'ninguno'}")
    return datos


def main(argumentos: list[str] | None = None) -> None:
    lector = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    grupo = lector.add_mutually_exclusive_group()
    grupo.add_argument("--caso", choices=sorted(CASOS), default="referencia", help="caso a generar")
    grupo.add_argument("--todos", action="store_true", help="genera todos los casos")
    lector.add_argument(
        "--salida", type=Path, default=SALIDA, help="carpeta de salida (cada caso va en una subcarpeta)"
    )
    opciones = lector.parse_args(argumentos)
    for nombre in sorted(CASOS) if opciones.todos else [opciones.caso]:
        generar_caso(nombre, opciones.salida / nombre)


if __name__ == "__main__":
    main()
