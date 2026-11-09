from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencias import requiere
from app.core.db import get_db
from app.core.permisos import Funcion
from app.models import Usuario
from app.schemas.errores import ErrorOut
from app.schemas.proyecto import AreasReservadasIn, ProyectoIn, ProyectoOut, ProyectoResumen
from app.services import proyectos

router = APIRouter(tags=["proyectos"])

# «Consultar alternativas» (p. 54).
CONSULTAR = requiere(Funcion.CONSULTAR_ALTERNATIVAS)
# «Registrar proyectos, delimitar terrenos y configurar parámetros» (p. 54).
REGISTRAR = requiere(Funcion.REGISTRAR_PROYECTOS)


@router.get("/proyectos", summary="Listar los proyectos", response_model=list[ProyectoResumen])
def listar_proyectos(db: Session = Depends(get_db), usuario: Usuario = Depends(CONSULTAR)) -> list[ProyectoResumen]:
    """Los proyectos del estudio, del más nuevo al más viejo (CU10, punto de entrada)."""
    return proyectos.listar(db)


@router.post(
    "/proyectos",
    summary="Registrar un proyecto con su terreno",
    status_code=201,
    response_model=ProyectoOut,
    responses={409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def crear_proyecto(
    datos: ProyectoIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(REGISTRAR),
) -> ProyectoOut:
    """Registra un proyecto de loteo con su cliente, su terreno, sus accesos y sus áreas reservadas
    (CU03, CU04).

    Los parámetros que llegan son la versión 1, validada por el motor (CU05); si no llegan, la
    versión 1 son los valores de referencia (D23). Si no se indica `srid_calculo`, se usa la faja
    POSGAR 2007 de la longitud del terreno (D21).
    """
    id_proyecto = proyectos.crear(db, datos, usuario).id_proyecto
    response.headers["Location"] = request.url_for("leer_proyecto", id_proyecto=id_proyecto).path
    # Lo que se responde se lee de la base, igual que en el GET.
    db.expire_all()
    return proyectos.presentar(proyectos.obtener(db, id_proyecto))


@router.get(
    "/proyectos/{id_proyecto}",
    summary="Consultar un proyecto",
    response_model=ProyectoOut,
    responses={404: {"model": ErrorOut}},
)
def leer_proyecto(
    id_proyecto: int, db: Session = Depends(get_db), usuario: Usuario = Depends(CONSULTAR)
) -> ProyectoOut:
    """Un proyecto con su terreno, sus accesos, sus parámetros vigentes y sus alternativas (RF13)."""
    return proyectos.presentar(proyectos.obtener(db, id_proyecto))


@router.put(
    "/proyectos/{id_proyecto}/areas-reservadas",
    summary="Reemplazar las áreas reservadas del proyecto",
    response_model=ProyectoOut,
    responses={404: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def reemplazar_areas_reservadas(
    id_proyecto: int,
    datos: AreasReservadasIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(REGISTRAR),
) -> ProyectoOut:
    """Las áreas reservadas del terreno, enteras (CU04, paso 5): reemplazan a las que tenía, con la
    misma validación del alta (422 si un área sale del terreno, se superpone con otra, cubren todo,
    toman el tramo de un acceso o dejan una parte sin acceso). Las versiones ya generadas no cambian:
    cada una guarda las áreas con las que se generó (D59). Lista vacía: el proyecto queda sin áreas."""
    proyectos.reemplazar_areas(db, id_proyecto, datos)
    db.expire_all()
    return proyectos.presentar(proyectos.obtener(db, id_proyecto))
