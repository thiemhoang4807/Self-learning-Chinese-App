from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, false, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("source_type in ('image','pdf','pptx','docx','xlsx','text','paste')", name="source_type_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(250))
    source_type: Mapped[str] = mapped_column(String(12))
    summary_note: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (
        CheckConstraint("length(char) = 1", name="character_single"),
        CheckConstraint("hsk_level between 1 and 5", name="character_level_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    char: Mapped[str] = mapped_column(String(1), unique=True)
    pinyin: Mapped[str] = mapped_column(String(60), default="", server_default="")
    han_viet: Mapped[str] = mapped_column(String(100), default="", server_default="")
    radical: Mapped[str] = mapped_column(String(60), default="", server_default="")
    components_json: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    mnemonic_vi: Mapped[str] = mapped_column(Text, default="", server_default="")
    hsk_level: Mapped[int | None]


class Word(Base):
    __tablename__ = "words"
    __table_args__ = (CheckConstraint("hsk_level between 1 and 5", name="word_level_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    simplified: Mapped[str] = mapped_column(String(100), unique=True)
    traditional: Mapped[str | None] = mapped_column(String(100))
    pinyin: Mapped[str] = mapped_column(String(200))
    han_viet: Mapped[str] = mapped_column(String(200), default="", server_default="")
    meaning_vi: Mapped[str] = mapped_column(Text)
    pos: Mapped[str] = mapped_column(String(100), default="", server_default="")
    hsk_level: Mapped[int | None] = mapped_column(index=True)
    mnemonic_vi: Mapped[str] = mapped_column(Text, default="", server_default="")
    usage_note_vi: Mapped[str] = mapped_column(Text, default="", server_default="")
    audio_path: Mapped[str | None] = mapped_column(String(255))


class WordCharacter(Base):
    __tablename__ = "word_characters"
    __table_args__ = (CheckConstraint("position >= 0", name="character_position_valid"),)

    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(primary_key=True)


class GrammarPattern(Base):
    __tablename__ = "grammar_patterns"
    __table_args__ = (CheckConstraint("hsk_level between 1 and 5", name="pattern_level_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern_formula: Mapped[str] = mapped_column(String(250), unique=True)
    title_vi: Mapped[str] = mapped_column(String(250))
    explanation_vi: Mapped[str] = mapped_column(Text)
    hsk_level: Mapped[int | None]
    structure_notes_vi: Mapped[str] = mapped_column(Text, default="", server_default="")


class Sentence(Base):
    __tablename__ = "sentences"

    id: Mapped[int] = mapped_column(primary_key=True)
    hanzi: Mapped[str] = mapped_column(String(600), unique=True)
    pinyin: Mapped[str] = mapped_column(Text)
    meaning_vi: Mapped[str] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(String(255))
    grammar_pattern_id: Mapped[int | None] = mapped_column(ForeignKey("grammar_patterns.id", ondelete="SET NULL"), index=True)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SentenceWord(Base):
    __tablename__ = "sentence_words"

    sentence_id: Mapped[int] = mapped_column(ForeignKey("sentences.id", ondelete="CASCADE"), primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), primary_key=True, index=True)


class SourceWord(Base):
    __tablename__ = "source_words"

    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), primary_key=True, index=True)


class SourcePattern(Base):
    __tablename__ = "source_patterns"

    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    pattern_id: Mapped[int] = mapped_column(ForeignKey("grammar_patterns.id", ondelete="CASCADE"), primary_key=True, index=True)


class SourceSentence(Base):
    __tablename__ = "source_sentences"

    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    sentence_id: Mapped[int] = mapped_column(ForeignKey("sentences.id", ondelete="CASCADE"), primary_key=True, index=True)


class ConfusablePair(Base):
    __tablename__ = "confusable_pairs"
    __table_args__ = (
        UniqueConstraint("word_a_id", "word_b_id"),
        CheckConstraint("word_a_id <> word_b_id", name="confusable_distinct_words"),
        CheckConstraint("hsk_level between 1 and 5", name="confusable_level_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    word_a_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"))
    word_b_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), index=True)
    diff_explanation_vi: Mapped[str] = mapped_column(Text)
    cloze_a_hanzi: Mapped[str] = mapped_column(Text)
    cloze_a_answer: Mapped[str] = mapped_column(String(100))
    cloze_b_hanzi: Mapped[str] = mapped_column(Text)
    cloze_b_answer: Mapped[str] = mapped_column(String(100))
    hsk_level: Mapped[int]


class UserCard(Base):
    __tablename__ = "user_cards"
    __table_args__ = (
        UniqueConstraint("item_type", "item_id"),
        CheckConstraint("item_type in ('word','pattern','confusable')", name="card_type_valid"),
        CheckConstraint("status in ('new','learning','review','mastered','ignored')", name="card_status_valid"),
        Index("ix_user_cards_status_due", "status", "due"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_type: Mapped[str] = mapped_column(String(16))
    item_id: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default="new", server_default="new")
    fsrs_state_json: Mapped[dict | None] = mapped_column(JSON)
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, server_default=func.now())
    wrong_count: Mapped[int] = mapped_column(default=0, server_default="0")
    reps: Mapped[int] = mapped_column(default=0, server_default="0")
    lapses: Mapped[int] = mapped_column(default=0, server_default="0")
    is_leech: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class ReviewLog(Base):
    __tablename__ = "review_logs"
    __table_args__ = (
        CheckConstraint("rating between 1 and 4", name="review_rating_valid"),
        CheckConstraint("response_ms >= 0", name="review_time_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("user_cards.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int]
    drill_mode: Mapped[str] = mapped_column(String(24))
    response_ms: Mapped[int]
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    review_token: Mapped[str | None] = mapped_column(String(64), unique=True)


class StoryAttempt(Base):
    __tablename__ = "story_attempts"
    __table_args__ = (CheckConstraint("score between 0 and 100", name="story_score_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    target_words: Mapped[list[str]] = mapped_column(JSON)
    text: Mapped[str] = mapped_column(Text)
    score: Mapped[int]
    feedback: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
