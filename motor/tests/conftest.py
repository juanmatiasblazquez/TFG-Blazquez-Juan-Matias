"""Fixtures compartidas: los casos de referencia se generan una sola vez por corrida."""

import pytest
from contorno import con_contorno

from motor_trazados import MotorGeneracion
from motor_trazados.referencia import solicitud_irregular, solicitud_referencia


@pytest.fixture(scope="session")
def referencia():
    return solicitud_referencia()


@pytest.fixture(scope="session")
def resultado_referencia(referencia):
    return MotorGeneracion().generar(referencia)


@pytest.fixture(scope="session")
def resultado_referencia_sin_asignador(referencia):
    """El rectangular como sale de la clasificación, sin completar la cesión (D44)."""
    return MotorGeneracion(asignar_espacios_verdes=False).generar(referencia)


@pytest.fixture(scope="session")
def referencia_contorno(referencia):
    """El rectangular con la calle de borde en todo el contorno (D50), para lo que es propio de ella."""
    return con_contorno(referencia)


@pytest.fixture(scope="session")
def resultado_referencia_contorno(referencia_contorno):
    return MotorGeneracion().generar(referencia_contorno)


@pytest.fixture(scope="session")
def irregular():
    return solicitud_irregular()


@pytest.fixture(scope="session")
def resultado_irregular(irregular):
    return MotorGeneracion().generar(irregular)
