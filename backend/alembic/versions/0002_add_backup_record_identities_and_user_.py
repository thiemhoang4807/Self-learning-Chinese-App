"""add backup record identities and user preferences

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("theme", sa.String(length=5), server_default="light", nullable=False),
        sa.Column("pinyin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint("theme in ('light','dark')", name="preference_theme_valid"),
        sa.CheckConstraint("id = 1", name="preference_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    if op.get_context().dialect.name == "postgresql":
        generate_uid = "CAST(gen_random_uuid() AS VARCHAR(36))"
    else:
        generate_uid = (
            "lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || "
            "'-4' || substr(hex(randomblob(2)), 2) || "
            "'-' || substr('89ab', (random() & 3) + 1, 1) || substr(hex(randomblob(2)), 2) || "
            "'-' || hex(randomblob(6)))"
        )
    # Adding nullable columns in place avoids rebuilding SQLite tables with cascading foreign keys.
    for table_name in ("review_logs", "sources", "story_attempts"):
        op.add_column(table_name, sa.Column("backup_uid", sa.String(length=36), nullable=True))
        table = sa.table(table_name, sa.column("backup_uid"))
        op.execute(table.update().where(table.c.backup_uid.is_(None)).values(backup_uid=sa.literal_column(generate_uid)))
        op.create_index(f"ix_{table_name}_backup_uid", table_name, ["backup_uid"], unique=True)


def downgrade() -> None:
    for table_name in ("story_attempts", "sources", "review_logs"):
        op.drop_index(f"ix_{table_name}_backup_uid", table_name=table_name)
        op.drop_column(table_name, "backup_uid")
    op.drop_table("user_preferences")
