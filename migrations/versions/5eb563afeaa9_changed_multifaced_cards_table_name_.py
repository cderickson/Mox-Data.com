"""changed multifaced_cards table name. increased all_decks.deck_nm length, input_options.var_nm length, removed fkey relationship on draft -> player.

Revision ID: 5eb563afeaa9
Revises: b8c4d1e2f9a0
Create Date: 2026-03-29 16:01:30.798983

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5eb563afeaa9'
down_revision = 'b8c4d1e2f9a0'
branch_labels = None
depends_on = None


def _table_exists(inspector, table_name):
    return table_name in inspector.get_table_names()


def _drop_table_if_exists(inspector, table_name):
    if _table_exists(inspector, table_name):
        op.drop_table(table_name)


def _column_length(inspector, table_name, column_name):
    for col in inspector.get_columns(table_name):
        if col.get("name") == column_name:
            col_type = col.get("type")
            return getattr(col_type, "length", None)
    return None


def _has_fk(inspector, table_name, constrained_cols, referred_table, referred_cols):
    for fk in inspector.get_foreign_keys(table_name):
        if (
            (fk.get("constrained_columns") or []) == constrained_cols
            and fk.get("referred_table") == referred_table
            and (fk.get("referred_columns") or []) == referred_cols
        ):
            return True
    return False


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _drop_table_if_exists(inspector, "_alembic_tmp_all_decks")
    _drop_table_if_exists(inspector, "_alembic_tmp_input_options")
    _drop_table_if_exists(inspector, "_alembic_tmp_draft")
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "multifaced_card"):
        op.drop_table("multifaced_card")

    if _table_exists(inspector, "all_decks") and _column_length(inspector, "all_decks", "deck_nm") == 50:
        with op.batch_alter_table("all_decks", schema=None) as batch_op:
            batch_op.alter_column(
                "deck_nm",
                existing_type=sa.VARCHAR(length=50),
                type_=sa.String(length=75),
                existing_nullable=False,
            )

    if _table_exists(inspector, "draft") and _table_exists(inspector, "player"):
        if not _has_fk(inspector, "draft", ["uid"], "player", ["uid"]):
            with op.batch_alter_table("draft", schema=None) as batch_op:
                batch_op.create_foreign_key(
                    "fk_draft_uid_player_uid",
                    "player",
                    ["uid"],
                    ["uid"],
                )

    if _table_exists(inspector, "input_options") and _column_length(inspector, "input_options", "var_nm") == 20:
        with op.batch_alter_table("input_options", schema=None) as batch_op:
            batch_op.alter_column(
                "var_nm",
                existing_type=sa.VARCHAR(length=20),
                type_=sa.String(length=40),
                existing_nullable=False,
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _drop_table_if_exists(inspector, "_alembic_tmp_all_decks")
    _drop_table_if_exists(inspector, "_alembic_tmp_input_options")
    _drop_table_if_exists(inspector, "_alembic_tmp_draft")
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "input_options") and _column_length(inspector, "input_options", "var_nm") == 40:
        with op.batch_alter_table("input_options", schema=None) as batch_op:
            batch_op.alter_column(
                "var_nm",
                existing_type=sa.String(length=40),
                type_=sa.VARCHAR(length=20),
                existing_nullable=False,
            )

    if _table_exists(inspector, "draft"):
        fk_names = {fk.get("name") for fk in inspector.get_foreign_keys("draft")}
        if "fk_draft_uid_player_uid" in fk_names:
            with op.batch_alter_table("draft", schema=None) as batch_op:
                batch_op.drop_constraint("fk_draft_uid_player_uid", type_="foreignkey")

    if _table_exists(inspector, "all_decks") and _column_length(inspector, "all_decks", "deck_nm") == 75:
        with op.batch_alter_table("all_decks", schema=None) as batch_op:
            batch_op.alter_column(
                "deck_nm",
                existing_type=sa.String(length=75),
                type_=sa.VARCHAR(length=50),
                existing_nullable=False,
            )

    if not _table_exists(inspector, "multifaced_card"):
        op.create_table(
            "multifaced_card",
            sa.Column("front_nm", sa.VARCHAR(length=50), nullable=False),
            sa.Column("back_nm", sa.VARCHAR(length=50), nullable=False),
            sa.Column("mult_type", sa.VARCHAR(length=20), nullable=False),
            sa.CheckConstraint(
                "mult_type IN ('SPLIT', 'TRANSFORM', 'DFC', 'MDFC', 'ADVENTURE')",
                name=op.f("ck_multifaced_card_mult_type"),
            ),
            sa.PrimaryKeyConstraint("front_nm", "back_nm"),
        )
