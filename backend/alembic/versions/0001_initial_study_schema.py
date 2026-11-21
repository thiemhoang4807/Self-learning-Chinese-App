"""initial study schema

Revision ID: 0001
Revises: none
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'characters',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('char', sa.String(length=1), nullable=False),
        sa.Column('pinyin', sa.String(length=60), server_default='', nullable=False),
        sa.Column('han_viet', sa.String(length=100), server_default='', nullable=False),
        sa.Column('radical', sa.String(length=60), server_default='', nullable=False),
        sa.Column('components_json', sa.JSON(), server_default='[]', nullable=False),
        sa.Column('mnemonic_vi', sa.Text(), server_default='', nullable=False),
        sa.Column('hsk_level', sa.Integer(), nullable=True),
        sa.CheckConstraint('hsk_level between 1 and 5', name='character_level_valid'),
        sa.CheckConstraint('length(char) = 1', name='character_single'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('char'),
    )
    op.create_table(
        'grammar_patterns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pattern_formula', sa.String(length=250), nullable=False),
        sa.Column('title_vi', sa.String(length=250), nullable=False),
        sa.Column('explanation_vi', sa.Text(), nullable=False),
        sa.Column('hsk_level', sa.Integer(), nullable=True),
        sa.Column('structure_notes_vi', sa.Text(), server_default='', nullable=False),
        sa.CheckConstraint('hsk_level between 1 and 5', name='pattern_level_valid'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pattern_formula'),
    )
    op.create_table(
        'sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=250), nullable=False),
        sa.Column('source_type', sa.String(length=12), nullable=False),
        sa.Column('summary_note', sa.Text(), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("source_type in ('image','pdf','pptx','docx','xlsx','text','paste')", name='source_type_valid'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'story_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('target_words', sa.JSON(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('feedback', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('score between 0 and 100', name='story_score_valid'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_story_attempts_created_at'), 'story_attempts', ['created_at'], unique=False)
    op.create_table(
        'user_cards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_type', sa.String(length=16), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='new', nullable=False),
        sa.Column('fsrs_state_json', sa.JSON(), nullable=True),
        sa.Column('due', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('wrong_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('reps', sa.Integer(), server_default='0', nullable=False),
        sa.Column('lapses', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_leech', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint("item_type in ('word','pattern','confusable')", name='card_type_valid'),
        sa.CheckConstraint("status in ('new','learning','review','mastered','ignored')", name='card_status_valid'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('item_type', 'item_id'),
    )
    op.create_index('ix_user_cards_status_due', 'user_cards', ['status', 'due'], unique=False)
    op.create_table(
        'words',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('simplified', sa.String(length=100), nullable=False),
        sa.Column('traditional', sa.String(length=100), nullable=True),
        sa.Column('pinyin', sa.String(length=200), nullable=False),
        sa.Column('han_viet', sa.String(length=200), server_default='', nullable=False),
        sa.Column('meaning_vi', sa.Text(), nullable=False),
        sa.Column('pos', sa.String(length=100), server_default='', nullable=False),
        sa.Column('hsk_level', sa.Integer(), nullable=True),
        sa.Column('mnemonic_vi', sa.Text(), server_default='', nullable=False),
        sa.Column('usage_note_vi', sa.Text(), server_default='', nullable=False),
        sa.Column('audio_path', sa.String(length=255), nullable=True),
        sa.CheckConstraint('hsk_level between 1 and 5', name='word_level_valid'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('simplified'),
    )
    op.create_index(op.f('ix_words_hsk_level'), 'words', ['hsk_level'], unique=False)
    op.create_table(
        'confusable_pairs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('word_a_id', sa.Integer(), nullable=False),
        sa.Column('word_b_id', sa.Integer(), nullable=False),
        sa.Column('diff_explanation_vi', sa.Text(), nullable=False),
        sa.Column('cloze_a_hanzi', sa.Text(), nullable=False),
        sa.Column('cloze_a_answer', sa.String(length=100), nullable=False),
        sa.Column('cloze_b_hanzi', sa.Text(), nullable=False),
        sa.Column('cloze_b_answer', sa.String(length=100), nullable=False),
        sa.Column('hsk_level', sa.Integer(), nullable=False),
        sa.CheckConstraint('hsk_level between 1 and 5', name='confusable_level_valid'),
        sa.CheckConstraint('word_a_id <> word_b_id', name='confusable_distinct_words'),
        sa.ForeignKeyConstraint(['word_a_id'], ['words.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['word_b_id'], ['words.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('word_a_id', 'word_b_id'),
    )
    op.create_index(op.f('ix_confusable_pairs_word_b_id'), 'confusable_pairs', ['word_b_id'], unique=False)
    op.create_table(
        'review_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('card_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('drill_mode', sa.String(length=24), nullable=False),
        sa.Column('response_ms', sa.Integer(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('review_token', sa.String(length=64), nullable=True),
        sa.CheckConstraint('rating between 1 and 4', name='review_rating_valid'),
        sa.CheckConstraint('response_ms >= 0', name='review_time_valid'),
        sa.ForeignKeyConstraint(['card_id'], ['user_cards.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('review_token'),
    )
    op.create_index(op.f('ix_review_logs_card_id'), 'review_logs', ['card_id'], unique=False)
    op.create_index(op.f('ix_review_logs_reviewed_at'), 'review_logs', ['reviewed_at'], unique=False)
    op.create_table(
        'sentences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('hanzi', sa.String(length=600), nullable=False),
        sa.Column('pinyin', sa.Text(), nullable=False),
        sa.Column('meaning_vi', sa.Text(), nullable=False),
        sa.Column('audio_path', sa.String(length=255), nullable=True),
        sa.Column('grammar_pattern_id', sa.Integer(), nullable=True),
        sa.Column('is_ai_generated', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['grammar_pattern_id'], ['grammar_patterns.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('hanzi'),
    )
    op.create_index(op.f('ix_sentences_grammar_pattern_id'), 'sentences', ['grammar_pattern_id'], unique=False)
    op.create_table(
        'source_patterns',
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('pattern_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['pattern_id'], ['grammar_patterns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('source_id', 'pattern_id'),
    )
    op.create_index(op.f('ix_source_patterns_pattern_id'), 'source_patterns', ['pattern_id'], unique=False)
    op.create_table(
        'source_words',
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('word_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['word_id'], ['words.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('source_id', 'word_id'),
    )
    op.create_index(op.f('ix_source_words_word_id'), 'source_words', ['word_id'], unique=False)
    op.create_table(
        'word_characters',
        sa.Column('word_id', sa.Integer(), nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.CheckConstraint('position >= 0', name='character_position_valid'),
        sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['word_id'], ['words.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('word_id', 'position'),
    )
    op.create_index(op.f('ix_word_characters_character_id'), 'word_characters', ['character_id'], unique=False)
    op.create_table(
        'sentence_words',
        sa.Column('sentence_id', sa.Integer(), nullable=False),
        sa.Column('word_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['sentence_id'], ['sentences.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['word_id'], ['words.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('sentence_id', 'word_id'),
    )
    op.create_index(op.f('ix_sentence_words_word_id'), 'sentence_words', ['word_id'], unique=False)
    op.create_table(
        'source_sentences',
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('sentence_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['sentence_id'], ['sentences.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('source_id', 'sentence_id'),
    )
    op.create_index(op.f('ix_source_sentences_sentence_id'), 'source_sentences', ['sentence_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_source_sentences_sentence_id'), table_name='source_sentences')
    op.drop_table('source_sentences')
    op.drop_index(op.f('ix_sentence_words_word_id'), table_name='sentence_words')
    op.drop_table('sentence_words')
    op.drop_index(op.f('ix_word_characters_character_id'), table_name='word_characters')
    op.drop_table('word_characters')
    op.drop_index(op.f('ix_source_words_word_id'), table_name='source_words')
    op.drop_table('source_words')
    op.drop_index(op.f('ix_source_patterns_pattern_id'), table_name='source_patterns')
    op.drop_table('source_patterns')
    op.drop_index(op.f('ix_sentences_grammar_pattern_id'), table_name='sentences')
    op.drop_table('sentences')
    op.drop_index(op.f('ix_review_logs_reviewed_at'), table_name='review_logs')
    op.drop_index(op.f('ix_review_logs_card_id'), table_name='review_logs')
    op.drop_table('review_logs')
    op.drop_index(op.f('ix_confusable_pairs_word_b_id'), table_name='confusable_pairs')
    op.drop_table('confusable_pairs')
    op.drop_index(op.f('ix_words_hsk_level'), table_name='words')
    op.drop_table('words')
    op.drop_index('ix_user_cards_status_due', table_name='user_cards')
    op.drop_table('user_cards')
    op.drop_index(op.f('ix_story_attempts_created_at'), table_name='story_attempts')
    op.drop_table('story_attempts')
    op.drop_table('sources')
    op.drop_table('grammar_patterns')
    op.drop_table('characters')
