"""RNF03: la generación tarda un tiempo acorde al tamaño del terreno (D27).

Cuatro terrenos: el rectangular de 480 × 270 m (12,96 ha, 286 lotes; D27), el irregular, con
una esquina de unos 28° y una entrante (D40), y los dos con áreas reservadas (D59), que pasan por
las rectas alineadas con el área y el cierre con piezas fijas. Los tiempos medidos están en D27, D40
y D59. El umbral
es generoso para detectar una regresión de orden de magnitud sin depender de la máquina. Medir
es tarea de la prueba: el paquete no lee el reloj (RNF05, D04).
"""

import time

import pytest

from motor_trazados import MotorGeneracion
from motor_trazados.referencia import solicitud_caso

UMBRAL_SEGUNDOS = 2.0
REPETICIONES = 3


@pytest.mark.parametrize("caso", ["referencia", "irregular", "reservada_centro", "reservada_borde"])
def test_el_caso_se_genera_dentro_del_umbral(caso, capsys):
    motor = MotorGeneracion()
    solicitud = solicitud_caso(caso)
    tiempos = []
    for _ in range(REPETICIONES):
        inicio = time.perf_counter()
        motor.generar(solicitud)
        tiempos.append(time.perf_counter() - inicio)
    mejor = min(tiempos)
    with capsys.disabled():
        print(
            f"\n[RNF03] caso {caso}: {mejor:.2f} s "
            f"(mejor de {REPETICIONES}; umbral {UMBRAL_SEGUNDOS:.1f} s)"
        )
    assert mejor < UMBRAL_SEGUNDOS


@pytest.mark.parametrize("giro", [0, 90, 45])
def test_el_recalculo_se_hace_dentro_del_umbral(giro, capsys):
    """El recálculo (CU09, D56) del rectangular con M2 y M3 fijadas, con la misma orientación, a 90° y
    a 45°: el mismo umbral que generar. No cuenta la generación de la versión de origen."""
    from dataclasses import replace

    motor = MotorGeneracion()
    solicitud = solicitud_caso("referencia")
    fijados = motor.fijar(motor.generar(solicitud), ["M2", "M3"], solicitud.estrategia.orientacion)
    nueva = replace(
        solicitud, estrategia=replace(solicitud.estrategia, orientacion=(solicitud.estrategia.orientacion + giro) % 180)
    )
    tiempos = []
    for _ in range(REPETICIONES):
        inicio = time.perf_counter()
        motor.recalcular(nueva, fijados)
        tiempos.append(time.perf_counter() - inicio)
    mejor = min(tiempos)
    with capsys.disabled():
        print(f"\n[RNF03] recálculo a +{giro}°: {mejor:.2f} s (mejor de {REPETICIONES}; umbral {UMBRAL_SEGUNDOS:.1f} s)")
    assert mejor < UMBRAL_SEGUNDOS
