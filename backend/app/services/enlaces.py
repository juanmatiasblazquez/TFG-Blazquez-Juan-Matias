"""Seleccionar alternativas, compartirlas y revocar el enlace (CU14, RF16; secuencia de la p. 45;
Seguridad, p. 54; D70).

- **Seleccionar** (p. 45, pasos 1 a 8): las alternativas que se presentarán al cliente pasan a
  `seleccionada`. Si alguna tiene una observación bloqueante sin responder, 409 y no cambia nada
  (CU14, 2.a). Las que estaban seleccionadas y no se eligieron vuelven a `generada`.
- **Compartir** (pasos 9 a 15): un enlace con las versiones vigentes de las seleccionadas, atado a ellas
  (`enlace_version`): lo que se genere después no cambia lo que ve el cliente. La fecha de vencimiento es
  obligatoria y de 30 días como máximo (p. 54); el enlace vale hasta el final de ese día en Córdoba.
- **El token** es aleatorio (`secrets.token_urlsafe(32)`, 256 bits) y se muestra una sola vez. La base
  guarda su SHA-256, con la misma función que la sesión (`sesiones.hash_token`, D63).
- **Validar** (p. 45, pasos 18 a 23): un token que no existe da 404, y uno vencido o revocado, 410 (CU15,
  2.a), con el mismo mensaje. Un acceso válido suma al contador (`registrarAcceso()`).
- **La descripción para el cliente** (p. 51; D76): se escribe en la alternativa y se copia en
  `enlace_version` al compartir. Cambiarla después no cambia lo que ya ve el cliente.
"""

import secrets
from datetime import timedelta
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import reloj
from app.core.errores import ErrorApi
from app.models import Alternativa, EnlaceCompartido, EnlaceVersion, Usuario, VersionAlternativa
from app.models.alternativa import EstadoAlternativa
from app.models.observacion import bloqueantes, designaciones
from app.schemas.enlace import EnlaceIn, EnlaceOut, SeleccionIn, SeleccionOut, VersionCompartida
from app.services import proyectos
from app.services.sesiones import hash_token

# p. 54: «una fecha de vencimiento obligatoria (como máximo 30 días)».
VIGENCIA_MAXIMA = timedelta(days=30)

NO_DISPONIBLE = "Este enlace no está disponible."
SUGERENCIA_NO_DISPONIBLE = "Puede haber vencido o haber sido revocado. Pedile al estudio que te comparta uno nuevo."

Estado = Literal["vigente", "vencido", "revocado"]


# --- La descripción para el cliente (p. 51; D76) ---------------------------------------------------


def describir(db: Session, id_alternativa: int, descripcion: str | None) -> Alternativa:
    """`PATCH /alternativas/{id}`: lo que el estudio le cuenta al cliente de este trazado. Vacía, se borra."""
    alternativa = db.get(Alternativa, id_alternativa)
    if alternativa is None:
        raise ErrorApi(404, f"No existe la alternativa {id_alternativa}.")
    alternativa.descripcion = (descripcion or "").strip() or None
    db.commit()
    return alternativa


# --- Seleccionar (CU14, paso 1) ---------------------------------------------------------------------


def seleccionar(db: Session, id_proyecto: int, datos: SeleccionIn) -> SeleccionOut:
    """`PATCH /proyectos/{id}/seleccion` (p. 45, paso 2): la selección pasa a ser exactamente la pedida."""
    proyecto = proyectos.obtener(db, id_proyecto)
    _bloquear(db, id_proyecto)
    por_codigo = {a.codigo: a for a in proyecto.alternativas}
    pedidas = list(dict.fromkeys(datos.alternativas))
    inexistentes = [
        (f"alternativas[{k}]", f"El proyecto no tiene una alternativa {codigo}.")
        for k, codigo in enumerate(pedidas)
        if codigo not in por_codigo
    ]
    if inexistentes:
        raise ErrorApi(422, "Alguna alternativa elegida no existe.", "Elegí entre las alternativas del proyecto.", inexistentes)
    _exigir_sin_bloqueantes([(f"alternativas[{k}]", por_codigo[codigo]) for k, codigo in enumerate(pedidas)])
    for alternativa in proyecto.alternativas:
        if alternativa.codigo in pedidas:
            alternativa.estado = EstadoAlternativa.SELECCIONADA
        elif alternativa.estado == EstadoAlternativa.SELECCIONADA:
            alternativa.estado = EstadoAlternativa.GENERADA
    db.commit()
    return SeleccionOut(alternativas=[proyectos.resumen_alternativa(a) for a in proyecto.alternativas])


