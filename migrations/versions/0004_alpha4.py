"""Alpha 4 project deletion tombstones.

Deletion logs deliberately have no foreign key to projects, so the minimal
audit record survives an intentional permanent project deletion.
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_alpha4"
down_revision = "0003_alpha3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_deletion_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_name", sa.String(160), nullable=False),
        sa.Column("technician_name", sa.String(100), nullable=False),
        sa.Column("action", sa.String(80), nullable=False, server_default="project.deleted"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade():
    op.drop_table("project_deletion_logs")
