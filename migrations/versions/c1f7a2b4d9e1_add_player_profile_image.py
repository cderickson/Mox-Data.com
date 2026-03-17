"""Add profile_image to player table

Revision ID: c1f7a2b4d9e1
Revises: 9b4f2e0c1a7d
Create Date: 2026-03-16 00:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1f7a2b4d9e1"
down_revision = "9b4f2e0c1a7d"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = [col["name"] for col in inspector.get_columns("player")]
    if "profile_image" not in column_names:
        op.add_column("player", sa.Column("profile_image", sa.String(length=100), nullable=True))
        op.execute("UPDATE player SET profile_image = 'Waterspout-Warden.png' WHERE profile_image IS NULL OR profile_image = ''")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column_names = [col["name"] for col in inspector.get_columns("player")]
    if "profile_image" in column_names:
        op.drop_column("player", "profile_image")
