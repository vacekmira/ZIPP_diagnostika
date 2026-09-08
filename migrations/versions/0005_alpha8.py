"""Alpha 8 hall heights and independent side access.

Revision ID: 0005_alpha8
Revises: 0004_alpha4
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_alpha8"
down_revision = "0004_alpha4"
branch_labels = None
depends_on = None


def upgrade():
    # Additive nullable columns preserve every historical row and label.
    op.add_column("projects", sa.Column("default_height_m", sa.Float(), nullable=True))
    op.add_column("bays", sa.Column("height_m", sa.Float(), nullable=True))
    op.add_column("trusses", sa.Column("left_access", sa.String(1), nullable=True))
    op.add_column("trusses", sa.Column("right_access", sa.String(1), nullable=True))
    op.add_column("trusses", sa.Column("access_note", sa.Text(), nullable=True))


def downgrade():
    for field in ("access_note", "right_access", "left_access"):
        op.drop_column("trusses", field)
    op.drop_column("bays", "height_m")
    op.drop_column("projects", "default_height_m")
