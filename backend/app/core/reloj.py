"""La hora de las reglas de seguridad (D63, D65, D70).

Es la única fuente de hora de los vencimientos de la sesión (12 h), de la contraseña temporal (24 h) y
de los enlaces compartidos (hasta 30 días), del bloqueo por intentos fallidos (30 min) y del límite por
minuto. Siempre en UTC y con zona horaria; `hoy` da la fecha de Córdoba, la del estudio.

Las pruebas la adelantan con `adelantar` (el fixture `reloj` de `tests/conftest.py`) en lugar de
dormir. Las fechas que solo registran cuándo pasó algo (`fecha_alta`, `fecha_generacion`) siguen
saliendo de `now()` de la base, porque no deciden nada.
"""

from datetime import UTC, date, datetime, time, timedelta, timezone

# La hora de Córdoba: UTC−3 todo el año (la Argentina no tiene horario de verano desde 2009). Fija, para
# no depender de la base de zonas horarias de la imagen.
CORDOBA = timezone(timedelta(hours=-3), "UTC-03:00")

_desfase = timedelta(0)


def ahora() -> datetime:
    return datetime.now(UTC) + _desfase


def hoy() -> date:
    """La fecha de hoy en Córdoba."""
    return ahora().astimezone(CORDOBA).date()


def fin_del_dia(dia: date) -> datetime:
    """El último instante de ese día en Córdoba (23:59:59,999999), en UTC. Es inclusivo: así, mostrado
    en la hora de Córdoba, sigue siendo ese día."""
    return datetime.combine(dia, time(23, 59, 59, 999999), CORDOBA).astimezone(UTC)


def adelantar(tiempo: timedelta) -> None:
    """Solo para las pruebas: corre el reloj hacia adelante."""
    global _desfase
    _desfase += tiempo


def reiniciar() -> None:
    """Solo para las pruebas: vuelve a la hora real."""
    global _desfase
    _desfase = timedelta(0)
