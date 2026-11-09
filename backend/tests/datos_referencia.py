"""Los casos de referencia del motor (motor_trazados.referencia) como pedidos a la API.

Es la copia única de esos cuerpos: los usan las pruebas y scripts/generar-referencia.ps1, que
los pide así (la salida es JSON en ASCII, para que PowerShell 5.1 no rompa los acentos, y el
script la manda tal cual, sin volver a serializar las coordenadas):

    docker compose exec -T api python -m tests.datos_referencia cliente
    docker compose exec -T api python -m tests.datos_referencia proyecto CODIGO ID_CLIENTE [CASO]
    docker compose exec -T api python -m tests.datos_referencia generacion [ORIENTACION] [SEMILLA]

CASO es uno de `motor_trazados.referencia.CASOS` («referencia», el rectangular, si no se dice) o de
`DEMOS` («prototipo», el pentágono de los prototipos de las p. 48 a 51). Todos se generan con la misma
estrategia.
"""

import json
import math
import sys

from motor_trazados.coordenadas import a_geograficas, a_metros
from motor_trazados.referencia import (
    CASOS,
    CENTRO,
    ROTACION,
    SEMILLA,
    solicitud_caso,
    solicitud_referencia,
    srid_referencia,
)
from shapely import Point, Polygon
from shapely.affinity import rotate, translate

VIAS = ("Calle pública", "Camino vecinal")
# El cliente es ficticio, como la ubicación: por eso no tiene CUIT.
CLIENTE = "Cliente de referencia (ficticio)"
# A qué corresponde cada área de los casos con áreas (CU04, paso 5; D59). Sin clase: el documento no
# enumera los valores de ClaseArea (D29).
DENOMINACIONES = {
    "reservada_centro": ("Reserva para equipamiento comunitario",),
    "reservada_borde": ("Servidumbre de electroducto",),
    "prototipo": ("Servidumbre de electroducto",),
}
# El ancho de cada acceso, si no es 20 m.
ANCHOS = {"prototipo": (20.0, 14.0)}


def _prototipo() -> tuple[Polygon, list[Point], list[Polygon]]:
    """Un terreno como el de los prototipos (p. 48 a 51; D73): un pentágono de unas 12 ha, con lados de
    ≈ 360, 272, 224, 218 y 271 m; una servidumbre de electroducto de 20 m sobre el lado este; A1 sobre el
    lado sur (la calle pública) y A2 sobre el oeste (el camino vecinal). En metros, alrededor de (0, 0),
    girado −ROTACION: la rotación común de los casos lo deja con el norte arriba, como en las figuras."""
    vertices = [(0, 0), (360, -19.6), (399.7, 249.7), (189.9, 329.4), (-19.9, 270.0)]
    v = [(x - 190, y - 140) for x, y in vertices]
    en = lambda a, b, t: Point(a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))  # noqa: E731
    dx, dy = v[2][0] - v[1][0], v[2][1] - v[1][1]
    largo = math.hypot(dx, dy)
    nx, ny = -dy / largo, dx / largo
    franja = Polygon([v[1], v[2], (v[2][0] + 20 * nx, v[2][1] + 20 * ny), (v[1][0] + 20 * nx, v[1][1] + 20 * ny)])
    derecho = lambda g: rotate(g, -ROTACION, origin=(0, 0))  # noqa: E731
    return derecho(Polygon(v)), [derecho(en(v[0], v[1], 0.413)), derecho(en(v[0], v[4], 0.4926))], [derecho(franja)]


# Casos de demostración: fuera de `referencia.CASOS`, porque las pruebas del motor recorren todos esos
# casos con exigencias (el 20 % de avenidas sin transversales de más, la cesión con los dos criterios)
# que un terreno armado para parecerse a un dibujo no tiene por qué cumplir (D73). Se llevan a 4326 con
# el mismo marco que los casos (`en_4326_como_los_casos`).
DEMOS = {"prototipo": _prototipo}


def terreno_y_accesos_4326(caso: str = "referencia") -> tuple[Polygon, list[Point]]:
    if caso in DEMOS:
        terreno, accesos, _ = DEMOS[caso]()
        return en_4326_como_los_casos(terreno), [en_4326_como_los_casos(a) for a in accesos]
    solicitud = solicitud_caso(caso)
    srid = srid_referencia()
    return a_geograficas(solicitud.terreno, srid), [a_geograficas(a, srid) for a in solicitud.accesos]


def areas_4326(caso: str = "referencia") -> list[Polygon]:
    """Las áreas reservadas de un caso, en 4326 (D59)."""
    if caso in DEMOS:
        return [en_4326_como_los_casos(area) for area in DEMOS[caso]()[2]]
    srid = srid_referencia()
    return [a_geograficas(area, srid) for area in solicitud_caso(caso).reservadas]


def en_4326_como_los_casos(geometria_del_caso):
    """Una geometría dibujada en las coordenadas de los casos de referencia (metros alrededor de
    (0, 0), sin rotar), llevada a 4326 como `referencia.solicitud_caso` lleva sus terrenos: así
    queda exacta respecto del terreno y de los accesos."""
    centro = a_metros(Point(CENTRO), srid_referencia())
    return a_geograficas(translate(rotate(geometria_del_caso, ROTACION, origin=(0, 0)), centro.x, centro.y), srid_referencia())


