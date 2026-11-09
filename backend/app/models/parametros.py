from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.proyecto import Proyecto
from app.models.tipos import Fecha


class ConjuntoParametros(Base):
    """Versión de los parámetros de un proyecto (ER `conjunto_parametros`). Cada versión de
    alternativa guarda con cuál se generó (p. 49)."""

    __tablename__ = "conjunto_parametros"
    __table_args__ = (
        UniqueConstraint("id_proyecto", "version"),
        # Un solo conjunto vigente por proyecto: es el que usa la generación (CU06, paso 2).
        Index("ix_conjunto_parametros_un_vigente", "id_proyecto", unique=True, postgresql_where=text("vigente")),
    )

    id_conjunto: Mapped[int] = mapped_column(primary_key=True)
    id_proyecto: Mapped[int] = mapped_column(ForeignKey("proyecto.id_proyecto"))
    version: Mapped[int]
    vigente: Mapped[bool]
    criterio_prioritario: Mapped[str] = mapped_column(String(30))
    porcentaje_espacio_verde: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    tolerancia_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    fecha_creacion: Mapped[Fecha]

    proyecto: Mapped[Proyecto] = relationship(back_populates="conjuntos")
    loteo: Mapped["ParametrosLoteo | None"] = relationship(back_populates="conjunto")
    jerarquias: Mapped[list["JerarquiaCorredor"]] = relationship(
        back_populates="conjunto", order_by="JerarquiaCorredor.orden"
    )


class ParametrosLoteo(Base):
    """Parámetros propios de un loteo (ER `parametros_loteo`, 1 a 0..1 con el conjunto). Es una
    relación simple y no herencia del ORM: el ER no tiene columna discriminadora; el tipo sale
    del proyecto."""

    __tablename__ = "parametros_loteo"

    id_conjunto: Mapped[int] = mapped_column(ForeignKey("conjunto_parametros.id_conjunto"), primary_key=True)
    frente_minimo_m: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    frente_objetivo_m: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    fondo_minimo_m: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    superficie_minima_m2: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    superficie_maxima_m2: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    relacion_fondo_frente_max: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    longitud_maxima_manzana_m: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    porcentaje_equipamiento: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    # Cuándo un remanente es espacio verde (D41; migración 0004) y el criterio de forma del lote
    # (D43; migración 0005). No están en el ER (D29). NULL quiere decir «no aplica»: el conjunto
    # es anterior al motor que usa ese parámetro (D45), y generar con él da 422.
    superficie_minima_verde_m2: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    ancho_minimo_verde_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    ancho_minimo_lote_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    factor_union_maximo: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    # Migración 0006, tampoco en el ER (D29): la Ley 4146, art. 12 (D48), la Ord. 8060, art. 54
    # (D49), y el criterio del asignador (D46: «menos_lotes» o «cercania»). Siguen la regla de
    # D45: NULL en un conjunto que ningún motor que los usa usó.
    porcentaje_minimo_avenidas: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    ancho_minimo_avenida_m: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    ancho_minimo_calle_m: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    ancho_minimo_calzada_m: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    porcentaje_incremento_esquina: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    criterio_espacio_verde: Mapped[str | None] = mapped_column(String(15))
    # Migración 0007, tampoco en el ER (D29): los lados de la manzana de la Ord. 8060, art. 48
    # (D50). NULL en los conjuntos anteriores (D45).
    lado_minimo_manzana_m: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    lado_maximo_manzana_m: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    lado_maximo_sin_pasaje_m: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    # Migración 0014, tampoco en el ER (D29): por dónde va la calle de borde, «contorno» (D50) o
    # «por_lado» (D86). «contorno» en los conjuntos que usó un motor con calle de borde (0.7.0 a 0.10.x),
    # NULL en los demás (D45).
    calle_borde: Mapped[str | None] = mapped_column(String(10))

    conjunto: Mapped[ConjuntoParametros] = relationship(back_populates="loteo")


class JerarquiaCorredor(Base):
    """Jerarquía de calle (ER `jerarquia_corredor`). `orden` 1 es la mayor y es única dentro del
    conjunto: con ella se vuelve de los tramos del motor a esta fila."""

    __tablename__ = "jerarquia_corredor"
    __table_args__ = (UniqueConstraint("id_conjunto", "orden"),)

    id_jerarquia: Mapped[int] = mapped_column(primary_key=True)
    id_conjunto: Mapped[int] = mapped_column(ForeignKey("conjunto_parametros.id_conjunto"))
    nombre: Mapped[str] = mapped_column(String(40))
    orden: Mapped[int] = mapped_column(SmallInteger)
    ancho_calzada_m: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    ancho_vereda_m: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    # Nombre del ER, pero guarda el LARGO de la línea de ochava, no un radio (D24, D29).
    radio_ochava_m: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    conjunto: Mapped[ConjuntoParametros] = relationship(back_populates="jerarquias")
