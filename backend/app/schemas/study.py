from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ItemType = Literal["word", "pattern", "confusable"]
DrillMode = Literal["flashcard", "listening", "cloze", "reorder", "reverse", "confusable"]
SessionMode = Literal["mixed", "flashcard", "listening", "cloze", "reorder", "reverse", "confusable"]


class CharacterView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    char: str
    pinyin: str
    han_viet: str
    radical: str
    components_json: list[str]
    mnemonic_vi: str
    hsk_level: int | None


class WordView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    simplified: str
    traditional: str | None
    pinyin: str
    han_viet: str
    meaning_vi: str
    pos: str
    hsk_level: int | None
    mnemonic_vi: str
    usage_note_vi: str
    audio_path: str | None
    status: str | None = None


class SentenceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hanzi: str
    pinyin: str
    meaning_vi: str
    audio_path: str | None
    grammar_pattern_id: int | None
    is_ai_generated: bool


class DrillCard(BaseModel):
    id: int = 0
    item_id: int
    item_type: ItemType
    status: str = "new"
    mode: DrillMode
    hanzi: str
    pinyin: str = ""
    han_viet: str = ""
    meaning_vi: str
    mnemonic_vi: str = ""
    usage_note_vi: str = ""
    grammar_hint: str = ""
    audio_text: str = ""
    characters: list[CharacterView] = Field(default_factory=list)
    sentences: list[SentenceView] = Field(default_factory=list)
    sentence_id: int | None = None
    prompt: str = ""
    answer: str = ""
    choices: list[str] = Field(default_factory=list)
    tiles: list[str] = Field(default_factory=list)


class StudySession(BaseModel):
    cards: list[DrillCard]


class QueueRequest(BaseModel):
    item_type: ItemType
    item_ids: list[int] = Field(min_length=1, max_length=500)


class QueueResult(BaseModel):
    queued: int


class RatingRequest(BaseModel):
    rating: int = Field(ge=1, le=4)
    drill_mode: DrillMode | Literal["passive"]
    response_ms: int = Field(ge=0, le=86_400_000)
    review_token: str | None = Field(default=None, min_length=1, max_length=64)


class RatingResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    due: datetime
    wrong_count: int
    is_leech: bool

    @field_validator("due")
    @classmethod
    def utc_due(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class WordPage(BaseModel):
    items: list[WordView]
    total: int


class CharacterTree(BaseModel):
    character: CharacterView
    words: list[WordView]


class ReaderText(BaseModel):
    text: str = Field(min_length=1, max_length=12000)


class ReaderLookup(BaseModel):
    word: str = Field(min_length=1, max_length=100)


class ReaderToken(BaseModel):
    text: str
    word: WordView | None


class ReaderResult(BaseModel):
    tokens: list[ReaderToken]


class CoverageLevel(BaseModel):
    level: int
    mastered: int
    ingested: int
    total: int
    available: int


class Pace(BaseModel):
    words_per_day: float
    remaining: int
    projected_date: date | None


class LeechView(BaseModel):
    card_id: int
    word_id: int
    simplified: str
    pinyin: str
    meaning_vi: str
    wrong_count: int


class DashboardView(BaseModel):
    levels: list[CoverageLevel]
    pace: Pace
    leeches: list[LeechView]
