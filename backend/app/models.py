from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class CatalogSet(Base):
    __tablename__ = "catalog_sets"
    __table_args__ = (
        CheckConstraint("num_parts >= 0", name="ck_catalog_sets_num_parts"),
    )

    set_num: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer)
    theme_id: Mapped[int | None] = mapped_column(Integer)
    theme_name: Mapped[str | None] = mapped_column(String)
    num_parts: Mapped[int] = mapped_column(Integer, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String)
    external_url: Mapped[str | None] = mapped_column(String)
    instructions_url: Mapped[str | None] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CatalogPart(Base):
    __tablename__ = "catalog_parts"

    part_num: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category_name: Mapped[str | None] = mapped_column(String)
    image_url: Mapped[str | None] = mapped_column(String)
    external_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class CatalogColor(Base):
    __tablename__ = "catalog_colors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    rgb_hex: Mapped[str] = mapped_column(String, nullable=False)
    external_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class CatalogSetPart(Base):
    __tablename__ = "catalog_set_parts"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_catalog_set_parts_quantity"),
        UniqueConstraint(
            "set_num",
            "part_num",
            "color_id",
            "is_spare",
            "source_kind",
            "source_id",
            name="uq_catalog_set_parts_source_row",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_num: Mapped[str] = mapped_column(
        ForeignKey("catalog_sets.set_num"), nullable=False, index=True
    )
    part_num: Mapped[str] = mapped_column(
        ForeignKey("catalog_parts.part_num"), nullable=False
    )
    color_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_colors.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    is_spare: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_kind: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)


class OwnedSet(Base):
    __tablename__ = "owned_sets"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_owned_sets_quantity"),
        CheckConstraint(
            "completeness IN ('complete', 'incomplete')",
            name="ck_owned_sets_completeness",
        ),
        CheckConstraint(
            "unknown_missing_count >= 0",
            name="ck_owned_sets_unknown_missing_count",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_num: Mapped[str] = mapped_column(
        ForeignKey("catalog_sets.set_num"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    completeness: Mapped[str] = mapped_column(
        String, nullable=False, default="complete"
    )
    unknown_missing_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    unknown_missing_note: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class OwnedSetMissingPart(Base):
    __tablename__ = "owned_set_missing_parts"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_owned_set_missing_parts_quantity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owned_set_id: Mapped[int] = mapped_column(
        ForeignKey("owned_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part_num: Mapped[str] = mapped_column(
        ForeignKey("catalog_parts.part_num"), nullable=False
    )
    color_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_colors.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class CatalogSetOverride(Base):
    __tablename__ = "catalog_set_overrides"

    set_num: Mapped[str] = mapped_column(
        ForeignKey("catalog_sets.set_num", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str | None] = mapped_column(String)
    year: Mapped[int | None] = mapped_column(Integer)
    theme_name: Mapped[str | None] = mapped_column(String)
    num_parts: Mapped[int | None] = mapped_column(Integer)
    image_url: Mapped[str | None] = mapped_column(String)
    external_url: Mapped[str | None] = mapped_column(String)
    instructions_url: Mapped[str | None] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CatalogSetPartOverride(Base):
    __tablename__ = "catalog_set_part_overrides"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('upsert', 'delete')",
            name="ck_catalog_set_part_overrides_operation",
        ),
        CheckConstraint(
            "(operation = 'upsert' AND quantity > 0) OR "
            "(operation = 'delete' AND quantity IS NULL)",
            name="ck_catalog_set_part_overrides_operation_quantity",
        ),
        UniqueConstraint(
            "set_num",
            "part_num",
            "color_id",
            "is_spare",
            name="uq_catalog_set_part_overrides_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_num: Mapped[str] = mapped_column(
        ForeignKey("catalog_sets.set_num", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    part_num: Mapped[str] = mapped_column(
        ForeignKey("catalog_parts.part_num"), nullable=False
    )
    color_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_colors.id"), nullable=False
    )
    is_spare: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    operation: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class EquivalenceGroup(Base):
    __tablename__ = "equivalence_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class EquivalenceMember(Base):
    __tablename__ = "equivalence_members"

    group_id: Mapped[int] = mapped_column(
        ForeignKey("equivalence_groups.id", ondelete="CASCADE"), primary_key=True
    )
    part_num: Mapped[str] = mapped_column(
        ForeignKey("catalog_parts.part_num"), primary_key=True
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_json: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
