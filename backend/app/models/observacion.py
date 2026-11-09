"""Observaciones y sus respuestas (ER `observacion` y `respuesta_observacion`, p. 47; CU11, CU12, RF17;
migración 0012, D69).

Los valores salen del documento:
- el tipo y la criticidad, del acta de observaciones (Anexo 1.5, formulario AO-05);
- el estado, de los casos de uso (CU11: «abierta»; CU12: «respondida») y de las operaciones de la clase
  `Observacion` (p. 46: `cerrar()`, `reabrir()`), con la `fecha_cierre` del ER;
- la acción de la respuesta, del CU12 (3.a, un recálculo; 3.b, una justificación o aclaración) y del
  acta («Recálculo parcial de un sector»).

Una observación cuelga de una versión pero no es parte de ella: su estado cambia con el ciclo de revisión.
La base solo admite cambiar `estado` y `fecha_cierre` (trigger `observacion_solo_estado`). Una respuesta
no se modifica nunca (el trigger de la 0002, D28).
"""

from datetime import datetime
from enum import StrEnum

from geoalchemy2 import WKBElement
from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.alternativa import Alternativa, VersionAlternativa
from app.models.tipos import Fecha, geometria
from app.models.usuario import FechaDeReloj, Usuario


class TipoObservacion(StrEnum):
    """Anexo 1.5: «normativa / dimensional / conectividad / comercial / gráfica»."""

    NORMATIVA = "normativa"
    DIMENSIONAL = "dimensional"
    CONECTIVIDAD = "conectividad"
    COMERCIAL = "comercial"
    GRAFICA = "grafica"


class Criticidad(StrEnum):
    """Anexo 1.5: «bloqueante / sugerida». Solo una bloqueante sin responder impide compartir (p. 45)."""

    BLOQUEANTE = "bloqueante"
    SUGERIDA = "sugerida"


class EstadoObservacion(StrEnum):
    """`abierta` (CU11, paso 5) → `respondida` (CU12, paso 5) → `cerrada` (`cerrar()`, p. 46: la
    conformidad del emisor, Anexo 1.5). Una respondida se puede reabrir (`reabrir()`); una cerrada no."""

    ABIERTA = "abierta"
    RESPONDIDA = "respondida"
    CERRADA = "cerrada"


class AccionRespuesta(StrEnum):
    """CU12: 3.a, un recálculo de un sector (CU09), que deja una versión resultante; 3.b, una
    justificación o una aclaración, en el comentario. El acta (Anexo 1.5) suma el «ajuste local» y la
    «regeneración completa», que el sistema no tiene (D69)."""

    RECALCULO_PARCIAL = "recalculo_parcial"
    JUSTIFICACION = "justificacion"
    ACLARACION = "aclaracion"


class Observacion(Base):
    """Una observación sobre una versión (ER `observacion`). El sector afectado es opcional (RF17)."""

    __tablename__ = "observacion"
    __table_args__ = (
        CheckConstraint("tipo IN ('normativa', 'dimensional', 'conectividad', 'comercial', 'grafica')", name="tipo"),
        CheckConstraint("criticidad IN ('bloqueante', 'sugerida')", name="criticidad"),
        CheckConstraint("estado IN ('abierta', 'respondida', 'cerrada')", name="estado"),
    )

    id_observacion: Mapped[int] = mapped_column(primary_key=True)
    id_version: Mapped[int] = mapped_column(ForeignKey("version_alternativa.id_version"), index=True)
    id_usuario_emisor: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"))
    tipo: Mapped[str] = mapped_column(String(15))
    criticidad: Mapped[str] = mapped_column(String(10))
    descripcion: Mapped[str] = mapped_column(Text)
    sector: Mapped[WKBElement | None] = mapped_column(geometria("POLYGON"))
    estado: Mapped[str] = mapped_column(String(12))
    fecha_emision: Mapped[Fecha]
    fecha_cierre: Mapped[datetime | None] = mapped_column(FechaDeReloj)

    version: Mapped[VersionAlternativa] = relationship(back_populates="observaciones")
    emisor: Mapped[Usuario] = relationship()
    respuestas: Mapped[list["RespuestaObservacion"]] = relationship(
        back_populates="observacion", order_by="RespuestaObservacion.id_respuesta"
    )


class RespuestaObservacion(Base):
    """Lo que se hizo ante una observación (ER `respuesta_observacion`). Con un recálculo, la versión que
    resultó (CU12, paso 5): un CHECK exige que `recalculo_parcial` la tenga y las demás acciones no."""

    __tablename__ = "respuesta_observacion"
    __table_args__ = (
        CheckConstraint("accion IN ('recalculo_parcial', 'justificacion', 'aclaracion')", name="accion"),
        CheckConstraint("(accion = 'recalculo_parcial') = (id_version_resultante IS NOT NULL)", name="version_resultante"),
    )

    id_respuesta: Mapped[int] = mapped_column(primary_key=True)
    id_observacion: Mapped[int] = mapped_column(ForeignKey("observacion.id_observacion"), index=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"))
    id_version_resultante: Mapped[int | None] = mapped_column(ForeignKey("version_alternativa.id_version"))
    accion: Mapped[str] = mapped_column(String(20))
    descripcion: Mapped[str] = mapped_column(Text)
    fecha: Mapped[Fecha]

    observacion: Mapped[Observacion] = relationship(back_populates="respuestas")
    usuario: Mapped[Usuario] = relationship()
    version_resultante: Mapped[VersionAlternativa | None] = relationship()


# --- Reglas sobre las observaciones de una alternativa (copia única, D69) --------------------------
# Son funciones de los objetos, sin consultas propias: las usan el proyecto (los contadores), la selección
# y los enlaces (CU14) y el servicio de observaciones, sin importarse entre ellos.


def de_la_alternativa(alternativa: Alternativa) -> list[Observacion]:
    """Todas las observaciones de la alternativa, de todas sus versiones, en el orden en que se
    registraron."""
    return sorted((o for v in alternativa.versiones for o in v.observaciones), key=lambda o: o.id_observacion)


def designaciones(alternativa: Alternativa) -> dict[int, str]:
    """O-1, O-2… por alternativa, en el orden de registro (p. 50). No se guardan: las observaciones no se
    borran nunca, así que el número no cambia."""
    return {o.id_observacion: f"O-{k}" for k, o in enumerate(de_la_alternativa(alternativa), 1)}


def bloquea(observacion: Observacion) -> bool:
    """Qué observación impide compartir: una bloqueante sin responder (p. 45; decisión del autor sobre
    el CU14, que decía «observaciones abiertas», D29). Una respondida ya no bloquea, aunque no se haya
    cerrado; una reabierta vuelve a bloquear."""
    return observacion.criticidad == Criticidad.BLOQUEANTE and observacion.estado == EstadoObservacion.ABIERTA


def abiertas(alternativa: Alternativa) -> list[Observacion]:
    return [o for o in de_la_alternativa(alternativa) if o.estado == EstadoObservacion.ABIERTA]


def bloqueantes(alternativa: Alternativa) -> list[Observacion]:
    """`tieneObservacionesBloqueantes()` (p. 45, paso 3): sobre todas las versiones de la alternativa,
    como el loop del diagrama, y no solo sobre la vigente: una versión nueva no responde una observación."""
    return [o for o in de_la_alternativa(alternativa) if bloquea(o)]
