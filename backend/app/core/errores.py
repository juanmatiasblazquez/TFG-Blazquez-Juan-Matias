"""Errores de la API con un solo formato (D32): causa, sugerencia, problemas por campo y la
geometría del problema, si la hay (CU06: «422 con causa y sugerencia»).

Los mensajes son en español (RNF01), también los de la validación de los datos de entrada,
que Pydantic da en inglés: se traducen por tipo de error.
"""

from collections.abc import Sequence

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.errores import ErrorOut, ProblemaOut


class ErrorApi(Exception):
    """Lo que la API responde cuando no puede hacer lo pedido. Lo lanzan los servicios."""

    def __init__(
        self,
        estado: int,
        causa: str,
        sugerencia: str | None = None,
        problemas: Sequence[tuple[str, str]] = (),
        geometria: dict | None = None,
        encabezados: dict[str, str] | None = None,
    ):
        super().__init__(causa)
        self.estado = estado
        # Por ejemplo `Retry-After` en un 429 (D65).
        self.encabezados = encabezados or {}
        self.cuerpo = ErrorOut(
            causa=causa,
            sugerencia=sugerencia,
            problemas=[ProblemaOut(campo=campo, mensaje=mensaje) for campo, mensaje in problemas],
            geometria=geometria,
        )


# Mensajes de los errores de validación de Pydantic que aparecen en esta API. Los valores de
# `ctx` (límites, valores esperados) se interpolan; un tipo que no está acá conserva el
# mensaje original.
MENSAJES_VALIDACION = {
    "missing": "Falta este dato.",
    "extra_forbidden": "Este campo no se admite.",
    "json_invalid": "El cuerpo no es un JSON válido.",
    "model_type": "Tiene que ser un objeto.",
    "model_attributes_type": "Tiene que ser un objeto.",
    "dict_type": "Tiene que ser un objeto.",
    "list_type": "Tiene que ser una lista.",
    "tuple_type": "Tiene que ser una lista.",
    "string_type": "Tiene que ser un texto.",
    "string_too_short": "No puede estar vacío.",
    "string_too_long": "Admite hasta {max_length} caracteres.",
    "bool_type": "Tiene que ser verdadero o falso.",
    "bool_parsing": "Tiene que ser verdadero o falso.",
    "int_type": "Tiene que ser un número entero.",
    "int_parsing": "Tiene que ser un número entero.",
    "int_from_float": "Tiene que ser un número entero.",
    "float_type": "Tiene que ser un número.",
    "float_parsing": "Tiene que ser un número.",
    "decimal_type": "Tiene que ser un número.",
    "decimal_parsing": "Tiene que ser un número.",
    "decimal_max_places": "Admite hasta {decimal_places} decimales.",
    "decimal_max_digits": "Admite hasta {max_digits} dígitos en total.",
    "finite_number": "Tiene que ser un número finito.",
    "greater_than": "Tiene que ser mayor que {gt}.",
    "greater_than_equal": "Tiene que ser mayor o igual que {ge}.",
    "less_than": "Tiene que ser menor que {lt}.",
    "less_than_equal": "Tiene que ser menor o igual que {le}.",
    "too_short": "Hacen falta al menos {min_length} elementos.",
    "too_long": "Admite hasta {max_length} elementos.",
    "literal_error": "Tiene que ser uno de estos valores: {expected}.",
    "enum": "Tiene que ser uno de estos valores: {expected}.",
}


def campo_de(ubicacion: Sequence) -> str:
    """('body', 'accesos', 0, 'ubicacion') → 'accesos[0].ubicacion'."""
    campo = ""
    for parte in ubicacion:
        if parte in ("body", "path", "query"):
            continue
        if isinstance(parte, int):
            campo += f"[{parte}]"
        else:
            campo += f".{parte}" if campo else str(parte)
    return campo or "cuerpo"


def mensaje_de(error: dict) -> str:
    if error["type"] == "value_error":
        # Los validadores propios ya escriben en español; Pydantic les antepone «Value error, ».
        return str(error["ctx"]["error"])
    plantilla = MENSAJES_VALIDACION.get(error["type"])
    if plantilla is None:
        return error["msg"]
    contexto = dict(error.get("ctx", {}))
    if "expected" in contexto:
        # Pydantic une los valores esperados con «or»: «'a', 'b' or 'c'».
        contexto["expected"] = str(contexto["expected"]).replace(" or ", " o ")
    try:
        return plantilla.format(**contexto)
    except (KeyError, IndexError):
        return error["msg"]


def _responder(estado: int, cuerpo: ErrorOut, encabezados: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=estado, content=cuerpo.model_dump(mode="json"), headers=encabezados)


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ErrorApi)
    def _error_api(request: Request, error: ErrorApi) -> JSONResponse:
        return _responder(error.estado, error.cuerpo, error.encabezados)

    # Los errores de Pydantic traen el valor recibido (`input`), que puede ser una contraseña: acá se
    # usan solo el tipo, la ubicación y el contexto, y nada se registra en el log (D66).
    @app.exception_handler(RequestValidationError)
    def _validacion(request: Request, error: RequestValidationError) -> JSONResponse:
        problemas = [ProblemaOut(campo=campo_de(e["loc"]), mensaje=mensaje_de(e)) for e in error.errors()]
        cuerpo = ErrorOut(
            causa="Los datos enviados no son válidos.",
            sugerencia="Corregí los campos señalados y volvé a enviar.",
            problemas=problemas,
        )
        return _responder(422, cuerpo)
