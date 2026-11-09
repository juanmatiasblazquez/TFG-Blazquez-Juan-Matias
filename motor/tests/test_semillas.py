"""RNF05: misma combinación de polígono, parámetros y estrategia → misma alternativa.

La convención: toda aleatoriedad del motor sale de `semillas.generador(semilla)`, con la
semilla explícita de la estrategia. Estas pruebas la atan. Las reglas que un análisis así
no puede ver (no iterar un `set` sin ordenarlo, desempatar con claves estables) están en
CLAUDE.md, «Invariantes de arquitectura».
"""

import ast

import numpy as np
import pytest

from analisis_fuente import Hallazgo, imports_absolutos, modulos_del_paquete, nombre_punteado
from motor_trazados.semillas import generador

# El único módulo que puede tocar numpy.random: el que crea el generador desde la semilla.
ARCHIVO_SEMILLAS = "motor_trazados/semillas.py"

# Módulos que dan azar global o valores distintos en cada corrida. Prohibidos en todo el motor.
MODULOS_NO_REPRODUCIBLES = {"random", "secrets", "uuid"}

# Llamadas que leen el reloj: el resultado dependería del momento de la corrida. Medir
# cuánto tardó una generación (`duracion_ms` del ER) es tarea de la API, no del motor.
LECTURAS_DEL_RELOJ = {"now", "utcnow", "today", "time", "time_ns"}
MODULOS_DEL_RELOJ = {"datetime", "date", "time"}


def fuentes_no_reproducibles(modulos: list[tuple[str, ast.Module]]) -> list[Hallazgo]:
    hallazgos = []
    for archivo, arbol in modulos:
        alias_numpy = {"numpy"}
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                alias_numpy |= {a.asname or a.name for a in nodo.names if a.name == "numpy"}

        for linea, modulo in imports_absolutos(arbol):
            raiz = modulo.split(".")[0]
            if raiz in MODULOS_NO_REPRODUCIBLES:
                hallazgos.append(Hallazgo(archivo, linea, f"importa «{modulo}»: azar fuera de la semilla"))
            elif modulo.startswith("numpy.random") and archivo != ARCHIVO_SEMILLAS:
                hallazgos.append(Hallazgo(archivo, linea, f"importa «{modulo}»: usar semillas.generador"))

        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.Attribute, ast.Call)):
                continue
            nombre = nombre_punteado(nodo.func if isinstance(nodo, ast.Call) else nodo) or ""
            partes = nombre.split(".")
            if (
                isinstance(nodo, ast.Attribute)
                and len(partes) == 2
                and partes[0] in alias_numpy
                and partes[1] == "random"
                and archivo != ARCHIVO_SEMILLAS
            ):
                hallazgos.append(Hallazgo(archivo, nodo.lineno, f"usa «{nombre}»: usar semillas.generador"))
            if (
                isinstance(nodo, ast.Call)
                and len(partes) >= 2
                and partes[-1] in LECTURAS_DEL_RELOJ
                and partes[-2] in MODULOS_DEL_RELOJ
            ):
                hallazgos.append(Hallazgo(archivo, nodo.lineno, f"lee el reloj con «{nombre}()»"))
    return sorted(set(hallazgos), key=lambda h: (h.archivo, h.linea))


def test_el_motor_no_tiene_otra_fuente_de_aleatoriedad():
    hallazgos = fuentes_no_reproducibles(modulos_del_paquete())
    assert not hallazgos, (
        "El motor tiene una fuente no reproducible (RNF05). Toda aleatoriedad sale de "
        "semillas.generador(semilla):\n" + "\n".join(map(str, hallazgos))
    )


def test_el_detector_encuentra_azar_y_reloj():
    """Sin esta prueba, un detector roto (que no encuentra nada) pasaría en verde."""
    codigo = ast.parse(
        "import numpy as np\n"
        "import random\n"
        "np.random.seed(1)\n"
        "from numpy.random import default_rng\n"
        "import datetime\n"
        "datetime.datetime.now()\n"
        "import time\n"
        "time.perf_counter()\n"
        "from uuid import uuid4\n"
    )
    hallazgos = fuentes_no_reproducibles([("motor_trazados/sintetico.py", codigo)])
    assert [h.linea for h in hallazgos] == [2, 3, 4, 6, 9]


def test_misma_semilla_misma_secuencia():
    assert np.array_equal(generador(20261027).random(1000), generador(20261027).random(1000))


def test_semillas_distintas_dan_secuencias_distintas():
    assert not np.array_equal(generador(1).random(100), generador(2).random(100))


def test_los_subgeneradores_tambien_son_reproducibles():
    primera = [g.integers(0, 1_000_000, 20) for g in generador(7).spawn(3)]
    segunda = [g.integers(0, 1_000_000, 20) for g in generador(7).spawn(3)]
    assert all(np.array_equal(a, b) for a, b in zip(primera, segunda, strict=True))


def test_la_secuencia_no_cambia_entre_versiones_de_numpy():
    """Valor dorado: NumPy no garantiza el mismo flujo de `Generator` entre versiones.

    Si esto falla después de subir NumPy, la misma semilla ya no reproduce las alternativas
    guardadas: es una decisión a registrar en docs/decisiones.md antes de aceptar la versión.
    """
    assert generador(42).integers(0, 1000, 8).tolist() == VALOR_DORADO_SEMILLA_42


@pytest.mark.parametrize("semilla", [None, True, 3.0, "42"])
def test_la_semilla_es_un_entero_explicito(semilla):
    with pytest.raises(TypeError, match="RNF05"):
        generador(semilla)


def test_la_semilla_no_es_negativa():
    with pytest.raises(ValueError):
        generador(-1)


# generador(42).integers(0, 1000, 8) con numpy==2.5.4 (PCG64).
VALOR_DORADO_SEMILLA_42 = [89, 773, 654, 438, 433, 858, 85, 697]
