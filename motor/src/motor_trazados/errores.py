"""Errores del motor: lo que la API traduce a respuestas (por ejemplo, 422 con causa y sugerencia).

Un incumplimiento de parámetros (un lote chico, la cesión de verde) NO es un error: la
alternativa se genera igual y lo lleva marcado (CU06, 6.a). Un error significa que no hay
alternativa que devolver.
"""

from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry


class ErrorMotor(Exception):
    """Base de los errores del motor."""


@dataclass(frozen=True, slots=True)
class Problema:
    """Un dato de la solicitud que no es válido, con el campo al que se refiere (RNF01)."""

    campo: str
    mensaje: str

    def __str__(self) -> str:
        return f"{self.campo}: {self.mensaje}"


class SolicitudInvalida(ErrorMotor):
    """La solicitud tiene datos incoherentes; `problemas` dice cuáles."""

    def __init__(self, problemas: list[Problema]):
        self.problemas = tuple(problemas)
        super().__init__("La solicitud no es válida. " + " ".join(f"{p}." for p in self.problemas))


class ErrorConectividad(ErrorMotor):
    """La red no se pudo conectar con todos los accesos (p. 43: 422 con causa y sugerencia)."""

    def __init__(self, causa: str, sugerencia: str, geometria: BaseGeometry | None = None):
        self.causa = causa
        self.sugerencia = sugerencia
        self.geometria = geometria
        super().__init__(f"{causa} {sugerencia}")


class TerrenoSinLotes(ErrorMotor):
    """En el terreno no entra ni un lote que cumpla los mínimos (D40): no hay loteo que
    devolver. Se informa con causa y sugerencia, como la conectividad (422 de CU06)."""

    def __init__(self, causa: str, sugerencia: str):
        self.causa = causa
        self.sugerencia = sugerencia
        super().__init__(f"{causa} {sugerencia}")


class SinDominioRestante(ErrorMotor):
    """Lo fijado abarca todo el terreno: no queda nada que recalcular (CU09, curso 3.a; D56). Se
    informa con causa y sugerencia, como la conectividad."""

    def __init__(self, causa: str, sugerencia: str):
        self.causa = causa
        self.sugerencia = sugerencia
        super().__init__(f"{causa} {sugerencia}")


class NoImplementado(ErrorMotor, NotImplementedError):
    """Lo pedido es parte del contrato pero todavía no se implementó (por ejemplo, playas).

    `sugerencia` es opcional: la API la muestra junto a la causa (422, CU06) cuando hay algo
    concreto que el usuario puede hacer mientras tanto.
    """

    def __init__(self, causa: str, sugerencia: str | None = None):
        self.causa = causa
        self.sugerencia = sugerencia
        super().__init__(causa if sugerencia is None else f"{causa} {sugerencia}")
