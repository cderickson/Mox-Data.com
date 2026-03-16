"""Initial full schema

Revision ID: 53d5e7b403c0
Revises:
Create Date: 2026-03-14 21:24:39.209459

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '53d5e7b403c0'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('all_decks',
    sa.Column('yyyy_mm', sa.String(length=7), nullable=False),
    sa.Column('deck_nm', sa.String(length=75), nullable=False),
    sa.Column('format_nm', sa.String(length=30), nullable=False),
    sa.Column('deck_lst', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('yyyy_mm', 'deck_nm', 'format_nm')
    )
    op.create_table('cards_played',
    sa.Column('uid', sa.Integer(), nullable=False),
    sa.Column('match_id', sa.String(length=75), nullable=False),
    sa.Column('casting_player1', sa.String(length=30), nullable=True),
    sa.Column('casting_player2', sa.String(length=30), nullable=True),
    sa.Column('plays1', sa.PickleType(), nullable=True),
    sa.Column('plays2', sa.PickleType(), nullable=True),
    sa.Column('lands1', sa.PickleType(), nullable=True),
    sa.Column('lands2', sa.PickleType(), nullable=True),
    sa.Column('proc_dt', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('uid', 'match_id')
    )
    op.create_table('game_actions',
    sa.Column('uid', sa.Integer(), nullable=False),
    sa.Column('match_id', sa.String(length=75), nullable=False),
    sa.Column('game_num', sa.Integer(), nullable=False),
    sa.Column('game_actions', sa.String(length=5000), nullable=True),
    sa.Column('proc_dt', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('uid', 'match_id', 'game_num')
    )
    op.create_table('input_options',
    sa.Column('table_nm', sa.String(length=20), nullable=False),
    sa.Column('var_nm', sa.String(length=40), nullable=False),
    sa.Column('options_lst', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('table_nm', 'var_nm')
    )
    op.create_table('multifaced_cards',
    sa.Column('front_nm', sa.String(length=50), nullable=False),
    sa.Column('back_nm', sa.String(length=50), nullable=False),
    sa.Column('mult_type', sa.String(length=20), nullable=False),
    sa.CheckConstraint("mult_type IN ('SPLIT', 'TRANSFORM', 'DFC', 'MDFC', 'ADVENTURE')", name='ck_multifaced_cards_mult_type'),
    sa.PrimaryKeyConstraint('front_nm', 'back_nm', 'mult_type')
    )
    op.create_table('player',
    sa.Column('uid', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(length=150), nullable=True),
    sa.Column('pwd', sa.String(length=150), nullable=True),
    sa.Column('username', sa.String(length=30), nullable=True),
    sa.Column('created_on', sa.DateTime(), nullable=True),
    sa.Column('is_admin', sa.Boolean(), nullable=True),
    sa.Column('is_confirmed', sa.Boolean(), nullable=True),
    sa.Column('confirmed_on', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('uid'),
    sa.UniqueConstraint('email')
    )
    op.create_table('removed',
    sa.Column('uid', sa.Integer(), nullable=False),
    sa.Column('match_id', sa.String(length=75), nullable=False),
    sa.Column('date', sa.String(length=20), nullable=True),
    sa.Column('reason', sa.String(length=20), nullable=True),
    sa.Column('proc_dt', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('uid', 'match_id')
    )
    op.create_table('task_history',
    sa.Column('task_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('uid', sa.Integer(), nullable=True),
    sa.Column('curr_username', sa.String(length=30), nullable=True),
    sa.Column('submit_date', sa.DateTime(), nullable=True),
    sa.Column('complete_date', sa.DateTime(), nullable=True),
    sa.Column('task_type', sa.String(length=35), nullable=True),
    sa.Column('error_code', sa.String(length=50), nullable=True),
    sa.PrimaryKeyConstraint('task_id')
    )
    op.create_table('draft',
    sa.Column('uid', sa.Integer(), nullable=False),
    sa.Column('draft_id', sa.String(length=75), nullable=False),
    sa.Column('hero', sa.String(length=30), nullable=False),
    sa.Column('player2', sa.String(length=30), nullable=True),
    sa.Column('player3', sa.String(length=30), nullable=True),
    sa.Column('player4', sa.String(length=30), nullable=True),
    sa.Column('player5', sa.String(length=30), nullable=True),
    sa.Column('player6', sa.String(length=30), nullable=True),
    sa.Column('player7', sa.String(length=30), nullable=True),
    sa.Column('player8', sa.String(length=30), nullable=True),
    sa.Column('match_wins', sa.Integer(), nullable=True),
    sa.Column('match_losses', sa.Integer(), nullable=True),
    sa.Column('draft_format', sa.String(length=20), nullable=True),
    sa.Column('date', sa.String(length=20), nullable=True),
    sa.Column('proc_dt', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['uid'], ['player.uid'], ),
    sa.PrimaryKeyConstraint('uid', 'draft_id', 'hero')
    )
    op.create_table('game',
    sa.Column('uid', sa.Integer(), nullable=False),
    sa.Column('match_id', sa.String(length=75), nullable=False),
    sa.Column('p1', sa.String(length=30), nullable=False),
    sa.Column('p2', sa.String(length=30), nullable=True),
    sa.Column('game_num', sa.Integer(), nullable=False),
    sa.Column('pd_selector', sa.String(length=2), nullable=True),
    sa.Column('pd_choice', sa.String(length=4), nullable=True),
    sa.Column('on_play', sa.String(length=2), nullable=True),
    sa.Column('on_draw', sa.String(length=2), nullable=True),
    sa.Column('p1_mulls', sa.Integer(), nullable=True),
    sa.Column('p2_mulls', sa.Integer(), nullable=True),
    sa.Column('turns', sa.Integer(), nullable=True),
    sa.Column('game_winner', sa.String(length=2), nullable=True),
    sa.Column('proc_dt', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['uid'], ['player.uid'], ),
    sa.PrimaryKeyConstraint('uid', 'match_id', 'p1', 'game_num')
    )
    op.create_table('match',
    sa.Column('uid', sa.Integer(), nullable=False),
    sa.Column('match_id', sa.String(length=75), nullable=False),
    sa.Column('draft_id', sa.String(length=75), nullable=True),
    sa.Column('p1', sa.String(length=30), nullable=False),
    sa.Column('p1_arch', sa.String(length=15), nullable=True),
    sa.Column('p1_subarch', sa.String(length=30), nullable=True),
    sa.Column('p2', sa.String(length=30), nullable=True),
    sa.Column('p2_arch', sa.String(length=15), nullable=True),
    sa.Column('p2_subarch', sa.String(length=30), nullable=True),
    sa.Column('p1_roll', sa.Integer(), nullable=True),
    sa.Column('p2_roll', sa.Integer(), nullable=True),
    sa.Column('roll_winner', sa.String(length=2), nullable=True),
    sa.Column('p1_wins', sa.Integer(), nullable=True),
    sa.Column('p2_wins', sa.Integer(), nullable=True),
    sa.Column('match_winner', sa.String(length=2), nullable=True),
    sa.Column('format', sa.String(length=20), nullable=True),
    sa.Column('match_type', sa.String(length=30), nullable=True),
    sa.Column('date', sa.String(length=20), nullable=True),
    sa.Column('proc_dt', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['uid'], ['player.uid'], ),
    sa.PrimaryKeyConstraint('uid', 'match_id', 'p1')
    )
    op.create_table('pick',
    sa.Column('uid', sa.Integer(), nullable=False),
    sa.Column('draft_id', sa.String(length=75), nullable=False),
    sa.Column('card', sa.String(length=50), nullable=True),
    sa.Column('pack_num', sa.Integer(), nullable=True),
    sa.Column('pick_num', sa.Integer(), nullable=True),
    sa.Column('pick_ovr', sa.Integer(), nullable=False),
    sa.Column('avail1', sa.String(length=75), nullable=True),
    sa.Column('avail2', sa.String(length=75), nullable=True),
    sa.Column('avail3', sa.String(length=75), nullable=True),
    sa.Column('avail4', sa.String(length=75), nullable=True),
    sa.Column('avail5', sa.String(length=75), nullable=True),
    sa.Column('avail6', sa.String(length=75), nullable=True),
    sa.Column('avail7', sa.String(length=75), nullable=True),
    sa.Column('avail8', sa.String(length=75), nullable=True),
    sa.Column('avail9', sa.String(length=75), nullable=True),
    sa.Column('avail10', sa.String(length=75), nullable=True),
    sa.Column('avail11', sa.String(length=75), nullable=True),
    sa.Column('avail12', sa.String(length=75), nullable=True),
    sa.Column('avail13', sa.String(length=75), nullable=True),
    sa.Column('avail14', sa.String(length=75), nullable=True),
    sa.Column('proc_dt', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['uid'], ['player.uid'], ),
    sa.PrimaryKeyConstraint('uid', 'draft_id', 'pick_ovr')
    )
    op.create_table('play',
    sa.Column('uid', sa.Integer(), nullable=False),
    sa.Column('match_id', sa.String(length=75), nullable=False),
    sa.Column('game_num', sa.Integer(), nullable=False),
    sa.Column('play_num', sa.Integer(), nullable=False),
    sa.Column('turn_num', sa.Integer(), nullable=True),
    sa.Column('casting_player', sa.String(length=30), nullable=True),
    sa.Column('action', sa.String(length=20), nullable=True),
    sa.Column('primary_card', sa.String(length=50), nullable=True),
    sa.Column('target_list', sa.JSON(), nullable=True),
    sa.Column('opp_target', sa.Integer(), nullable=True),
    sa.Column('self_target', sa.Integer(), nullable=True),
    sa.Column('cards_drawn', sa.Integer(), nullable=True),
    sa.Column('attacker_list', sa.JSON(), nullable=True),
    sa.Column('attackers', sa.Integer(), nullable=True),
    sa.Column('active_player', sa.String(length=30), nullable=True),
    sa.Column('non_active_player', sa.String(length=30), nullable=True),
    sa.Column('proc_dt', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['uid'], ['player.uid'], ),
    sa.PrimaryKeyConstraint('uid', 'match_id', 'game_num', 'play_num')
    )

def downgrade():
    op.drop_table('play')
    op.drop_table('pick')
    op.drop_table('match')
    op.drop_table('game')
    op.drop_table('draft')
    op.drop_table('task_history')
    op.drop_table('removed')
    op.drop_table('player')
    op.drop_table('input_options')
    op.drop_table('multifaced_cards')
    op.drop_table('game_actions')
    op.drop_table('cards_played')
    op.drop_table('all_decks')