"""Control de acceso por dirección al inicio de sesión (CU01, 4.b; Seguridad, p. 53; D65).

- **Bloqueo:** tras 10 intentos fallidos consecutivos desde una dirección, se bloquea el inicio de
  sesión desde ella durante 30 min. Cuenta cualquier cuenta: es por dirección. El contador vuelve a
  cero con un ingreso correcto desde esa dirección o cuando vence el bloqueo. Las sesiones ya
  abiertas no se tocan.
- **Límite por minuto:** a lo sumo `SOLICITUDES_POR_MINUTO` pedidos por dirección en una ventana fija
  de un minuto, cumplan o no.

Los dos se aplican a los servicios que verifican una contraseña (el inicio de sesión y el cambio de
contraseña) y se controlan ANTES de verificarla, así lo bloqueado o limitado no gasta Argon2. Todo
vive en `acceso_direccion`, con upserts atómicos (dos fallos simultáneos no leen el mismo valor), y
cada fallo se confirma antes de responder el error.

La dirección es la que informa Nginx (`app.api.dependencias.direccion_cliente`, D64), y la hora, la
de `app.core.reloj`.
"""

import math
from datetime import datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core import reloj
from app.core.errores import ErrorApi
from app.models import AccesoDireccion

INTENTOS_ANTES_DEL_BLOQUEO = 10  # p. 53, CU01 4.b
DURACION_BLOQUEO = timedelta(minutes=30)  # p. 53
# La p. 53 pide limitar «la cantidad de solicitudes por minuto al servicio de inicio de sesión» sin
# dar un número: criterio de diseño. Alcanza para un humano que se equivoca y frena un barrido.
SOLICITUDES_POR_MINUTO = 10
VENTANA = timedelta(minutes=1)


def _segundos_hasta(momento: datetime, ahora: datetime) -> int:
    return max(1, math.ceil((momento - ahora).total_seconds()))


def _hora(momento: datetime) -> str:
    """La hora local de Córdoba (UTC−3, sin horario de verano) para el mensaje."""
    return momento.astimezone(reloj.CORDOBA).strftime("%H:%M")


def controlar(db: Session, direccion: str) -> None:
    """Antes de verificar una contraseña: cuenta la solicitud y responde 429 si la dirección está
    bloqueada o pasó el límite del minuto. Un bloqueo vencido se levanta acá, con el contador en
    cero."""
    ahora = reloj.ahora()
    fila = db.execute(
        text(
            """
            INSERT INTO acceso_direccion (direccion, intentos_fallidos, bloqueada_hasta, ventana_inicio,
                                          solicitudes_en_ventana)
            VALUES (:direccion, 0, NULL, :ahora, 1)
            ON CONFLICT (direccion) DO UPDATE SET
                solicitudes_en_ventana = CASE
                    WHEN acceso_direccion.ventana_inicio <= :ventana_vieja THEN 1
                    ELSE acceso_direccion.solicitudes_en_ventana + 1 END,
                ventana_inicio = CASE
                    WHEN acceso_direccion.ventana_inicio <= :ventana_vieja THEN :ahora
                    ELSE acceso_direccion.ventana_inicio END,
                intentos_fallidos = CASE
                    WHEN acceso_direccion.bloqueada_hasta <= :ahora THEN 0
                    ELSE acceso_direccion.intentos_fallidos END,
                bloqueada_hasta = CASE
                    WHEN acceso_direccion.bloqueada_hasta <= :ahora THEN NULL
                    ELSE acceso_direccion.bloqueada_hasta END
            RETURNING bloqueada_hasta, ventana_inicio, solicitudes_en_ventana
            """
        ),
        {"direccion": direccion, "ahora": ahora, "ventana_vieja": ahora - VENTANA},
    ).one()
    db.commit()
    if fila.bloqueada_hasta is not None:
        raise ErrorApi(
            429,
            "Se bloqueó el inicio de sesión desde esta dirección por demasiados intentos fallidos.",
            f"Vas a poder volver a intentar a las {_hora(fila.bloqueada_hasta)} (30 minutos después del "
            "último intento). Si no recordás la contraseña, pedile una temporal al director técnico.",
            encabezados={"Retry-After": str(_segundos_hasta(fila.bloqueada_hasta, ahora))},
        )
    if fila.solicitudes_en_ventana > SOLICITUDES_POR_MINUTO:
        raise ErrorApi(
            429,
            "Demasiadas solicitudes de inicio de sesión en un minuto.",
            "Esperá un minuto y volvé a intentar.",
            encabezados={"Retry-After": str(_segundos_hasta(fila.ventana_inicio + VENTANA, ahora))},
        )


def registrar_fallo(db: Session, direccion: str) -> None:
    """Un intento fallido más. Con el décimo consecutivo, la dirección queda bloqueada 30 min. Se
    confirma acá: el error que sigue no lo deshace."""
    ahora = reloj.ahora()
    db.execute(
        text(
            """
            UPDATE acceso_direccion SET
                intentos_fallidos = intentos_fallidos + 1,
                bloqueada_hasta = CASE
                    WHEN intentos_fallidos + 1 >= :intentos THEN CAST(:hasta AS timestamptz)
                    ELSE bloqueada_hasta END
            WHERE direccion = :direccion
            """
        ),
        {"direccion": direccion, "intentos": INTENTOS_ANTES_DEL_BLOQUEO, "hasta": ahora + DURACION_BLOQUEO},
    )
    db.commit()


def registrar_exito(db: Session, direccion: str) -> None:
    """Un ingreso correcto: el contador de fallos de la dirección vuelve a cero. Va en la misma
    transacción que lo que se haya hecho (la sesión nueva, la contraseña nueva)."""
    db.execute(
        text("UPDATE acceso_direccion SET intentos_fallidos = 0 WHERE direccion = :direccion"),
        {"direccion": direccion},
    )


def bloqueadas(db: Session) -> list[AccesoDireccion]:
    """Las direcciones con un bloqueo que no venció, de la que se libera antes a la que se libera
    después (D72). Las que tienen fallos pero no llegaron al décimo no están bloqueadas."""
    return list(
        db.scalars(
            select(AccesoDireccion)
            .where(AccesoDireccion.bloqueada_hasta > reloj.ahora())
            .order_by(AccesoDireccion.bloqueada_hasta, AccesoDireccion.direccion)
        )
    )


def desbloquear_desde_el_portal(db: Session, direccion: str) -> None:
    """El director técnico destraba una dirección bloqueada (D72): con todo el estudio detrás de la misma
    dirección pública, diez fallos de una persona dejan afuera a todos. 404 si no está bloqueada."""
    if direccion not in {fila.direccion for fila in bloqueadas(db)}:
        raise ErrorApi(
            404,
            f"La dirección {direccion} no está bloqueada.",
            "Puede que el bloqueo ya haya vencido o que otro director técnico la haya desbloqueado.",
        )
    desbloquear(db, direccion)


def segundos_restantes(fila: AccesoDireccion) -> int:
    return _segundos_hasta(fila.bloqueada_hasta, reloj.ahora())


def desbloquear(db: Session, direccion: str | None = None) -> int:
    """Borra el control de una dirección, o el de todas: la salida de emergencia de `app.admin` y el
    desbloqueo desde el portal. Devuelve cuántas filas borró."""
    consulta = delete(AccesoDireccion)
    if direccion is not None:
        consulta = consulta.where(AccesoDireccion.direccion == direccion)
    cantidad = db.execute(consulta).rowcount
    db.commit()
    return cantidad
