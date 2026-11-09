"""Alternativas y sus versiones (ER, p. 47). Una versión y todo lo que cuelga de ella es
INMUTABLE (RNF04): lo garantiza un trigger de la migración 0002, no solo este código (D28)."""

from decimal import Decimal
from enum import StrEnum

from geoalchemy2 import WKBElement
from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.parametros import ConjuntoParametros, JerarquiaCorredor
from app.models.proyecto import Proyecto, PuntoAcceso
from app.models.tipos import Fecha, geometria
from app.models.usuario import Usuario


class EstadoAlternativa(StrEnum):
    """El estado de una alternativa (ER `alternativa.estado`; migración 0012, D69). El documento tipa
    `estado: EstadoAlternativa` sin enumerar sus valores: salen de los casos de uso. Las transiciones
    viven en `services.observaciones` (observar, responder, reabrir) y en `services.enlaces.seleccionar`."""

    # Al generarse, y cuando todas sus observaciones quedaron respondidas (D69).
    GENERADA = "generada"
    # Con una observación registrada o reabierta (CU11, paso 5).
    OBSERVADA = "observada"
    # Marcada para presentar al cliente (CU14, paso 1; `seleccionar()`, p. 45, paso 7).
    SELECCIONADA = "seleccionada"


class TipoVersion(StrEnum):
    """Cómo nació una versión (migración 0010, D62). No está en el ER (D29)."""

    # La versión 1 de una alternativa (CU06).
    GENERADA = "generada"
    # La n + 1 de un recálculo con sector fijado (CU09, D56).
    RECALCULADA = "recalculada"
    # La n + 1 que vuelve a una versión anterior, sin correr el motor (D60).
    COPIA = "copia"


class Alternativa(Base):
    """Alternativa de un proyecto (ER `alternativa`). `codigo` es A, B, C… por proyecto, como la
    «Alternativa B» de la p. 49."""

    __tablename__ = "alternativa"
    __table_args__ = (
        UniqueConstraint("id_proyecto", "codigo"),
        CheckConstraint("estado IN ('generada', 'observada', 'seleccionada')", name="estado"),
    )

    id_alternativa: Mapped[int] = mapped_column(primary_key=True)
    id_proyecto: Mapped[int] = mapped_column(ForeignKey("proyecto.id_proyecto"))
    codigo: Mapped[str] = mapped_column(String(5))
    # Uno de `EstadoAlternativa` (D69).
    estado: Mapped[str] = mapped_column(String(20))
    fecha_creacion: Mapped[Fecha]
    # Lo que el estudio le cuenta al cliente de este trazado (p. 51; migración 0013, D76). No está en el
    # ER (D29). Se copia en el enlace al compartir: lo que ve el cliente no cambia después (D70).
    descripcion: Mapped[str | None] = mapped_column(Text)

    proyecto: Mapped[Proyecto] = relationship(back_populates="alternativas")
    versiones: Mapped[list["VersionAlternativa"]] = relationship(
        back_populates="alternativa", order_by="VersionAlternativa.numero"
    )

    def version_vigente(self) -> "VersionAlternativa":
        return self.versiones[-1]


