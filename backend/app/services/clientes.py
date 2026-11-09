"""Clientes del estudio (ER `cliente`). CU03 exige uno por proyecto (D35)."""

import psycopg.errors
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errores import ErrorApi
from app.models import Cliente
from app.schemas.cliente import ClienteIn, ClienteOut


def crear(db: Session, datos: ClienteIn) -> Cliente:
    """Da de alta un cliente. El CUIT ya viene normalizado y verificado (ClienteIn)."""
    if datos.cuit is not None and db.scalar(select(Cliente.id_cliente).where(Cliente.cuit == datos.cuit)) is not None:
        raise _cuit_repetido(datos.cuit)
    cliente = Cliente(**datos.model_dump())
    db.add(cliente)
    try:
        db.commit()
    except IntegrityError as error:
        # Dos altas simultáneas con el mismo CUIT: la restricción única decide.
        db.rollback()
        if isinstance(error.orig, psycopg.errors.UniqueViolation):
            raise _cuit_repetido(datos.cuit) from error
        raise
    return cliente


def listar(db: Session) -> list[Cliente]:
    return list(db.scalars(select(Cliente).order_by(Cliente.razon_social, Cliente.id_cliente)))


def obtener(db: Session, id_cliente: int) -> Cliente:
    cliente = db.get(Cliente, id_cliente)
    if cliente is None:
        raise ErrorApi(404, f"No existe el cliente {id_cliente}.")
    return cliente


def presentar(cliente: Cliente) -> ClienteOut:
    return ClienteOut(
        id_cliente=cliente.id_cliente,
        razon_social=cliente.razon_social,
        cuit=cliente.cuit,
        email=cliente.email,
        telefono=cliente.telefono,
    )


def _cuit_repetido(cuit: str | None) -> ErrorApi:
    return ErrorApi(
        409,
        f"Ya existe un cliente con el CUIT {cuit}.",
        "Elegí ese cliente de la lista en lugar de darlo de alta otra vez.",
        [("cuit", "Ya está en uso.")],
    )
