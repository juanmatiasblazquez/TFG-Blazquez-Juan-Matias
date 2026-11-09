"""observaciones y enlaces compartidos (API 0.12.0)

Las entidades del ER que faltaban para el flujo hasta su límite: registrar y responder observaciones
(CU11, CU12, RF17) y compartir alternativas con el cliente (CU14, CU15, RF16).

- **`alternativa.estado`** suma un CHECK con sus tres valores (`EstadoAlternativa`, D69): `generada`
  (el de siempre), `observada` (CU11, paso 5) y `seleccionada` (`seleccionar()`, p. 45, paso 7). Las
  que ya existen están todas en `generada`.
- **`observacion`** (ER): tipo y criticidad del acta de observaciones (Anexo 1.5), estado (`abierta`,
  `respondida`, `cerrada`) y el sector afectado, opcional. Cuelga de una versión, pero no es parte de
  ella: su estado cambia con el ciclo de revisión. Por eso no lleva el trigger de la 0002 sino uno
  propio, `observacion_solo_estado()`: un UPDATE solo puede cambiar `estado` y `fecha_cierre`, y no se
  admiten DELETE ni TRUNCATE. Lo que se observó, quién y cuándo, no cambia nunca (D28).
- **`respuesta_observacion`** (ER): la acción, el comentario y, si la acción fue un recálculo, la versión
  que resultó (CU12, paso 5). Un CHECK ata las dos cosas: `recalculo_parcial` lleva versión resultante, y
  las otras acciones no. Es un registro: inmutable, con el trigger de la 0002.
- **`enlace_compartido`** (ER): el token se guarda como SHA-256 (64 caracteres hexadecimales: el
  varchar(64) del ER), nunca en claro (p. 54). Suma `id_usuario`, quién lo generó, que el ER no tiene
  (D29). `revocado`, `ultimo_acceso` y `cantidad_accesos` cambian con el uso.
- **`enlace_version`** (ER): ata el enlace a versiones concretas (p. 45: lo que se genere después no
  cambia lo que ve el cliente). Cuelga de una versión: inmutable, con el trigger de la 0002.

Lo que se aparta del ER, anotado en D28 y D29.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Los registros que no se modifican nunca: el trigger de la 0002 (RNF04, D28).
INMUTABLES = ("respuesta_observacion", "enlace_version")


def geometria(tipo: str) -> Geometry:
    return Geometry(geometry_type=tipo, srid=4326, spatial_index=False)


def upgrade() -> None:
    op.create_check_constraint(
        op.f("ck_alternativa_estado"), "alternativa", "estado IN ('generada', 'observada', 'seleccionada')"
    )

    op.create_table(
        "observacion",
        sa.Column("id_observacion", sa.Integer(), nullable=False),
        sa.Column("id_version", sa.Integer(), nullable=False),
        sa.Column("id_usuario_emisor", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(15), nullable=False),
        sa.Column("criticidad", sa.String(10), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("sector", geometria("POLYGON"), nullable=True),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("fecha_emision", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("fecha_cierre", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id_observacion", name="pk_observacion"),
        sa.ForeignKeyConstraint(["id_version"], ["version_alternativa.id_version"], name="fk_observacion_id_version"),
        sa.ForeignKeyConstraint(["id_usuario_emisor"], ["usuario.id_usuario"], name="fk_observacion_id_usuario_emisor"),
        sa.CheckConstraint(
            "tipo IN ('normativa', 'dimensional', 'conectividad', 'comercial', 'grafica')",
            name=op.f("ck_observacion_tipo"),
        ),
        sa.CheckConstraint("criticidad IN ('bloqueante', 'sugerida')", name=op.f("ck_observacion_criticidad")),
        sa.CheckConstraint("estado IN ('abierta', 'respondida', 'cerrada')", name=op.f("ck_observacion_estado")),
    )
    op.create_index(op.f("ix_observacion_id_version"), "observacion", ["id_version"])

    op.create_table(
        "respuesta_observacion",
        sa.Column("id_respuesta", sa.Integer(), nullable=False),
        sa.Column("id_observacion", sa.Integer(), nullable=False),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("id_version_resultante", sa.Integer(), nullable=True),
        sa.Column("accion", sa.String(20), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id_respuesta", name="pk_respuesta_observacion"),
        sa.ForeignKeyConstraint(
            ["id_observacion"], ["observacion.id_observacion"], name="fk_respuesta_observacion_id_observacion"
        ),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuario.id_usuario"], name="fk_respuesta_observacion_id_usuario"),
        sa.ForeignKeyConstraint(
            ["id_version_resultante"],
            ["version_alternativa.id_version"],
            name="fk_respuesta_observacion_id_version_resultante",
        ),
        sa.CheckConstraint(
            "accion IN ('recalculo_parcial', 'justificacion', 'aclaracion')",
            name=op.f("ck_respuesta_observacion_accion"),
        ),
        sa.CheckConstraint(
            "(accion = 'recalculo_parcial') = (id_version_resultante IS NOT NULL)",
            name=op.f("ck_respuesta_observacion_version_resultante"),
        ),
    )
    op.create_index(op.f("ix_respuesta_observacion_id_observacion"), "respuesta_observacion", ["id_observacion"])

    op.create_table(
        "enlace_compartido",
        sa.Column("id_enlace", sa.Integer(), nullable=False),
        sa.Column("id_proyecto", sa.Integer(), nullable=False),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("fecha_creacion", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("fecha_vencimiento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revocado", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("ultimo_acceso", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cantidad_accesos", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id_enlace", name="pk_enlace_compartido"),
        sa.ForeignKeyConstraint(["id_proyecto"], ["proyecto.id_proyecto"], name="fk_enlace_compartido_id_proyecto"),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuario.id_usuario"], name="fk_enlace_compartido_id_usuario"),
        sa.UniqueConstraint("token", name="uq_enlace_compartido_token"),
    )
    op.create_index(op.f("ix_enlace_compartido_id_proyecto"), "enlace_compartido", ["id_proyecto"])

    op.create_table(
        "enlace_version",
        sa.Column("id_enlace", sa.Integer(), nullable=False),
        sa.Column("id_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id_enlace", "id_version", name="pk_enlace_version"),
        sa.ForeignKeyConstraint(["id_enlace"], ["enlace_compartido.id_enlace"], name="fk_enlace_version_id_enlace"),
        sa.ForeignKeyConstraint(
            ["id_version"], ["version_alternativa.id_version"], name="fk_enlace_version_id_version"
        ),
    )

    # Lo observado no cambia: solo el estado y la fecha de cierre (D28, D69).
    op.execute(
        """
        CREATE FUNCTION observacion_solo_estado() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'UPDATE'
               AND (NEW.id_observacion, NEW.id_version, NEW.id_usuario_emisor, NEW.tipo, NEW.criticidad,
                    NEW.descripcion, ST_AsEWKB(NEW.sector), NEW.fecha_emision)
                   IS NOT DISTINCT FROM
                   (OLD.id_observacion, OLD.id_version, OLD.id_usuario_emisor, OLD.tipo, OLD.criticidad,
                    OLD.descripcion, ST_AsEWKB(OLD.sector), OLD.fecha_emision) THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION
                'Una observación registrada no se modifica (RNF04): no se admite % sobre % salvo el estado.',
                TG_OP, TG_TABLE_NAME
                USING HINT = 'Respondela, cerrala o reabrila: solo cambia su estado.';
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER observacion_inmutable BEFORE UPDATE OR DELETE ON observacion "
        "FOR EACH ROW EXECUTE FUNCTION observacion_solo_estado()"
    )
    op.execute(
        "CREATE TRIGGER observacion_inmutable_truncate BEFORE TRUNCATE ON observacion "
        "FOR EACH STATEMENT EXECUTE FUNCTION observacion_solo_estado()"
    )
    for tabla in INMUTABLES:
        op.execute(
            f"CREATE TRIGGER {tabla}_inmutable BEFORE UPDATE OR DELETE ON {tabla} "
            "FOR EACH ROW EXECUTE FUNCTION version_inmutable()"
        )
        op.execute(
            f"CREATE TRIGGER {tabla}_inmutable_truncate BEFORE TRUNCATE ON {tabla} "
            "FOR EACH STATEMENT EXECUTE FUNCTION version_inmutable()"
        )


def downgrade() -> None:
    # Borrar las tablas se lleva sus triggers (DROP TABLE no los dispara).
    op.drop_table("enlace_version")
    op.drop_index(op.f("ix_enlace_compartido_id_proyecto"), table_name="enlace_compartido")
    op.drop_table("enlace_compartido")
    op.drop_index(op.f("ix_respuesta_observacion_id_observacion"), table_name="respuesta_observacion")
    op.drop_table("respuesta_observacion")
    op.drop_index(op.f("ix_observacion_id_version"), table_name="observacion")
    op.drop_table("observacion")
    op.execute("DROP FUNCTION observacion_solo_estado()")
    op.drop_constraint(op.f("ck_alternativa_estado"), "alternativa", type_="check")