class VersionAlternativa(Base):
    """Una versión generada (ER `version_alternativa`). Los indicadores llevan los nombres del
    ER (D29). `version_motor` no está en el ER: sin ella no se sabe con qué motor se puede
    reproducir la versión (D05, D28)."""

    __tablename__ = "version_alternativa"
    __table_args__ = (
        UniqueConstraint("id_alternativa", "numero"),
        CheckConstraint("tipo IN ('generada', 'recalculada', 'copia')", name="tipo"),
    )

    id_version: Mapped[int] = mapped_column(primary_key=True)
    id_alternativa: Mapped[int] = mapped_column(ForeignKey("alternativa.id_alternativa"))
    id_conjunto: Mapped[int] = mapped_column(ForeignKey("conjunto_parametros.id_conjunto"))
    # Versión de la que sale un recálculo (CU09); nula en la versión 1.
    id_version_origen: Mapped[int | None] = mapped_column(ForeignKey("version_alternativa.id_version"))
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"))
    numero: Mapped[int]
    # Generada, recalculada o copia (`TipoVersion`, D62): explícito desde la 0010.
    tipo: Mapped[str] = mapped_column(String(12))
    patron_red: Mapped[str] = mapped_column(String(15))
    orientacion_grados: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    semilla: Mapped[int]
    geom_fijada: Mapped[WKBElement | None] = mapped_column(geometria("MULTIPOLYGON"))
    cumple_restricciones: Mapped[bool]
    cantidad_celdas: Mapped[int]
    superficie_aprovechable_m2: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    porcentaje_circulacion: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    porcentaje_espacio_verde: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    longitud_red_m: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # Nula si no hay celdas útiles a las que medir la distancia.
    distancia_media_acceso_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    # Indicadores de los remanentes (D41), fuera del ER (migración 0004, D29). Nulos en las
    # versiones generadas antes del motor 0.4.0.
    superficie_espacio_verde_m2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    superficie_espacio_libre_m2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    porcentaje_cesion: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    # Los lotes que pasan la superficie máxima (D47) y la longitud de avenidas sobre la de la red
    # (Ley 4146, art. 12; D48), fuera del ER (migración 0006). Nulos antes del motor 0.6.0.
    cantidad_lotes_grandes: Mapped[int | None]
    porcentaje_avenidas: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # La distancia media y la máxima de los lotes al espacio verde más cercano, por la red (D51),
    # fuera del ER (migración 0007). Nulas antes del motor 0.7.0, o sin lotes o sin verde.
    distancia_media_verde_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    distancia_maxima_verde_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    # El verde que computa para la cesión, sin las puntas del art. 48 (D55), fuera del ER (migración
    # 0008). Nulo antes del motor 0.8.0.
    superficie_verde_computable_m2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    duracion_ms: Mapped[int]
    version_motor: Mapped[str] = mapped_column(String(20))
    fecha_generacion: Mapped[Fecha]

    alternativa: Mapped[Alternativa] = relationship(back_populates="versiones")
    conjunto: Mapped[ConjuntoParametros] = relationship()
    usuario: Mapped[Usuario] = relationship()
    nodos: Mapped[list["NodoRed"]] = relationship(order_by="NodoRed.id_nodo")
    tramos: Mapped[list["TramoCirculacion"]] = relationship(order_by="TramoCirculacion.id_tramo")
    manzanas: Mapped[list["Manzana"]] = relationship(order_by="Manzana.id_manzana")
    celdas: Mapped[list["Celda"]] = relationship(order_by="Celda.id_celda")
    incumplimientos: Mapped[list["Incumplimiento"]] = relationship(order_by="Incumplimiento.id_incumplimiento")
    # Las áreas reservadas con las que se generó (D59), en el orden de la solicitud (R1, R2…).
    areas_reservadas: Mapped[list["AreaReservadaVersion"]] = relationship(
        order_by="AreaReservadaVersion.id_area_version"
    )
    # Las observaciones registradas sobre esta versión (CU11, D69). No son parte de la versión: cuelgan
    # de ella y cambian de estado sin tocarla.
    observaciones: Mapped[list["Observacion"]] = relationship(  # noqa: F821
        back_populates="version", order_by="Observacion.id_observacion"
    )


class NodoRed(Base):
    """Intersección o extremo de la red (ER `nodo_red`). Coincide con 0..1 punto de acceso."""

    __tablename__ = "nodo_red"

    id_nodo: Mapped[int] = mapped_column(primary_key=True)
    id_version: Mapped[int] = mapped_column(ForeignKey("version_alternativa.id_version"), index=True)
    id_punto_acceso: Mapped[int | None] = mapped_column(ForeignKey("punto_acceso.id_punto_acceso"))
    geom: Mapped[WKBElement] = mapped_column(geometria("POINT"))

    punto_acceso: Mapped[PuntoAcceso | None] = relationship()


class TramoCirculacion(Base):
    """Tramo de la red entre dos nodos (ER `tramo_circulacion`). `geom` es la superficie de calle
    del tramo: MultiPolygon y opcional, porque con la grilla oblicua un tramo puede quedar
    partido o entero dentro de un cruce (el ER dice Polygon; D28)."""

    __tablename__ = "tramo_circulacion"

    id_tramo: Mapped[int] = mapped_column(primary_key=True)
    id_version: Mapped[int] = mapped_column(ForeignKey("version_alternativa.id_version"), index=True)
    id_jerarquia: Mapped[int] = mapped_column(ForeignKey("jerarquia_corredor.id_jerarquia"))
    id_nodo_origen: Mapped[int] = mapped_column(ForeignKey("nodo_red.id_nodo"))
    id_nodo_destino: Mapped[int] = mapped_column(ForeignKey("nodo_red.id_nodo"))
    eje: Mapped[WKBElement] = mapped_column(geometria("LINESTRING"))
    geom: Mapped[WKBElement | None] = mapped_column(geometria("MULTIPOLYGON"))
    longitud_m: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    fijado: Mapped[bool]

    jerarquia: Mapped[JerarquiaCorredor] = relationship()
    origen: Mapped[NodoRed] = relationship(foreign_keys=[id_nodo_origen])
    destino: Mapped[NodoRed] = relationship(foreign_keys=[id_nodo_destino])


