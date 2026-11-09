from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencias import requiere
from app.core.db import get_db
from app.core.permisos import Funcion
from app.models import Usuario
from app.schemas.cliente import ClienteIn, ClienteOut
from app.schemas.errores import ErrorOut
from app.services import clientes

router = APIRouter(tags=["clientes"])

# «Consultar alternativas» (p. 54).
CONSULTAR = requiere(Funcion.CONSULTAR_ALTERNATIVAS)
# «Registrar proyectos, delimitar terrenos y configurar parámetros» (p. 54).
REGISTRAR = requiere(Funcion.REGISTRAR_PROYECTOS)


@router.get("/clientes", summary="Listar los clientes", response_model=list[ClienteOut])
def listar_clientes(db: Session = Depends(get_db), usuario: Usuario = Depends(CONSULTAR)) -> list[ClienteOut]:
    """Los clientes del estudio, por razón social: entre ellos se elige el del proyecto (CU03)."""
    return [clientes.presentar(cliente) for cliente in clientes.listar(db)]


@router.post(
    "/clientes",
    summary="Dar de alta un cliente",
    status_code=201,
    response_model=ClienteOut,
    responses={409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def crear_cliente(
    datos: ClienteIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(REGISTRAR),
) -> ClienteOut:
    """CU03: «si un cliente no está cargado, primero hay que darlo de alta». El CUIT es
    opcional; si se indica, se verifica y no se puede repetir (D35)."""
    cliente = clientes.crear(db, datos)
    response.headers["Location"] = request.url_for("leer_cliente", id_cliente=cliente.id_cliente).path
    return clientes.presentar(cliente)


@router.get(
    "/clientes/{id_cliente}",
    summary="Consultar un cliente",
    response_model=ClienteOut,
    responses={404: {"model": ErrorOut}},
)
def leer_cliente(id_cliente: int, db: Session = Depends(get_db), usuario: Usuario = Depends(CONSULTAR)) -> ClienteOut:
    return clientes.presentar(clientes.obtener(db, id_cliente))
