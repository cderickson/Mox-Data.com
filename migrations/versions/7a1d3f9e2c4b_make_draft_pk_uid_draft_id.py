"""Make draft primary key uid + draft_id

Revision ID: 7a1d3f9e2c4b
Revises: c1f7a2b4d9e1
Create Date: 2026-03-16 14:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7a1d3f9e2c4b"
down_revision = "c1f7a2b4d9e1"
branch_labels = None
depends_on = None


def _row_sort_key(row):
    # Prefer the most recently processed row if duplicates exist.
    return (
        row.get("proc_dt") is not None,
        row.get("proc_dt"),
        row.get("date") or "",
        row.get("hero") or "",
    )


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    pk_cols = (inspector.get_pk_constraint("draft") or {}).get("constrained_columns") or []
    if pk_cols == ["uid", "draft_id"]:
        return

    metadata = sa.MetaData()
    draft_old = sa.Table("draft", metadata, autoload_with=bind)
    rows = bind.execute(sa.select(draft_old)).mappings().all()

    # If duplicate (uid, draft_id) rows exist, keep the most recent one.
    deduped = {}
    for row in rows:
        row_dict = dict(row)
        key = (row_dict["uid"], row_dict["draft_id"])
        current = deduped.get(key)
        if current is None or _row_sort_key(row_dict) > _row_sort_key(current):
            deduped[key] = row_dict

    op.create_table(
        "draft_tmp",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("draft_id", sa.String(length=75), nullable=False),
        sa.Column("hero", sa.String(length=30), nullable=True),
        sa.Column("player2", sa.String(length=30), nullable=True),
        sa.Column("player3", sa.String(length=30), nullable=True),
        sa.Column("player4", sa.String(length=30), nullable=True),
        sa.Column("player5", sa.String(length=30), nullable=True),
        sa.Column("player6", sa.String(length=30), nullable=True),
        sa.Column("player7", sa.String(length=30), nullable=True),
        sa.Column("player8", sa.String(length=30), nullable=True),
        sa.Column("match_wins", sa.Integer(), nullable=True),
        sa.Column("match_losses", sa.Integer(), nullable=True),
        sa.Column("draft_format", sa.String(length=20), nullable=True),
        sa.Column("date", sa.String(length=20), nullable=True),
        sa.Column("proc_dt", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("uid", "draft_id"),
    )

    if deduped:
        draft_tmp = sa.table(
            "draft_tmp",
            sa.column("uid", sa.Integer()),
            sa.column("draft_id", sa.String()),
            sa.column("hero", sa.String()),
            sa.column("player2", sa.String()),
            sa.column("player3", sa.String()),
            sa.column("player4", sa.String()),
            sa.column("player5", sa.String()),
            sa.column("player6", sa.String()),
            sa.column("player7", sa.String()),
            sa.column("player8", sa.String()),
            sa.column("match_wins", sa.Integer()),
            sa.column("match_losses", sa.Integer()),
            sa.column("draft_format", sa.String()),
            sa.column("date", sa.String()),
            sa.column("proc_dt", sa.DateTime()),
        )
        op.bulk_insert(draft_tmp, list(deduped.values()))

    op.drop_table("draft")
    op.rename_table("draft_tmp", "draft")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    pk_cols = (inspector.get_pk_constraint("draft") or {}).get("constrained_columns") or []
    if pk_cols == ["uid", "draft_id", "hero"]:
        return

    metadata = sa.MetaData()
    draft_old = sa.Table("draft", metadata, autoload_with=bind)
    rows = bind.execute(sa.select(draft_old)).mappings().all()

    op.create_table(
        "draft_tmp",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("draft_id", sa.String(length=75), nullable=False),
        sa.Column("hero", sa.String(length=30), nullable=False),
        sa.Column("player2", sa.String(length=30), nullable=True),
        sa.Column("player3", sa.String(length=30), nullable=True),
        sa.Column("player4", sa.String(length=30), nullable=True),
        sa.Column("player5", sa.String(length=30), nullable=True),
        sa.Column("player6", sa.String(length=30), nullable=True),
        sa.Column("player7", sa.String(length=30), nullable=True),
        sa.Column("player8", sa.String(length=30), nullable=True),
        sa.Column("match_wins", sa.Integer(), nullable=True),
        sa.Column("match_losses", sa.Integer(), nullable=True),
        sa.Column("draft_format", sa.String(length=20), nullable=True),
        sa.Column("date", sa.String(length=20), nullable=True),
        sa.Column("proc_dt", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("uid", "draft_id", "hero"),
    )

    if rows:
        # Ensure hero is non-null for downgraded PK.
        normalized_rows = []
        for row in rows:
            row_dict = dict(row)
            row_dict["hero"] = row_dict.get("hero") or ""
            normalized_rows.append(row_dict)

        draft_tmp = sa.table(
            "draft_tmp",
            sa.column("uid", sa.Integer()),
            sa.column("draft_id", sa.String()),
            sa.column("hero", sa.String()),
            sa.column("player2", sa.String()),
            sa.column("player3", sa.String()),
            sa.column("player4", sa.String()),
            sa.column("player5", sa.String()),
            sa.column("player6", sa.String()),
            sa.column("player7", sa.String()),
            sa.column("player8", sa.String()),
            sa.column("match_wins", sa.Integer()),
            sa.column("match_losses", sa.Integer()),
            sa.column("draft_format", sa.String()),
            sa.column("date", sa.String()),
            sa.column("proc_dt", sa.DateTime()),
        )
        op.bulk_insert(draft_tmp, normalized_rows)

    op.drop_table("draft")
    op.rename_table("draft_tmp", "draft")