class Manzana(Base):
    """Manzana (ER `manzana`): M1, M2… en el orden en que las devuelve el motor."""

    __tablename__ = "manzana"
    __table_args__ = (UniqueConstraint("id_version", "designacion"),)

    id_manzana: Mapped[int] = mapped_column(primary_key=True)
    id_version: Mapped[int] = mapped_column(ForeignKey("version_alternativa.id_version"))
    designacion: Mapped[str] = mapped_column(String(10))
    geom: Mapped[WKBElement] = mapped_column(geometria("POLYGON"))
    superficie_m2: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    fijada: Mapped[bool]


class Celda(Base):
    """Celda útil o fracción (ER `celda`). Las medidas son las del motor, en metros (D26)."""

    __tablename__ = "celda"
    __table_args__ = (UniqueConstraint("id_version", "designacion"),)

    id_celda: Mapped[int] = mapped_column(primary_key=True)
    id_version: Mapped[int] = mapped_column(ForeignKey("version_alternativa.id_version"))
    id_manzana: Mapped[int | None] = mapped_column(ForeignKey("manzana.id_manzana"))
    designacion: Mapped[str] = mapped_column(String(12))
    tipo: Mapped[str] = mapped_column(String(15))
    geom: Mapped[WKBElement] = mapped_column(geometria("POLYGON"))
    superficie_m2: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    frente_m: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    fondo_m: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    cumple: Mapped[bool]
    motivo_incumplimiento: Mapped[str | None] = mapped_column(String(200))
    fijada: Mapped[bool]

    manzana: Mapped[Manzana | None] = relationship()


class AreaReservadaVersion(Base):
    """La copia de un área reservada con la que se generó una versión (D59).

    NO está en el ER: el proyecto puede cambiar sus áreas (`area_reservada`), y una versión anterior
    tiene que seguir diciendo con qué áreas se generó, para reproducirla (RNF05) y para recalcularla
    con las mismas (CU09). Guarda el polígono que recibió el motor, con la precisión completa, y la
    designación R1, R2…, en el orden de la solicitud. Es inmutable como toda la versión (RNF04).
    """

    __tablename__ = "area_reservada_version"
    __table_args__ = (UniqueConstraint("id_version", "designacion"),)

    id_area_version: Mapped[int] = mapped_column(primary_key=True)
    id_version: Mapped[int] = mapped_column(ForeignKey("version_alternativa.id_version"))
    designacion: Mapped[str] = mapped_column(String(10))
    geom: Mapped[WKBElement] = mapped_column(geometria("POLYGON"))
    clase: Mapped[str | None] = mapped_column(String(20))
    denominacion: Mapped[str] = mapped_column(String(120))
    destino: Mapped[str | None] = mapped_column(String(200))
    superficie_m2: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class Incumplimiento(Base):
    """Toda restricción que no se cumple en una versión, como la informa el verificador.

    NO está en el ER: sin esta tabla, los incumplimientos que no son de una celda (la cesión de
    espacio verde, la conectividad) se perderían, y la pantalla de la p. 49 no se podría
    reconstruir desde la base (D28). Queda anotada para sumarla al documento.
    """

    __tablename__ = "incumplimiento"

    id_incumplimiento: Mapped[int] = mapped_column(primary_key=True)
    id_version: Mapped[int] = mapped_column(ForeignKey("version_alternativa.id_version"), index=True)
    # La celda incumplidora, si el elemento es una celda.
    id_celda: Mapped[int | None] = mapped_column(ForeignKey("celda.id_celda"))
    tipo: Mapped[str] = mapped_column(String(30))
    # Designación de lo que incumple: «M3-L07», «A2», «red» o «terreno».
    elemento: Mapped[str] = mapped_column(String(20))
    detalle: Mapped[str] = mapped_column(Text)
    geom: Mapped[WKBElement | None] = mapped_column(geometria("GEOMETRY"))

    celda: Mapped[Celda | None] = relationship()
