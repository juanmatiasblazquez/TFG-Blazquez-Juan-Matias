"""usuarios, sesiones y control de acceso (API 0.11.0)

La autenticación real reemplaza al usuario de desarrollo (RF01 a RF03, RNF02, CU01, CU02; Seguridad,
p. 53 y 54).

- **`usuario`** suma lo que la contraseña temporal necesita y el ER no tiene (D29, D66):
  - `debe_cambiar_contrasena`: hasta que el usuario la reemplace, su sesión solo permite cambiarla;
  - `vence_contrasena_temporal`: la temporal vale 24 h (p. 53).

  Y un CHECK del rol: los tres con cuenta de la tabla de la p. 54 (`app.core.permisos.Rol`). El
  Cliente no tiene cuenta (CU15).
- **`sesion`** (fuera del ER, D63): un token aleatorio por sesión, guardado como SHA-256, con su
  vencimiento a las 12 h y la fecha de cierre. El token vive en una cookie `HttpOnly`.
- **`acceso_direccion`** (fuera del ER, D65): los intentos fallidos consecutivos por dirección, el
  bloqueo de 30 min tras el décimo (CU01, 4.b) y las solicitudes del minuto en curso.
- **El usuario de desarrollo se desactiva (D68).** Su hash era «!», así que nunca pudo iniciar sesión;
  conserva la autoría de sus proyectos y versiones, porque los usuarios no se borran (CU02). En una
  base nueva o en producción el UPDATE no encuentra nada.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMAIL_DESARROLLO = "desarrollo@trazados.local"


def upgrade() -> None:
    op.add_column(
        "usuario",
        sa.Column("debe_cambiar_contrasena", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("usuario", sa.Column("vence_contrasena_temporal", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        op.f("ck_usuario_rol"), "usuario", "rol IN ('director_tecnico', 'proyectista', 'consultor_interno')"
    )

    op.create_table(
        "sesion",
        sa.Column("id_sesion", sa.Integer(), nullable=False),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("hash_token", sa.String(64), nullable=False),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vence", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cerrada_en", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id_sesion", name="pk_sesion"),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuario.id_usuario"], name="fk_sesion_id_usuario"),
        sa.UniqueConstraint("hash_token", name="uq_sesion_hash_token"),
    )
    op.create_index(op.f("ix_sesion_id_usuario"), "sesion", ["id_usuario"])

    op.create_table(
        "acceso_direccion",
        sa.Column("direccion", sa.String(45), nullable=False),
        sa.Column("intentos_fallidos", sa.Integer(), nullable=False),
        sa.Column("bloqueada_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ventana_inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("solicitudes_en_ventana", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("direccion", name="pk_acceso_direccion"),
    )

    op.execute(f"UPDATE usuario SET activo = false WHERE email = '{EMAIL_DESARROLLO}'")


def downgrade() -> None:
    op.execute(f"UPDATE usuario SET activo = true WHERE email = '{EMAIL_DESARROLLO}'")
    op.drop_table("acceso_direccion")
    op.drop_index(op.f("ix_sesion_id_usuario"), table_name="sesion")
    op.drop_table("sesion")
    op.drop_constraint(op.f("ck_usuario_rol"), "usuario", type_="check")
    op.drop_column("usuario", "vence_contrasena_temporal")
    op.drop_column("usuario", "debe_cambiar_contrasena")
