"""tablas del flujo de generación: proyecto, parámetros, alternativas y versiones

Crea las entidades del ER (p. 47) que usa la generación de una alternativa (CU03 a CU06) y
nada más: cliente, áreas reservadas, parámetros de estacionamiento, observaciones y enlaces
compartidos entran con la funcionalidad que los usa (D28).

Lo que se aparta del ER, registrado en D28:
- `version_alternativa.version_motor` y la tabla `incumplimiento`, que el ER no tiene.
- `tramo_circulacion.geom` es MultiPolygon y opcional (el ER dice Polygon).
- `proyecto` todavía no tiene `id_cliente`.
- Las fechas son timestamp with time zone.

Las versiones son INMUTABLES (RNF04): un trigger rechaza UPDATE, DELETE y TRUNCATE sobre la
versión y todo lo que cuelga de ella. Así ni un error del código ni un `psql` a mano pisan una
versión guardada.

Los nombres de restricciones e índices siguen la convención de app.core.db
(CONVENCION_NOMBRES): la prueba de que los modelos coinciden con las migraciones los compara.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tablas de una versión, en el orden en que se crean (y al revés se borran).
TABLAS_INMUTABLES = ("version_alternativa", "nodo_red", "tramo_circulacion", "manzana", "celda", "incumplimiento")


def geometria(tipo: str) -> Geometry:
    return Geometry(geometry_type=tipo, srid=4326, spatial_index=False)


def _fecha(nombre: str) -> sa.Column:
    return sa.Column(nombre, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "usuario",
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column("apellido", sa.String(60), nullable=False),
        sa.Column("email", sa.String(120), nullable=False),
        sa.Column("hash_contrasena", sa.String(255), nullable=False),
        sa.Column("rol", sa.String(20), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        _fecha("fecha_alta"),
        sa.PrimaryKeyConstraint("id_usuario", name="pk_usuario"),
        sa.UniqueConstraint("email", name="uq_usuario_email"),
    )
    op.create_table(
        "proyecto",
        sa.Column("id_proyecto", sa.Integer(), nullable=False),
        sa.Column("id_usuario_responsable", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("tipo", sa.String(25), nullable=False),
        sa.Column("ubicacion", sa.String(200), nullable=True),
        sa.Column("jurisdiccion", sa.String(120), nullable=True),
        sa.Column("srid_calculo", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        _fecha("fecha_creacion"),
        sa.PrimaryKeyConstraint("id_proyecto", name="pk_proyecto"),
        sa.ForeignKeyConstraint(
            ["id_usuario_responsable"], ["usuario.id_usuario"], name="fk_proyecto_id_usuario_responsable"
        ),
        sa.UniqueConstraint("codigo", name="uq_proyecto_codigo"),
    )
    op.create_table(
        "terreno",
        sa.Column("id_terreno", sa.Integer(), nullable=False),
        sa.Column("id_proyecto", sa.Integer(), nullable=False),
        sa.Column("geom", geometria("POLYGON"), nullable=False),
        sa.Column("superficie_m2", sa.Numeric(12, 2), nullable=False),
        sa.Column("perimetro_m", sa.Numeric(10, 2), nullable=False),
        sa.Column("origen", sa.String(12), nullable=False),
        sa.PrimaryKeyConstraint("id_terreno", name="pk_terreno"),
        sa.ForeignKeyConstraint(["id_proyecto"], ["proyecto.id_proyecto"], name="fk_terreno_id_proyecto"),
        sa.UniqueConstraint("id_proyecto", name="uq_terreno_id_proyecto"),
    )
    op.create_table(
        "punto_acceso",
        sa.Column("id_punto_acceso", sa.Integer(), nullable=False),
        sa.Column("id_terreno", sa.Integer(), nullable=False),
        sa.Column("geom", geometria("POINT"), nullable=False),
        sa.Column("ancho_m", sa.Numeric(6, 2), nullable=True),
        sa.Column("via_vinculacion", sa.String(120), nullable=True),
        sa.PrimaryKeyConstraint("id_punto_acceso", name="pk_punto_acceso"),
        sa.ForeignKeyConstraint(["id_terreno"], ["terreno.id_terreno"], name="fk_punto_acceso_id_terreno"),
    )
    op.create_index("ix_punto_acceso_id_terreno", "punto_acceso", ["id_terreno"])

    op.create_table(
        "conjunto_parametros",
        sa.Column("id_conjunto", sa.Integer(), nullable=False),
        sa.Column("id_proyecto", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("vigente", sa.Boolean(), nullable=False),
        sa.Column("criterio_prioritario", sa.String(30), nullable=False),
        sa.Column("porcentaje_espacio_verde", sa.Numeric(5, 2), nullable=False),
        sa.Column("tolerancia_pct", sa.Numeric(5, 2), nullable=False),
        _fecha("fecha_creacion"),
        sa.PrimaryKeyConstraint("id_conjunto", name="pk_conjunto_parametros"),
        sa.ForeignKeyConstraint(["id_proyecto"], ["proyecto.id_proyecto"], name="fk_conjunto_parametros_id_proyecto"),
        sa.UniqueConstraint("id_proyecto", "version", name="uq_conjunto_parametros_id_proyecto_version"),
    )
    # Un solo conjunto vigente por proyecto (CU06, paso 2: «parámetros vigentes»).
    op.create_index(
        "ix_conjunto_parametros_un_vigente",
        "conjunto_parametros",
        ["id_proyecto"],
        unique=True,
        postgresql_where=sa.text("vigente"),
    )
    op.create_table(
        "parametros_loteo",
        sa.Column("id_conjunto", sa.Integer(), nullable=False),
        sa.Column("frente_minimo_m", sa.Numeric(6, 2), nullable=False),
        sa.Column("frente_objetivo_m", sa.Numeric(6, 2), nullable=False),
        sa.Column("fondo_minimo_m", sa.Numeric(6, 2), nullable=False),
        sa.Column("superficie_minima_m2", sa.Numeric(8, 2), nullable=False),
        sa.Column("superficie_maxima_m2", sa.Numeric(8, 2), nullable=False),
        sa.Column("relacion_fondo_frente_max", sa.Numeric(4, 2), nullable=False),
        sa.Column("longitud_maxima_manzana_m", sa.Numeric(7, 2), nullable=False),
        sa.Column("porcentaje_equipamiento", sa.Numeric(5, 2), nullable=False),
        sa.PrimaryKeyConstraint("id_conjunto", name="pk_parametros_loteo"),
        sa.ForeignKeyConstraint(
            ["id_conjunto"], ["conjunto_parametros.id_conjunto"], name="fk_parametros_loteo_id_conjunto"
        ),
    )
    op.create_table(
        "jerarquia_corredor",
        sa.Column("id_jerarquia", sa.Integer(), nullable=False),
        sa.Column("id_conjunto", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(40), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False),
        sa.Column("ancho_calzada_m", sa.Numeric(5, 2), nullable=False),
        sa.Column("ancho_vereda_m", sa.Numeric(5, 2), nullable=False),
        sa.Column("radio_ochava_m", sa.Numeric(5, 2), nullable=False),
        sa.PrimaryKeyConstraint("id_jerarquia", name="pk_jerarquia_corredor"),
        sa.ForeignKeyConstraint(
            ["id_conjunto"], ["conjunto_parametros.id_conjunto"], name="fk_jerarquia_corredor_id_conjunto"
        ),
        sa.UniqueConstraint("id_conjunto", "orden", name="uq_jerarquia_corredor_id_conjunto_orden"),
    )

    op.create_table(
        "alternativa",
        sa.Column("id_alternativa", sa.Integer(), nullable=False),
        sa.Column("id_proyecto", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(5), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        _fecha("fecha_creacion"),
        sa.PrimaryKeyConstraint("id_alternativa", name="pk_alternativa"),
        sa.ForeignKeyConstraint(["id_proyecto"], ["proyecto.id_proyecto"], name="fk_alternativa_id_proyecto"),
        sa.UniqueConstraint("id_proyecto", "codigo", name="uq_alternativa_id_proyecto_codigo"),
    )
    op.create_table(
        "version_alternativa",
        sa.Column("id_version", sa.Integer(), nullable=False),
        sa.Column("id_alternativa", sa.Integer(), nullable=False),
        sa.Column("id_conjunto", sa.Integer(), nullable=False),
        sa.Column("id_version_origen", sa.Integer(), nullable=True),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("patron_red", sa.String(15), nullable=False),
        sa.Column("orientacion_grados", sa.Numeric(5, 2), nullable=False),
        sa.Column("semilla", sa.Integer(), nullable=False),
        sa.Column("geom_fijada", geometria("MULTIPOLYGON"), nullable=True),
        sa.Column("cumple_restricciones", sa.Boolean(), nullable=False),
        sa.Column("cantidad_celdas", sa.Integer(), nullable=False),
        sa.Column("superficie_aprovechable_m2", sa.Numeric(12, 2), nullable=False),
        sa.Column("porcentaje_circulacion", sa.Numeric(5, 2), nullable=False),
        sa.Column("porcentaje_espacio_verde", sa.Numeric(5, 2), nullable=False),
        sa.Column("longitud_red_m", sa.Numeric(10, 2), nullable=False),
        sa.Column("distancia_media_acceso_m", sa.Numeric(8, 2), nullable=True),
        sa.Column("duracion_ms", sa.Integer(), nullable=False),
        sa.Column("version_motor", sa.String(20), nullable=False),
        _fecha("fecha_generacion"),
        sa.PrimaryKeyConstraint("id_version", name="pk_version_alternativa"),
        sa.ForeignKeyConstraint(
            ["id_alternativa"], ["alternativa.id_alternativa"], name="fk_version_alternativa_id_alternativa"
        ),
        sa.ForeignKeyConstraint(
            ["id_conjunto"], ["conjunto_parametros.id_conjunto"], name="fk_version_alternativa_id_conjunto"
        ),
        sa.ForeignKeyConstraint(
            ["id_version_origen"], ["version_alternativa.id_version"], name="fk_version_alternativa_id_version_origen"
        ),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuario.id_usuario"], name="fk_version_alternativa_id_usuario"),
        sa.UniqueConstraint("id_alternativa", "numero", name="uq_version_alternativa_id_alternativa_numero"),
    )
    op.create_table(
        "nodo_red",
        sa.Column("id_nodo", sa.Integer(), nullable=False),
        sa.Column("id_version", sa.Integer(), nullable=False),
        sa.Column("id_punto_acceso", sa.Integer(), nullable=True),
        sa.Column("geom", geometria("POINT"), nullable=False),
        sa.PrimaryKeyConstraint("id_nodo", name="pk_nodo_red"),
        sa.ForeignKeyConstraint(["id_version"], ["version_alternativa.id_version"], name="fk_nodo_red_id_version"),
        sa.ForeignKeyConstraint(
            ["id_punto_acceso"], ["punto_acceso.id_punto_acceso"], name="fk_nodo_red_id_punto_acceso"
        ),
    )
    op.create_index("ix_nodo_red_id_version", "nodo_red", ["id_version"])
    op.create_table(
        "tramo_circulacion",
        sa.Column("id_tramo", sa.Integer(), nullable=False),
        sa.Column("id_version", sa.Integer(), nullable=False),
        sa.Column("id_jerarquia", sa.Integer(), nullable=False),
        sa.Column("id_nodo_origen", sa.Integer(), nullable=False),
        sa.Column("id_nodo_destino", sa.Integer(), nullable=False),
        sa.Column("eje", geometria("LINESTRING"), nullable=False),
        sa.Column("geom", geometria("MULTIPOLYGON"), nullable=True),
        sa.Column("longitud_m", sa.Numeric(8, 2), nullable=False),
        sa.Column("fijado", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id_tramo", name="pk_tramo_circulacion"),
        sa.ForeignKeyConstraint(
            ["id_version"], ["version_alternativa.id_version"], name="fk_tramo_circulacion_id_version"
        ),
        sa.ForeignKeyConstraint(
            ["id_jerarquia"], ["jerarquia_corredor.id_jerarquia"], name="fk_tramo_circulacion_id_jerarquia"
        ),
        sa.ForeignKeyConstraint(["id_nodo_origen"], ["nodo_red.id_nodo"], name="fk_tramo_circulacion_id_nodo_origen"),
        sa.ForeignKeyConstraint(
            ["id_nodo_destino"], ["nodo_red.id_nodo"], name="fk_tramo_circulacion_id_nodo_destino"
        ),
    )
    op.create_index("ix_tramo_circulacion_id_version", "tramo_circulacion", ["id_version"])
    op.create_table(
        "manzana",
        sa.Column("id_manzana", sa.Integer(), nullable=False),
        sa.Column("id_version", sa.Integer(), nullable=False),
        sa.Column("designacion", sa.String(10), nullable=False),
        sa.Column("geom", geometria("POLYGON"), nullable=False),
        sa.Column("superficie_m2", sa.Numeric(12, 2), nullable=False),
        sa.Column("fijada", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id_manzana", name="pk_manzana"),
        sa.ForeignKeyConstraint(["id_version"], ["version_alternativa.id_version"], name="fk_manzana_id_version"),
        sa.UniqueConstraint("id_version", "designacion", name="uq_manzana_id_version_designacion"),
    )
    op.create_table(
        "celda",
        sa.Column("id_celda", sa.Integer(), nullable=False),
        sa.Column("id_version", sa.Integer(), nullable=False),
        sa.Column("id_manzana", sa.Integer(), nullable=True),
        sa.Column("designacion", sa.String(12), nullable=False),
        sa.Column("tipo", sa.String(15), nullable=False),
        sa.Column("geom", geometria("POLYGON"), nullable=False),
        sa.Column("superficie_m2", sa.Numeric(10, 2), nullable=False),
        sa.Column("frente_m", sa.Numeric(7, 2), nullable=False),
        sa.Column("fondo_m", sa.Numeric(7, 2), nullable=False),
        sa.Column("cumple", sa.Boolean(), nullable=False),
        sa.Column("motivo_incumplimiento", sa.String(200), nullable=True),
        sa.Column("fijada", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id_celda", name="pk_celda"),
        sa.ForeignKeyConstraint(["id_version"], ["version_alternativa.id_version"], name="fk_celda_id_version"),
        sa.ForeignKeyConstraint(["id_manzana"], ["manzana.id_manzana"], name="fk_celda_id_manzana"),
        sa.UniqueConstraint("id_version", "designacion", name="uq_celda_id_version_designacion"),
    )
    op.create_table(
        "incumplimiento",
        sa.Column("id_incumplimiento", sa.Integer(), nullable=False),
        sa.Column("id_version", sa.Integer(), nullable=False),
        sa.Column("id_celda", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("elemento", sa.String(20), nullable=False),
        sa.Column("detalle", sa.Text(), nullable=False),
        sa.Column("geom", geometria("GEOMETRY"), nullable=True),
        sa.PrimaryKeyConstraint("id_incumplimiento", name="pk_incumplimiento"),
        sa.ForeignKeyConstraint(
            ["id_version"], ["version_alternativa.id_version"], name="fk_incumplimiento_id_version"
        ),
        sa.ForeignKeyConstraint(["id_celda"], ["celda.id_celda"], name="fk_incumplimiento_id_celda"),
    )
    op.create_index("ix_incumplimiento_id_version", "incumplimiento", ["id_version"])

    # RNF04: una versión no se modifica nunca; toda modificación crea una versión nueva.
    op.execute(
        """
        CREATE FUNCTION version_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION
                'Las versiones de alternativa son inmutables (RNF04): no se admite % sobre %.',
                TG_OP, TG_TABLE_NAME
                USING HINT = 'Generá o recalculá una versión nueva en lugar de modificar esta.';
        END
        $$
        """
    )
    for tabla in TABLAS_INMUTABLES:
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
    for tabla in reversed(TABLAS_INMUTABLES):
        op.drop_table(tabla)
    op.execute("DROP FUNCTION version_inmutable()")
    for tabla in ("alternativa", "jerarquia_corredor", "parametros_loteo", "conjunto_parametros",
                  "punto_acceso", "terreno", "proyecto", "usuario"):
        op.drop_table(tabla)
