"""Add limited_format to match table

Revision ID: 9b4f2e0c1a7d
Revises: 53d5e7b403c0
Create Date: 2026-03-15 18:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9b4f2e0c1a7d"
down_revision = "53d5e7b403c0"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = [col["name"] for col in inspector.get_columns("match")]
    if "limited_format" not in column_names:
        op.add_column("match", sa.Column("limited_format", sa.String(length=20), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = [col["name"] for col in inspector.get_columns("match")]
    if "limited_format" in column_names:
        op.drop_column("match", "limited_format")
