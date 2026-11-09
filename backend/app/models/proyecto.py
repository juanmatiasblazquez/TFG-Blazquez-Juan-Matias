from decimal import Decimal

from geoalchemy2 import WKBElement
from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.cliente import Cliente
from app.models.tipos import Fecha, geometria
from app.models.usuario import Usuario

# Estados del proyecto (CU03). El documento no enumera EstadoProyecto: estos son los dos que
# nombra el caso de uso.
EN_PREPARACION = "en_preparacion"
LISTO_PARA_GENERAR = "listo_para_generar"


class Proyecto(Base):
    """Proyecto de loteo (ER `proyecto`), con su cliente, que CU03 hace obligatorio (D35)."""

    __tablename__ = "proyecto"

    id_proyecto: Mapped[int] = mapped_column(primary_key=True)
    id_cliente: Mapped[int] = mapped_column(ForeignKey("cliente.id_cliente"), index=True)
    id_usuario_responsable: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"))
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(25))
    ubicacion: Mapped[str | None] = mapped_column(String(200))
    jurisdiccion: Mapped[str | None] = mapped_column(String(120))
    # SRID del sistema de cálculo en metros (RF04, D21).
    srid_calculo: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(20))
    fecha_creacion: Mapped[Fecha]

    cliente: Mapped[Cliente] = relationship()
    responsable: Mapped[Usuario] = relationship()
    terreno: Mapped["Terreno"] = relationship(back_populates="proyecto")
    conjuntos: Mapped[list["ConjuntoParametros"]] = relationship(  # noqa: F821
        back_populates="proyecto", order_by="ConjuntoParametros.version"
    )
    alternativas: Mapped[list["Alternativa"]] = relationship(  # noqa: F821
        back_populates="proyecto", order_by="Alternativa.id_alternativa"
    )

    def parametros_vigentes(self) -> "ConjuntoParametros | None":  # noqa: F821
        return next((conjunto for conjunto in self.conjuntos if conjunto.vigente), None)


class Terreno(Base):
    """Polígono del terreno (ER `terreno`). Superficie y perímetro se miden en el sistema de
    cálculo, igual que los mide el motor."""

    __tablename__ = "terreno"

    id_terreno: Mapped[int] = mapped_column(primary_key=True)
    id_proyecto: Mapped[int] = mapped_column(ForeignKey("proyecto.id_proyecto"), unique=True)
    geom: Mapped[WKBElement] = mapped_column(geometria("POLYGON"))
    superficie_m2: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    perimetro_m: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # «dibujado» o «importado» (herramientas de la p. 48).
    origen: Mapped[str] = mapped_column(String(12))

    proyecto: Mapped[Proyecto] = relationship(back_populates="terreno")
    # El orden por id es la designación A1, A2… (el ER no la guarda) y el orden de los accesos
    # en la solicitud al motor.
    accesos: Mapped[list["PuntoAcceso"]] = relationship(
        back_populates="terreno", order_by="PuntoAcceso.id_punto_acceso"
    )
    # El orden por id es la designación R1, R2… (el ER no la guarda) y el orden de las áreas en la
    # solicitud al motor (D59). Se reemplazan enteras: las que se sacan se borran.
    areas_reservadas: Mapped[list["AreaReservada"]] = relationship(
        back_populates="terreno", order_by="AreaReservada.id_area_reservada", cascade="all, delete-orphan"
    )


class AreaReservada(Base):
    """Área reservada del terreno (ER `area_reservada`; CU04, paso 5): el motor la descuenta del
    dominio y la rodea con una calle (D59). `clase` es texto libre: el documento tipa la clase como
    `ClaseArea` pero no enumera sus valores (D29)."""

    __tablename__ = "area_reservada"

    id_area_reservada: Mapped[int] = mapped_column(primary_key=True)
    id_terreno: Mapped[int] = mapped_column(ForeignKey("terreno.id_terreno"), index=True)
    geom: Mapped[WKBElement] = mapped_column(geometria("POLYGON"))
    clase: Mapped[str | None] = mapped_column(String(20))
    # «A qué corresponde» el área (CU04, paso 5): «Servidumbre de electroducto» (p. 48).
    denominacion: Mapped[str] = mapped_column(String(120))
    destino: Mapped[str | None] = mapped_column(String(200))

    terreno: Mapped[Terreno] = relationship(back_populates="areas_reservadas")


class PuntoAcceso(Base):
    """Punto de acceso sobre el perímetro (ER `punto_acceso`)."""

    __tablename__ = "punto_acceso"

    id_punto_acceso: Mapped[int] = mapped_column(primary_key=True)
    id_terreno: Mapped[int] = mapped_column(ForeignKey("terreno.id_terreno"), index=True)
    geom: Mapped[WKBElement] = mapped_column(geometria("POINT"))
    # El motor no lo usa: el conector toma el ancho de la jerarquía mayor (D24).
    ancho_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    via_vinculacion: Mapped[str | None] = mapped_column(String(120))

    terreno: Mapped[Terreno] = relationship(back_populates="accesos")
