"""Única fuente de aleatoriedad del motor (RNF05).

Una misma combinación de polígono, parámetros y estrategia tiene que producir siempre la
misma alternativa. Por eso el motor no usa estado aleatorio global (`random`,
`numpy.random.seed`, `numpy.random.rand`...) ni fuentes que cambian entre corridas (el
reloj, `uuid`, `secrets`). Todo componente que necesite azar recibe un
`numpy.random.Generator` creado acá a partir de la semilla explícita de la estrategia
(`Estrategia.semilla` en el diagrama de clases, persistida en `version_alternativa.semilla`
del ER). Lo ata tests/test_semillas.py.

Para repartir azar entre partes independientes (por ejemplo, un generador por manzana) se
usa `generador(semilla).spawn(n)`, que también es determinista. Si una función de NetworkX
pide `seed`, se le pasa un entero sacado del generador, nunca `None`.
"""

import numpy as np

# La semilla que se propone antes de generar (p. 43, paso 1; D42): la del ejemplo de la p. 49.
# Cualquier entero sirve; lo que importa es que quede explícita en la versión.
SEMILLA_SUGERIDA = 1042


def validar_semilla(semilla: int) -> None:
    """Exige una semilla entera, explícita y no negativa (copia única de la regla).

    Con `None`, NumPy toma entropía del sistema operativo (no reproducible), y un `float`,
    un `bool` o un texto son casi siempre un error del llamador que conviene ver enseguida.
    La usan `generador` y `SolicitudGeneracion.validar`.
    """
    if isinstance(semilla, bool) or not isinstance(semilla, int):
        raise TypeError(
            f"La semilla debe ser un entero explícito (RNF05); se recibió {semilla!r}."
        )
    if semilla < 0:
        raise ValueError(f"La semilla debe ser un entero no negativo; se recibió {semilla}.")


def generador(semilla: int) -> np.random.Generator:
    """Crea el generador pseudoaleatorio de una generación a partir de su semilla."""
    validar_semilla(semilla)
    return np.random.default_rng(semilla)