def cuerpo_area(area: Polygon, denominacion: str, **cambios) -> dict:
    """Un área de `areas_reservadas`, con su polígono en 4326 con la precisión completa."""
    return {
        "geometria": {"type": "Polygon", "coordinates": [[list(c) for c in area.exterior.coords]]},
        "denominacion": denominacion,
    } | cambios


def cuerpo_cliente() -> dict:
    """POST /api/clientes con el cliente del caso de referencia."""
    return {"razon_social": CLIENTE}


def cuerpo_proyecto(
    codigo: str,
    id_cliente: int,
    terreno: Polygon | None = None,
    accesos: list[Point] | None = None,
    caso: str = "referencia",
    **cambios,
) -> dict:
    """POST /api/proyectos con el terreno de un caso de referencia (o el que se indique, en
    4326)."""
    terreno_ref, accesos_ref = terreno_y_accesos_4326(caso)
    terreno = terreno_ref if terreno is None else terreno
    accesos = accesos_ref if accesos is None else accesos
    nombre = (
        "Loteo de referencia"
        if caso == "referencia"
        else "Loteo de demostración" if caso in DEMOS else f"Loteo de referencia ({caso})"
    )
    anchos = ANCHOS.get(caso, ())
    cuerpo = {
        "id_cliente": id_cliente,
        "codigo": codigo,
        "nombre": nombre,
        "tipo": "loteo",
        "ubicacion": "Periferia sudeste de la ciudad de Córdoba (ubicación ilustrativa)",
        "jurisdiccion": "Municipalidad de Córdoba",
        "terreno": {"type": "Polygon", "coordinates": [[list(c) for c in terreno.exterior.coords]]},
        "origen": "dibujado",
        "accesos": [
            {
                "ubicacion": {"type": "Point", "coordinates": [a.x, a.y]},
                "ancho_m": anchos[k] if k < len(anchos) else 20.0,
                "via_vinculacion": via,
            }
            for k, (a, via) in enumerate(zip(accesos, VIAS * len(accesos)))
        ],
        "areas_reservadas": [
            cuerpo_area(area, denominacion)
            for area, denominacion in zip(areas_4326(caso), DENOMINACIONES.get(caso, ()), strict=True)
        ],
    }
    return cuerpo | cambios


def cuerpo_generacion(**cambios) -> dict:
    """POST /api/proyectos/{id}/alternativas con la estrategia del caso de referencia."""
    return {"estrategia": {"patron_red": "grilla", "orientacion_grados": ROTACION, "semilla": SEMILLA} | cambios}


def cuerpo_recalculo(manzanas: list[str], **cambios) -> dict:
    """POST /api/versiones/{id}/recalculos: las manzanas que se conservan y la estrategia (la de
    referencia, salvo cambios) (CU09, D56)."""
    return {"manzanas": list(manzanas)} | cuerpo_generacion(**cambios)


def en_4326_junto_al_de_referencia(geometria_local):
    """Una geometría dibujada en metros alrededor de (0, 0), llevada al centro del terreno de
    referencia (centro redondeado al metro, como el marco local del motor) y pasada a 4326."""
    centro = solicitud_referencia().terreno.centroid  # ya en metros, en el sistema de cálculo
    ubicada = translate(geometria_local, round(centro.x), round(centro.y))
    return a_geograficas(ubicada, srid_referencia())


if __name__ == "__main__":
    pedido, *argumentos = sys.argv[1:] or ["cliente"]
    if pedido == "cliente":
        cuerpo = cuerpo_cliente()
    elif pedido == "proyecto":
        if len(argumentos) not in (2, 3) or (len(argumentos) == 3 and argumentos[2] not in CASOS.keys() | DEMOS.keys()):
            sys.exit(f"Uso: proyecto CODIGO ID_CLIENTE [CASO], con CASO en {', '.join(sorted(CASOS.keys() | DEMOS.keys()))}")
        cuerpo = cuerpo_proyecto(argumentos[0], int(argumentos[1]), caso=argumentos[2] if len(argumentos) == 3 else "referencia")
    elif pedido == "generacion":
        cambios = {}
        if len(argumentos) > 0:
            cambios["orientacion_grados"] = float(argumentos[0])
        if len(argumentos) > 1:
            cambios["semilla"] = int(argumentos[1])
        cuerpo = cuerpo_generacion(**cambios)
    elif pedido == "recalculo":
        # recalculo ORIENTACION SEMILLA M2 M3…
        if len(argumentos) < 3:
            sys.exit("Uso: recalculo ORIENTACION SEMILLA MANZANA [MANZANA…]")
        cuerpo = cuerpo_recalculo(argumentos[2:], orientacion_grados=float(argumentos[0]), semilla=int(argumentos[1]))
    else:
        sys.exit(f"Pedido desconocido: {pedido!r} (cliente, proyecto, generacion o recalculo).")
    print(json.dumps(cuerpo))
