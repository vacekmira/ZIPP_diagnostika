"""Alpha 3 single-bay labeling metadata.

The migration only widens the existing CHECK constraint. Existing projects,
bays, truss labels, diagnostics, pairs, and audit rows are not rewritten.
"""

from alembic import op


revision = "0003_alpha3"
down_revision = "0002_alpha2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("projects") as batch:
        batch.drop_constraint("ck_project_labeling_scheme", type_="check")
        batch.create_check_constraint(
            "ck_project_labeling_scheme",
            "labeling_scheme IN ('legacy','bay_prefix','single_v')",
        )


def downgrade():
    # Existing V labels remain untouched. Only future default-label behavior
    # falls back to the Alpha 2 scheme after a downgrade.
    op.execute("UPDATE projects SET labeling_scheme='bay_prefix' WHERE labeling_scheme='single_v'")
    with op.batch_alter_table("projects") as batch:
        batch.drop_constraint("ck_project_labeling_scheme", type_="check")
        batch.create_check_constraint(
            "ck_project_labeling_scheme",
            "labeling_scheme IN ('legacy','bay_prefix')",
        )
