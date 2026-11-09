from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencias import requiere
from app.core.db import get_db
from app.core.permisos import Funcion
from app.models import Usuario
from app.schemas.errores import ErrorOut
from app.schemas.usuario import ContrasenaTemporalOut, UsuarioCambiosIn, UsuarioCreadoOut, UsuarioIn, UsuarioOut
from app.services import usuarios

router = APIRouter(tags=["usuarios"])

# CU02: solo el director técnico (p. 54, «Gestionar usuarios y roles»).
GESTIONAR = requiere(Funcion.GESTIONAR_USUARIOS)


@router.get("/usuarios", summary="Listar los usuarios", response_model=list[UsuarioOut])
def listar_usuarios(db: Session = Depends(get_db), usuario: Usuario = Depends(GESTIONAR)) -> list[UsuarioOut]:
    """CU02, paso 2: los usuarios con su rol y su estado, los activos primero."""
    return [UsuarioOut.model_validate(u) for u in usuarios.listar(db)]


@router.post(
    "/usuarios",
    summary="Dar de alta un usuario",
    status_code=201,
    response_model=UsuarioCreadoOut,
    responses={409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def crear_usuario(
    datos: UsuarioIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(GESTIONAR),
) -> UsuarioCreadoOut:
    """CU02, pasos 3 a 6: el usuario nuevo y su contraseña temporal, que vale 24 h y se muestra esta
    única vez para que el director técnico la entregue (en la base queda solo su hash). 409 si el correo
    ya está registrado (6.a)."""
    nuevo, temporal, vence = usuarios.crear_desde(db, datos)
    response.headers["Location"] = request.url_for("leer_usuario", id_usuario=nuevo.id_usuario).path
    return UsuarioCreadoOut(usuario=UsuarioOut.model_validate(nuevo), contrasena_temporal=temporal, vence=vence)


@router.get(
    "/usuarios/{id_usuario}",
    summary="Consultar un usuario",
    response_model=UsuarioOut,
    responses={404: {"model": ErrorOut}},
)
def leer_usuario(id_usuario: int, db: Session = Depends(get_db), usuario: Usuario = Depends(GESTIONAR)) -> UsuarioOut:
    return UsuarioOut.model_validate(usuarios.obtener(db, id_usuario))


@router.patch(
    "/usuarios/{id_usuario}",
    summary="Modificar un usuario, su rol o darlo de baja",
    response_model=UsuarioOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def modificar_usuario(
    id_usuario: int,
    cambios: UsuarioCambiosIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(GESTIONAR),
) -> UsuarioOut:
    """CU02, 3.a y 3.b: los datos, el rol o la baja. `activo: false` lo da de baja (nunca se borra) y
    cierra sus sesiones; un cambio de rol vale desde su pedido siguiente. 409 si el correo ya está
    registrado o si dejaría sin ningún director técnico activo. Reactivar es `POST …/reactivacion`."""
    return UsuarioOut.model_validate(usuarios.modificar(db, id_usuario, cambios))


@router.post(
    "/usuarios/{id_usuario}/contrasena-temporal",
    summary="Reemplazar la contraseña por una temporal",
    response_model=ContrasenaTemporalOut,
    responses={404: {"model": ErrorOut}},
)
def reemplazar_contrasena(
    id_usuario: int, db: Session = Depends(get_db), usuario: Usuario = Depends(GESTIONAR)
) -> ContrasenaTemporalOut:
    """Contraseña olvidada (p. 53): una temporal nueva, que vale 24 h, se muestra esta única vez y hay
    que reemplazar en el primer ingreso. Cierra las sesiones abiertas del usuario."""
    temporal, vence = usuarios.reemplazar_contrasena(db, id_usuario)
    return ContrasenaTemporalOut(contrasena_temporal=temporal, vence=vence)


@router.post(
    "/usuarios/{id_usuario}/reactivacion",
    summary="Reactivar un usuario",
    response_model=UsuarioCreadoOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}},
)
def reactivar_usuario(
    id_usuario: int, db: Session = Depends(get_db), usuario: Usuario = Depends(GESTIONAR)
) -> UsuarioCreadoOut:
    """Vuelve a dar de alta a un usuario desactivado con una contraseña temporal nueva, que vale 24 h y se
    muestra esta única vez (D72): no vuelve con la que tenía. 409 si ya está activo."""
    reactivado, temporal, vence = usuarios.reactivar(db, id_usuario)
    return UsuarioCreadoOut(usuario=UsuarioOut.model_validate(reactivado), contrasena_temporal=temporal, vence=vence)
