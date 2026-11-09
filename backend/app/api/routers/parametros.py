from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencias import requiere
from app.core.db import get_db
from app.core.permisos import Funcion
from app.models import Usuario
from app.schemas.errores import ErrorOut
from app.schemas.parametros import (
    CoherenciaOut,
    ConjuntoParametrosOut,
    ParametrosIn,
    ParametrosOut,
    ReferenciaParametrosOut,
)
from app.services import parametros, proyectos

router = APIRouter(tags=["parametros"])

# «Consultar alternativas» (p. 54).
CONSULTAR = requiere(Funcion.CONSULTAR_ALTERNATIVAS)
# «Registrar proyectos, delimitar terrenos y configurar parámetros» (p. 54).
REGISTRAR = requiere(Funcion.REGISTRAR_PROYECTOS)


@router.get(
    "/parametros/referencia",
    summary="Valores de referencia de un loteo, con su fuente",
    response_model=ReferenciaParametrosOut,
)
def leer_referencia(usuario: Usuario = Depends(CONSULTAR)) -> ReferenciaParametrosOut:
    """Los valores con los que arranca el formulario de parámetros (CU05, paso 1), y al lado
    de cada uno el artículo de la norma o «a validar» (D23). Salen del motor (D36)."""
    return parametros.referencia()


@router.post(
    "/proyectos/{id_proyecto}/parametros",
    summary="Configurar los parámetros de un proyecto",
    status_code=201,
    response_model=ParametrosOut,
    responses={404: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def configurar_parametros(
    id_proyecto: int,
    datos: ParametrosIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(REGISTRAR),
) -> ParametrosOut:
    """CU05: crea una versión nueva del conjunto, que pasa a ser la vigente. Las alternativas ya
    generadas conservan la suya. 422 con el campo si los valores no son coherentes (3.a)."""
    proyectos.configurar_parametros(db, id_proyecto, datos)
    # Lo que se responde se lee de la base, igual que en el GET del proyecto.
    db.expire_all()
    return parametros.presentar_parametros(proyectos.obtener(db, id_proyecto).parametros_vigentes())


@router.get(
    "/proyectos/{id_proyecto}/parametros",
    summary="Versiones del conjunto de parámetros",
    response_model=list[ConjuntoParametrosOut],
    responses={404: {"model": ErrorOut}},
)
def listar_versiones(
    id_proyecto: int, db: Session = Depends(get_db), usuario: Usuario = Depends(CONSULTAR)
) -> list[ConjuntoParametrosOut]:
    """Las versiones del conjunto, de la última a la primera, con las alternativas que conservan cada una
    (figura 16, «Versiones del conjunto»; D82)."""
    return parametros.versiones(proyectos.obtener(db, id_proyecto))


@router.post(
    "/parametros/validacion",
    summary="Validar un conjunto de parámetros sin guardarlo",
    response_model=CoherenciaOut,
    responses={422: {"model": ErrorOut}},
)
def validar_parametros(datos: ParametrosIn, usuario: Usuario = Depends(REGISTRAR)) -> CoherenciaOut:
    """Las reglas de coherencia de la p. 49 y las del motor, cumplidas o no, mientras se editan los
    parámetros (figura 16, «Validación de coherencia»; D78). No guarda nada: 200 con los problemas por
    campo, los mismos que daría guardarlos. Un valor con otro tipo o fuera de su columna da 422, como al
    guardar."""
    return parametros.coherencia(datos)