def _exigir_sin_bloqueantes(alternativas: list[tuple[str, Alternativa]]) -> None:
    """CU14, 2.a, con la regla de la p. 45: 409 si alguna tiene una observación bloqueante sin
    responder, con un problema por alternativa que nombra cuáles."""
    problemas = []
    for campo, alternativa in alternativas:
        pendientes = bloqueantes(alternativa)
        if pendientes:
            nombres = designaciones(alternativa)
            lista = ", ".join(f"{nombres[o.id_observacion]} ({o.tipo})" for o in pendientes)
            cantidad = "una observación bloqueante" if len(pendientes) == 1 else f"{len(pendientes)} observaciones bloqueantes"
            problemas.append((campo, f"La alternativa {alternativa.codigo} tiene {cantidad} sin responder: {lista}."))
    if problemas:
        raise ErrorApi(
            409,
            "No se puede compartir una alternativa con observaciones bloqueantes sin responder."
            if len(problemas) == 1
            else "No se pueden compartir alternativas con observaciones bloqueantes sin responder.",
            "Respondé esas observaciones antes de seleccionarla para el cliente (CU14, 2.a).",
            problemas,
        )


# --- Compartir (CU14, pasos 3 a 5) ------------------------------------------------------------------


def compartir(db: Session, id_proyecto: int, datos: EnlaceIn, usuario: Usuario) -> tuple[EnlaceCompartido, str]:
    """`POST /proyectos/{id}/enlaces` (p. 45, pasos 10 a 14): el enlace con las versiones vigentes de las
    alternativas seleccionadas, y su token, que no se guarda."""
    proyecto = proyectos.obtener(db, id_proyecto)
    _bloquear(db, id_proyecto)
    hoy = reloj.hoy()
    if datos.fecha_vencimiento < hoy:
        raise _fecha_invalida("Ya pasó: elegí una fecha desde hoy.")
    if datos.fecha_vencimiento > hoy + VIGENCIA_MAXIMA:
        raise _fecha_invalida(f"Puede ser como máximo el {hoy + VIGENCIA_MAXIMA:%d/%m/%Y}: 30 días desde hoy (p. 54).")
    seleccionadas = [a for a in proyecto.alternativas if a.estado == EstadoAlternativa.SELECCIONADA]
    if not seleccionadas:
        raise ErrorApi(
            422,
            "No hay alternativas seleccionadas para compartir.",
            "Marcá una o más alternativas como seleccionadas (CU14, paso 1).",
        )
    # Seleccionar ya lo controló; registrar o reabrir una observación saca la alternativa de la selección.
    # Se vuelve a controlar igual: es lo último antes de darle acceso al cliente.
    _exigir_sin_bloqueantes([(f"alternativas.{a.codigo}", a) for a in seleccionadas])
    token = secrets.token_urlsafe(32)
    enlace = EnlaceCompartido(
        proyecto=proyecto,
        usuario=usuario,
        token=hash_token(token),
        fecha_vencimiento=reloj.fin_del_dia(datos.fecha_vencimiento),
        versiones=[EnlaceVersion(version=_vigente(db, a), descripcion=a.descripcion) for a in seleccionadas],
    )
    db.add(enlace)
    db.commit()
    return enlace, token


def _fecha_invalida(mensaje: str) -> ErrorApi:
    return ErrorApi(
        422,
        "La fecha de vencimiento no sirve.",
        "El enlace vale hasta el final del día elegido, y como máximo 30 días.",
        [("fecha_vencimiento", mensaje)],
    )


# --- La lista y la revocación -----------------------------------------------------------------------


