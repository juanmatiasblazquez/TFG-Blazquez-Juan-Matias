"""RNF05: la misma solicitud (polígono, parámetros y estrategia con su semilla) da exactamente
la misma alternativa, bit a bit.

La segunda prueba repite la generación en subprocesos con distinto PYTHONHASHSEED. Cambiar esa
semilla cambia el orden en que se iteran los `set` y los `dict` armados desde ellos con
claves de texto: si algún paso del motor dependiera de ese orden, la huella cambiaría. Es la
regla que el análisis estático de test_semillas.py no puede ver (CLAUDE.md, invariante 2).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from motor_trazados import MotorGeneracion
from motor_trazados.referencia import solicitud_caso
from huella import huella

# El rectangular de siempre, el irregular (D40), que pasa por el cierre de la partición, la
# transversal de enlace y la clasificación de remanentes, y los dos con áreas reservadas (D59), que
# pasan por las rectas alineadas con el área y el cierre con piezas fijas.
CASOS = ("referencia", "irregular", "reservada_centro", "reservada_borde")


@pytest.mark.parametrize("caso", CASOS)
def test_la_misma_solicitud_da_la_misma_alternativa(caso):
    motor = MotorGeneracion()
    assert huella(motor.generar(solicitud_caso(caso))) == huella(motor.generar(solicitud_caso(caso)))


@pytest.mark.parametrize("caso", CASOS)
def test_la_alternativa_no_depende_del_orden_de_hash_del_proceso(caso):
    esperada = huella(MotorGeneracion().generar(solicitud_caso(caso)))
    carpeta = Path(__file__).resolve().parent
    for semilla_hash in ("0", "1", "4242"):
        entorno = {**os.environ, "PYTHONHASHSEED": semilla_hash}
        salida = subprocess.run(
            [sys.executable, str(carpeta / "huella.py"), caso],
            capture_output=True,
            text=True,
            check=True,
            env=entorno,
            cwd=carpeta,
        )
        assert salida.stdout.strip() == esperada, f"{caso}: con PYTHONHASHSEED={semilla_hash} cambia la alternativa"
