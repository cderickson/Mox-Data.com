"""Add export_job table for async exports

Revision ID: b8c4d1e2f9a0
Revises: 7a1d3f9e2c4b
Create Date: 2026-03-16 16:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b8c4d1e2f9a0"
down_revision = "7a1d3f9e2c4b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "export_job",
        sa.Column("export_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("storage_type", sa.String(length=10), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("cleaned_at", sa.DateTime(), nullable=True),
        sa.Column("zip_key", sa.String(length=512), nullable=True),
        sa.Column("file_keys", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("export_id"),
    )


def downgrade():
    op.drop_table("export_job")
