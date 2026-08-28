"""Alpha 2 authentication and labeling metadata.

Existing projects are deliberately marked as legacy. No existing bay name,
truss label, diagnostic state, audit row, or relationship is rewritten.
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_alpha2"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("labeling_scheme", sa.String(16), nullable=False, server_default="legacy"))
        batch.create_check_constraint("ck_project_labeling_scheme", "labeling_scheme IN ('legacy','bay_prefix')")
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("auth_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("id = 1", name="ck_app_settings_singleton"),
    )
    op.execute(sa.text("INSERT INTO app_settings (id, auth_version) VALUES (1, 1)"))


def downgrade():
    op.drop_table("app_settings")
    with op.batch_alter_table("projects") as batch:
        batch.drop_constraint("ck_project_labeling_scheme", type_="check")
        batch.drop_column("labeling_scheme")
