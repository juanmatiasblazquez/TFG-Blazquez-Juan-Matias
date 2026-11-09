"""Comandos de administración (D68). Corren dentro del contenedor de la API, con acceso al servidor:

    docker compose exec api python -m app.admin crear-director --nombre Ana --apellido Pérez --email ana@estudio.com.ar
    docker compose exec api python -m app.admin contrasena-temporal --email ana@estudio.com.ar
    docker compose exec api python -m app.admin desbloquear --todas
    docker compose exec api python -m app.admin desbloquear --direccion 203.0.113.7

- `crear-director`: el primer director técnico, o uno más. No hay credenciales por defecto en ningún
  entorno: el comando genera una contraseña temporal que vale 24 h, la imprime UNA sola vez y guarda
  solo su hash. Ningún comando acepta una contraseña elegida.
- `contrasena-temporal`: reemplaza la contraseña de cualquier usuario por una temporal, con las mismas
  reglas que en el portal. Sirve si el único director técnico olvidó la suya.
- `desbloquear`: levanta el bloqueo por intentos fallidos de una dirección o de todas (D65). Con todo
  el estudio detrás de la misma dirección, un bloqueo los deja a todos afuera.

La salida de `docker compose exec` va a la terminal de quien lo corre, no al log del contenedor.
"""

import argparse
import sys
from datetime import datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.errores import ErrorApi, campo_de, mensaje_de
from app.core.permisos import Rol
from app.models import Usuario
from app.schemas.usuario import UsuarioIn, validar_email
from app.services import acceso, usuarios


def _hora_local(momento: datetime) -> str:
    """Córdoba: UTC−3, sin horario de verano."""
    return (momento - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M")


def _mostrar_temporal(usuario: Usuario, temporal: str, vence: datetime) -> None:
    print()
    print(f"  Usuario:             {usuario.nombre} {usuario.apellido} <{usuario.email}> ({usuario.rol})")
    print(f"  Contraseña temporal: {temporal}")
    print(f"  Vence:               {_hora_local(vence)} (hora de Córdoba)")
    print()
    print("  Se muestra esta única vez: en la base queda solo su hash. En el primer ingreso hay que")
    print("  reemplazarla por una propia.")
    print()


def crear_director(nombre: str, apellido: str, email: str) -> int:
    # Las mismas reglas que el alta por la API (CU02): largos, correo y rol.
    try:
        datos = UsuarioIn(nombre=nombre, apellido=apellido, email=email, rol=Rol.DIRECTOR_TECNICO)
    except ValidationError as error:
        # Con los mensajes en español de la API (D32).
        for problema in error.errors():
            print(f"{campo_de(problema['loc'])}: {mensaje_de(problema)}")
        return 1
    with SessionLocal() as db:
        try:
            usuario, temporal, vence = usuarios.crear_desde(db, datos)
        except ErrorApi as error:
            print(f"{error.cuerpo.causa} Para darle una contraseña nueva: contrasena-temporal --email {email}")
            return 1
        _mostrar_temporal(usuario, temporal, vence)
    return 0


def contrasena_temporal(email: str) -> int:
    with SessionLocal() as db:
        usuario = db.scalar(select(Usuario).where(Usuario.email == validar_email(email)))
        if usuario is None:
            print(f"No hay ningún usuario con el correo {email}.")
            return 1
        temporal, vence = usuarios.reemplazar_contrasena(db, usuario.id_usuario)
        _mostrar_temporal(usuario, temporal, vence)
        if not usuario.activo:
            print("  Ojo: el usuario está desactivado. Reactivalo desde la gestión de usuarios.")
    return 0


def desbloquear(direccion: str | None) -> int:
    with SessionLocal() as db:
        cantidad = acceso.desbloquear(db, direccion)
    objetivo = f"la dirección {direccion}" if direccion else "todas las direcciones"
    print(f"Listo: se borró el control de acceso de {objetivo} ({cantidad} fila(s)).")
    return 0


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.admin", description="Administración de usuarios y accesos.")
    comandos = parser.add_subparsers(dest="comando", required=True)

    director = comandos.add_parser("crear-director", help="Crea un director técnico con una contraseña temporal.")
    director.add_argument("--nombre", required=True)
    director.add_argument("--apellido", required=True)
    director.add_argument("--email", required=True)

    temporal = comandos.add_parser("contrasena-temporal", help="Reemplaza la contraseña de un usuario por una temporal.")
    temporal.add_argument("--email", required=True)

    bloqueo = comandos.add_parser("desbloquear", help="Levanta el bloqueo por intentos fallidos.")
    cual = bloqueo.add_mutually_exclusive_group(required=True)
    cual.add_argument("--direccion")
    cual.add_argument("--todas", action="store_true")

    args = parser.parse_args(argumentos)
    try:
        if args.comando == "crear-director":
            return crear_director(args.nombre, args.apellido, args.email)
        if args.comando == "contrasena-temporal":
            return contrasena_temporal(args.email)
        return desbloquear(None if args.todas else args.direccion)
    except ValueError as error:
        print(error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
