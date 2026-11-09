from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencias import requiere
from app.core.db import get_db
from app.core.permisos import Funcion
from app.models import Usuario
from app.schemas.alternativa import AlternativaOut, DescripcionIn, GeneracionIn
from app.schemas.errores import ErrorOut
from app.services import enlaces
from app.services.generacion import ServicioGeneracion, obtener_alternativa, presentar_alternativa

router = APIRouter(tags=["alternativas"])

# «Consultar alternativas» (p. 54).
CONSULTAR = requiere(Funcion.CONSULTAR_ALTERNATIVAS)
# «Generar alternativas y recalcular sectores» (p. 54).
GENERAR = requiere(Funcion.GENERAR_ALTERNATIVAS)
# «Seleccionar alternativas, compartirlas y revocarlas» (p. 54): la descripción es para el cliente (D76).
COMPARTIR = requiere(Funcion.COMPARTIR_ALTERNATIVAS)


@router.post(
    "/proyectos/{id_proyecto}/alternativas",
    summary="Generar una alternativa",
    status_code=201,
    response_model=AlternativaOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def generar_alternativa(
    id_proyecto: int,
    datos: GeneracionIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(GENERAR),
) -> AlternativaOut:
    """Genera una alternativa nueva con la estrategia confirmada (CU06, secuencia de la p. 43).

    201 con la versión 1 en GeoJSON y sus indicadores. 422 con causa y sugerencia si el motor
    no puede generar (red que no conecta los accesos, terreno que todavía no soporta); en ese
    caso no se guarda nada. Es `def` y no `async def`: el motor ocupa la CPU (D08).
    """
    servicio = ServicioGeneracion(db)
    id_alternativa = servicio.generar_alternativa(id_proyecto, datos.estrategia, usuario).id_alternativa
    response.headers["Location"] = request.url_for("leer_alternativa", id_alternativa=id_alternativa).path
    # Lo que se responde se lee de la base, igual que en el GET.
    db.expire_all()
    return presentar_alternativa(obtener_alternativa(db, id_alternativa))


@router.get(
    "/alternativas/{id_alternativa}",
    summary="Consultar una alternativa",
    response_model=AlternativaOut,
    responses={404: {"model": ErrorOut}},
)
def leer_alternativa(
    id_alternativa: int, db: Session = Depends(get_db), usuario: Usuario = Depends(CONSULTAR)
) -> AlternativaOut:
    """Una alternativa con su versión vigente, en GeoJSON, y la lista de sus versiones (CU10)."""
    return presentar_alternativa(obtener_alternativa(db, id_alternativa))


@router.patch(
    "/alternativas/{id_alternativa}",
    summary="Describir una alternativa para el cliente",
    response_model=AlternativaOut,
    responses={404: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def describir_alternativa(
    id_alternativa: int, datos: DescripcionIn, db: Session = Depends(get_db), usuario: Usuario = Depends(COMPARTIR)
) -> AlternativaOut:
    """La descripción del trazado que ve el cliente arriba de los indicadores (p. 51; D76). Se copia en el
    enlace al compartir: cambiarla después no cambia lo que ya ve el cliente."""
    enlaces.describir(db, id_alternativa, datos.descripcion)
    db.expire_all()
    return presentar_alternativa(obtener_alternativa(db, id_alternativa))
