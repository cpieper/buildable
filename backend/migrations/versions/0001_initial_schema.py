"""Create the catalog and collection persistence schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_sets",
        sa.Column("set_num", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("theme_id", sa.Integer(), nullable=True),
        sa.Column("theme_name", sa.String(), nullable=True),
        sa.Column("num_parts", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("external_url", sa.String(), nullable=True),
        sa.Column("instructions_url", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("num_parts >= 0", name="ck_catalog_sets_num_parts"),
        sa.PrimaryKeyConstraint("set_num"),
    )
    op.create_table(
        "catalog_parts",
        sa.Column("part_num", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category_name", sa.String(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column(
            "external_ids_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.PrimaryKeyConstraint("part_num"),
    )
    op.create_table(
        "catalog_colors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("rgb_hex", sa.String(), nullable=False),
        sa.Column(
            "external_ids_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("secret", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "equivalence_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "catalog_set_parts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("set_num", sa.String(), nullable=False),
        sa.Column("part_num", sa.String(), nullable=False),
        sa.Column("color_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "is_spare", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_catalog_set_parts_quantity"),
        sa.ForeignKeyConstraint(["color_id"], ["catalog_colors.id"]),
        sa.ForeignKeyConstraint(["part_num"], ["catalog_parts.part_num"]),
        sa.ForeignKeyConstraint(["set_num"], ["catalog_sets.set_num"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "set_num",
            "part_num",
            "color_id",
            "is_spare",
            "source_kind",
            "source_id",
            name="uq_catalog_set_parts_source_row",
        ),
    )
    op.create_index(
        op.f("ix_catalog_set_parts_set_num"),
        "catalog_set_parts",
        ["set_num"],
        unique=False,
    )
    op.create_table(
        "owned_sets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("set_num", sa.String(), nullable=False),
        sa.Column(
            "quantity", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "completeness",
            sa.String(),
            nullable=False,
            server_default=sa.text("'complete'"),
        ),
        sa.Column(
            "unknown_missing_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("unknown_missing_note", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("quantity > 0", name="ck_owned_sets_quantity"),
        sa.CheckConstraint(
            "completeness IN ('complete', 'incomplete')",
            name="ck_owned_sets_completeness",
        ),
        sa.CheckConstraint(
            "unknown_missing_count >= 0",
            name="ck_owned_sets_unknown_missing_count",
        ),
        sa.ForeignKeyConstraint(["set_num"], ["catalog_sets.set_num"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_owned_sets_set_num"), "owned_sets", ["set_num"], unique=False
    )
    op.create_table(
        "catalog_set_overrides",
        sa.Column("set_num", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("theme_name", sa.String(), nullable=True),
        sa.Column("num_parts", sa.Integer(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("external_url", sa.String(), nullable=True),
        sa.Column("instructions_url", sa.String(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["set_num"], ["catalog_sets.set_num"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("set_num"),
    )
    op.create_table(
        "catalog_set_part_overrides",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("set_num", sa.String(), nullable=False),
        sa.Column("part_num", sa.String(), nullable=False),
        sa.Column("color_id", sa.Integer(), nullable=False),
        sa.Column(
            "is_spare", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "operation IN ('upsert', 'delete')",
            name="ck_catalog_set_part_overrides_operation",
        ),
        sa.CheckConstraint(
            "(operation = 'upsert' AND quantity > 0) OR "
            "(operation = 'delete' AND quantity IS NULL)",
            name="ck_catalog_set_part_overrides_operation_quantity",
        ),
        sa.ForeignKeyConstraint(["color_id"], ["catalog_colors.id"]),
        sa.ForeignKeyConstraint(["part_num"], ["catalog_parts.part_num"]),
        sa.ForeignKeyConstraint(
            ["set_num"], ["catalog_sets.set_num"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "set_num",
            "part_num",
            "color_id",
            "is_spare",
            name="uq_catalog_set_part_overrides_identity",
        ),
    )
    op.create_index(
        op.f("ix_catalog_set_part_overrides_set_num"),
        "catalog_set_part_overrides",
        ["set_num"],
        unique=False,
    )
    op.create_table(
        "owned_set_missing_parts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owned_set_id", sa.Integer(), nullable=False),
        sa.Column("part_num", sa.String(), nullable=False),
        sa.Column("color_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_owned_set_missing_parts_quantity"),
        sa.ForeignKeyConstraint(["color_id"], ["catalog_colors.id"]),
        sa.ForeignKeyConstraint(
            ["owned_set_id"], ["owned_sets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["part_num"], ["catalog_parts.part_num"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_owned_set_missing_parts_owned_set_id"),
        "owned_set_missing_parts",
        ["owned_set_id"],
        unique=False,
    )
    op.create_table(
        "equivalence_members",
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("part_num", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"], ["equivalence_groups.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["part_num"], ["catalog_parts.part_num"]),
        sa.PrimaryKeyConstraint("group_id", "part_num"),
    )


def downgrade() -> None:
    op.drop_table("equivalence_members")
    op.drop_index(
        op.f("ix_owned_set_missing_parts_owned_set_id"),
        table_name="owned_set_missing_parts",
    )
    op.drop_table("owned_set_missing_parts")
    op.drop_index(
        op.f("ix_catalog_set_part_overrides_set_num"),
        table_name="catalog_set_part_overrides",
    )
    op.drop_table("catalog_set_part_overrides")
    op.drop_table("catalog_set_overrides")
    op.drop_index(op.f("ix_owned_sets_set_num"), table_name="owned_sets")
    op.drop_table("owned_sets")
    op.drop_index(op.f("ix_catalog_set_parts_set_num"), table_name="catalog_set_parts")
    op.drop_table("catalog_set_parts")
    op.drop_table("sync_runs")
    op.drop_table("equivalence_groups")
    op.drop_table("app_settings")
    op.drop_table("catalog_colors")
    op.drop_table("catalog_parts")
    op.drop_table("catalog_sets")
