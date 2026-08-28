from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint("labeling_scheme IN ('legacy','bay_prefix')", name="ck_project_labeling_scheme"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    labeling_scheme: Mapped[str] = mapped_column(String(16), default="bay_prefix")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    bays: Mapped[list[Bay]] = relationship(back_populates="project", order_by="Bay.position")


class Bay(Base):
    __tablename__ = "bays"
    __table_args__ = (UniqueConstraint("project_id", "position", name="uq_bay_project_position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="bays")
    trusses: Mapped[list[Truss]] = relationship(back_populates="bay", order_by="Truss.position")
    dilation_pairs: Mapped[list[DilationPair]] = relationship(back_populates="bay")


class Truss(Base):
    __tablename__ = "trusses"
    __table_args__ = (
        UniqueConstraint("bay_id", "position", name="uq_truss_bay_position"),
        CheckConstraint("type IN ('normal','gable','dilation')", name="ck_truss_type"),
        CheckConstraint("exclusion_reason IS NULL OR exclusion_reason IN ('leak','crack','other')", name="ck_exclusion_reason"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bay_id: Mapped[int] = mapped_column(ForeignKey("bays.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(80))
    type: Mapped[str] = mapped_column(String(16), default="normal")
    left_done: Mapped[bool] = mapped_column(Boolean, default=False)
    right_done: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    exclusion_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    bay: Mapped[Bay] = relationship(back_populates="trusses")
    pair_membership: Mapped[DilationPairMember | None] = relationship(back_populates="truss", uselist=False)


class DilationPair(Base):
    __tablename__ = "dilation_pairs"

    id: Mapped[int] = mapped_column(primary_key=True)
    bay_id: Mapped[int] = mapped_column(ForeignKey("bays.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    bay: Mapped[Bay] = relationship(back_populates="dilation_pairs")
    members: Mapped[list[DilationPairMember]] = relationship(
        back_populates="pair", cascade="all, delete-orphan", order_by="DilationPairMember.member_order"
    )


class DilationPairMember(Base):
    __tablename__ = "dilation_pair_members"
    __table_args__ = (
        UniqueConstraint("dilation_pair_id", "member_order", name="uq_pair_member_order"),
        UniqueConstraint("truss_id", name="uq_pair_member_truss"),
        CheckConstraint("member_order IN (1,2)", name="ck_pair_member_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dilation_pair_id: Mapped[int] = mapped_column(ForeignKey("dilation_pairs.id", ondelete="CASCADE"), index=True)
    truss_id: Mapped[int] = mapped_column(ForeignKey("trusses.id", ondelete="RESTRICT"), index=True)
    member_order: Mapped[int] = mapped_column(Integer)

    pair: Mapped[DilationPair] = relationship(back_populates="members")
    truss: Mapped[Truss] = relationship(back_populates="pair_membership")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), index=True)
    bay_id: Mapped[int | None] = mapped_column(ForeignKey("bays.id", ondelete="RESTRICT"), nullable=True, index=True)
    truss_id: Mapped[int | None] = mapped_column(ForeignKey("trusses.id", ondelete="RESTRICT"), nullable=True, index=True)
    technician_name: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(80), index=True)
    field: Mapped[str | None] = mapped_column(String(80), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AppSettings(Base):
    __tablename__ = "app_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_app_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_version: Mapped[int] = mapped_column(Integer, default=1)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