def listar(db: Session, id_proyecto: int) -> list[EnlaceOut]:
    """Los enlaces del proyecto, del más nuevo al más viejo, con su estado."""
    proyectos.obtener(db, id_proyecto)
    enlaces = db.scalars(
        select(EnlaceCompartido)
        .where(EnlaceCompartido.id_proyecto == id_proyecto)
        .order_by(EnlaceCompartido.fecha_creacion.desc(), EnlaceCompartido.id_enlace.desc())
    )
    return [presentar(enlace) for enlace in enlaces]


def obtener(db: Session, id_enlace: int) -> EnlaceCompartido:
    enlace = db.get(EnlaceCompartido, id_enlace)
    if enlace is None:
        raise ErrorApi(404, f"No existe el enlace {id_enlace}.")
    return enlace


def revocar(db: Session, id_enlace: int) -> EnlaceCompartido:
    """`revocar()` (p. 46): en cualquier momento (p. 54), sin vuelta atrás. Revocar uno revocado no cambia
    nada."""
    enlace = obtener(db, id_enlace)
    enlace.revocado = True
    db.commit()
    return enlace


def estado_de(enlace: EnlaceCompartido) -> Estado:
    """`estaVigente()` (p. 46), con el motivo: revocado manda sobre vencido."""
    if enlace.revocado:
        return "revocado"
    # `fecha_vencimiento` es el último instante del día elegido (`reloj.fin_del_dia`): vale hasta ese instante.
    if reloj.ahora() > enlace.fecha_vencimiento:
        return "vencido"
    return "vigente"


def presentar(enlace: EnlaceCompartido) -> EnlaceOut:
    versiones = sorted(
        (
            VersionCompartida(
                id_version=ev.id_version,
                codigo_alternativa=ev.version.alternativa.codigo,
                numero_version=ev.version.numero,
            )
            for ev in enlace.versiones
        ),
        key=lambda v: (len(v.codigo_alternativa), v.codigo_alternativa),
    )
    return EnlaceOut(
        id_enlace=enlace.id_enlace,
        estado=estado_de(enlace),
        fecha_creacion=enlace.fecha_creacion,
        fecha_vencimiento=enlace.fecha_vencimiento,
        creado_por=proyectos.resumen_usuario(enlace.usuario),
        versiones=versiones,
        ultimo_acceso=enlace.ultimo_acceso,
        cantidad_accesos=enlace.cantidad_accesos,
    )


# --- El acceso del cliente (CU15) -------------------------------------------------------------------


def vigente(db: Session, token: str) -> EnlaceCompartido:
    """`validar(token)` (p. 45, paso 18): el enlace del token, si sigue vigente. 404 si no existe; 410 si
    venció o fue revocado (paso 20; CU15, 2.a). Los dos con el mismo mensaje."""
    enlace = db.scalar(select(EnlaceCompartido).where(EnlaceCompartido.token == hash_token(token)))
    if enlace is None:
        raise ErrorApi(404, NO_DISPONIBLE, SUGERENCIA_NO_DISPONIBLE)
    if estado_de(enlace) != "vigente":
        raise ErrorApi(410, NO_DISPONIBLE, SUGERENCIA_NO_DISPONIBLE)
    return enlace


def registrar_acceso(db: Session, enlace: EnlaceCompartido) -> None:
    """`registrarAcceso()` (p. 45, paso 22): cuándo fue el último y cuántos van, en un UPDATE atómico."""
    db.execute(
        update(EnlaceCompartido)
        .where(EnlaceCompartido.id_enlace == enlace.id_enlace)
        .values(cantidad_accesos=EnlaceCompartido.cantidad_accesos + 1, ultimo_acceso=reloj.ahora())
    )
    db.commit()


# --- Auxiliares -------------------------------------------------------------------------------------


def _bloquear(db: Session, id_proyecto: int) -> None:
    """Bloquea las alternativas del proyecto hasta el final de la transacción: una observación que se
    registra mientras tanto espera, y no se cuela en un enlace."""
    db.execute(select(Alternativa.id_alternativa).where(Alternativa.id_proyecto == id_proyecto).with_for_update())


def _vigente(db: Session, alternativa: Alternativa) -> VersionAlternativa:
    return db.scalar(
        select(VersionAlternativa)
        .where(VersionAlternativa.id_alternativa == alternativa.id_alternativa)
        .order_by(VersionAlternativa.numero.desc())
        .limit(1)
    )
