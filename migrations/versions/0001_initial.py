"""Initial data model for ZIPP diagnostics."""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("projects",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(160), nullable=False),
        sa.Column("note", sa.Text()), sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("bays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False), sa.Column("name", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "position", name="uq_bay_project_position"))
    op.create_index("ix_bays_project_id", "bays", ["project_id"])
    op.create_table("trusses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bay_id", sa.Integer(), sa.ForeignKey("bays.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False), sa.Column("label", sa.String(80), nullable=False),
        sa.Column("type", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("left_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("right_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exclusion_reason", sa.String(16)), sa.Column("exclusion_note", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("type IN ('normal','gable','dilation')", name="ck_truss_type"),
        sa.CheckConstraint("exclusion_reason IS NULL OR exclusion_reason IN ('leak','crack','other')", name="ck_exclusion_reason"),
        sa.UniqueConstraint("bay_id", "position", name="uq_truss_bay_position"))
    op.create_index("ix_trusses_bay_id", "trusses", ["bay_id"])
    op.create_table("dilation_pairs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bay_id", sa.Integer(), sa.ForeignKey("bays.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_dilation_pairs_bay_id", "dilation_pairs", ["bay_id"])
    op.create_table("dilation_pair_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dilation_pair_id", sa.Integer(), sa.ForeignKey("dilation_pairs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("truss_id", sa.Integer(), sa.ForeignKey("trusses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("member_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("member_order IN (1,2)", name="ck_pair_member_order"),
        sa.UniqueConstraint("dilation_pair_id", "member_order", name="uq_pair_member_order"),
        sa.UniqueConstraint("truss_id", name="uq_pair_member_truss"))
    op.create_index("ix_dilation_pair_members_dilation_pair_id", "dilation_pair_members", ["dilation_pair_id"])
    op.create_index("ix_dilation_pair_members_truss_id", "dilation_pair_members", ["truss_id"])
    op.create_table("audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("bay_id", sa.Integer(), sa.ForeignKey("bays.id", ondelete="RESTRICT")),
        sa.Column("truss_id", sa.Integer(), sa.ForeignKey("trusses.id", ondelete="RESTRICT")),
        sa.Column("technician_name", sa.String(100), nullable=False), sa.Column("action", sa.String(80), nullable=False),
        sa.Column("field", sa.String(80)), sa.Column("old_value", sa.Text()), sa.Column("new_value", sa.Text()),
        sa.Column("metadata_json", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_audit_logs_project_id", "audit_logs", ["project_id"])
    op.create_index("ix_audit_logs_bay_id", "audit_logs", ["bay_id"])
    op.create_index("ix_audit_logs_truss_id", "audit_logs", ["truss_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade():
    op.drop_table("audit_logs")
    op.drop_table("dilation_pair_members")
    op.drop_table("dilation_pairs")
    op.drop_table("trusses")
    op.drop_table("bays")
    op.drop_table("projects")
