import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Pesos del dígito verificador del CUIT (módulo 11), del primero al décimo dígito.
PESOS_CUIT = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def normalizar_cuit(cuit: str) -> str:
    """'20123456786' o '20-12345678-6' → '20-12345678-6' (el varchar(13) del ER).

    ValueError si no tiene 11 dígitos o si el verificador no coincide. Un resultado de 10 no
    es válido: a esos números se les asigna otro prefijo (23 o 33), que da otro verificador.
    """
    digitos = re.sub(r"[\s.-]", "", cuit)
    if not re.fullmatch(r"\d{11}", digitos):
        raise ValueError("Tiene que tener 11 dígitos, con o sin guiones (NN-NNNNNNNN-N).")
    verificador = 11 - sum(int(d) * peso for d, peso in zip(digitos, PESOS_CUIT)) % 11
    if verificador == 11:
        verificador = 0
    if verificador == 10 or verificador != int(digitos[-1]):
        raise ValueError("No es un CUIT válido: el dígito verificador no coincide.")
    return f"{digitos[:2]}-{digitos[2:10]}-{digitos[10]}"


class ClienteIn(BaseModel):
    """Alta de un cliente (CU03: si no está cargado, primero hay que darlo de alta)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    razon_social: str = Field(min_length=1, max_length=120)
    cuit: str | None = Field(None, description="11 dígitos, con o sin guiones. Se guarda como NN-NNNNNNNN-N.")
    email: str | None = Field(None, max_length=120)
    telefono: str | None = Field(None, max_length=30)

    @field_validator("cuit")
    @classmethod
    def _cuit(cls, cuit: str | None) -> str | None:
        return normalizar_cuit(cuit) if cuit else None

    @field_validator("email")
    @classmethod
    def _email(cls, email: str | None) -> str | None:
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("No es una dirección de correo válida.")
        return email or None

    @field_validator("telefono")
    @classmethod
    def _telefono(cls, telefono: str | None) -> str | None:
        return telefono or None


class ClienteOut(BaseModel):
    id_cliente: int
    razon_social: str
    cuit: str | None
    email: str | None
    telefono: str | None
