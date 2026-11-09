"""El terreno del alta antes de registrarlo (CU04; figura 15; D79, D80): solo HTTP. Las reglas están en
`services.terrenos`, que usa las del motor."""

from fastapi import APIRouter, Depends

from app.api.dependencias import requiere
from app.core.permisos import Funcion
from app.models import Usuario
from app.schemas.errores import ErrorOut
from app.schemas.terrenos import ImportacionIn, ImportacionOut, MedicionIn, MedicionOut
from app.services import terrenos

router = APIRouter(tags=["terrenos"])

# «Registrar proyectos, delimitar terrenos y configurar parámetros» (p. 54).
REGISTRAR = requiere(Funcion.REGISTRAR_PROYECTOS)


@router.post(
    "/terrenos/medicion",
    summary="Medir y validar un terreno dibujado",
    response_model=MedicionOut,
    responses={422: {"model": ErrorOut}},
)
def medir_terreno(datos: MedicionIn, usuario: Usuario = Depends(REGISTRAR)) -> MedicionOut:
    """La superficie, el perímetro, los vértices y los lados de lo dibujado en el paso 2 del alta, en el
    sistema de cálculo, y las reglas de la geometría (CU04, 3.a y 6.a), con las del motor (D79). No guarda
    nada: lo que está mal va en `reglas` y `problemas`, con 200. 422 solo si el sistema de cálculo no
    sirve."""
    return terrenos.medir(datos)


@router.post(
    "/terrenos/importacion",
    summary="Importar los vértices del terreno desde una planilla",
    response_model=ImportacionOut,
    responses={422: {"model": ErrorOut}},
)
def importar_vertices(datos: ImportacionIn, usuario: Usuario = Depends(REGISTRAR)) -> ImportacionOut:
    """El polígono de una planilla de vértices (CSV) en POSGAR 2007 o en latitud y longitud, en EPSG:4326
    con la precisión completa (CU04, paso 3; D80). No guarda nada. 422 con los problemas por línea."""
    return terrenos.importar(datos)
