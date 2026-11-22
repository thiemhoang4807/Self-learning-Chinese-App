from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Annotated, Hashable, Literal, TypeVar
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from app.schemas.ingestion import HskLevel, SourceType
from app.schemas.study import ItemType

RecordId = Annotated[int, Field(ge=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Theme = Literal["light", "dark"]
T = TypeVar("T")


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


UtcDateTime = Annotated[datetime, AfterValidator(as_utc)]


class SnapshotRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", allow_inf_nan=False)


class Preferences(SnapshotRecord):
    theme: Theme
    pinyin: bool


class PreferencePatch(SnapshotRecord):
    theme: Theme | None = None
    pinyin: bool | None = None

    @model_validator(mode="after")
    def has_updates(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Cần ít nhất một cài đặt hợp lệ.")
        return self


class WordRecord(SnapshotRecord):
    id: RecordId
    simplified: str = Field(min_length=1, max_length=100)
    traditional: str | None = Field(max_length=100)
    pinyin: str = Field(max_length=200)
    han_viet: str = Field(max_length=200)
    meaning_vi: str
    pos: str = Field(max_length=100)
    hsk_level: HskLevel | None
    mnemonic_vi: str
    usage_note_vi: str
    audio_path: str | None = Field(max_length=255)


class CharacterRecord(SnapshotRecord):
    id: RecordId
    char: str = Field(min_length=1, max_length=1)
    pinyin: str = Field(max_length=60)
    han_viet: str = Field(max_length=100)
    radical: str = Field(max_length=60)
    components_json: list[str]
    mnemonic_vi: str
    hsk_level: HskLevel | None


class PatternRecord(SnapshotRecord):
    id: RecordId
    pattern_formula: str = Field(min_length=1, max_length=250)
    title_vi: str = Field(max_length=250)
    explanation_vi: str
    hsk_level: HskLevel | None
    structure_notes_vi: str


class SentenceRecord(SnapshotRecord):
    id: RecordId
    hanzi: str = Field(min_length=1, max_length=600)
    pinyin: str
    meaning_vi: str
    audio_path: str | None = Field(max_length=255)
    grammar_pattern_id: RecordId | None
    is_ai_generated: bool
    created_at: UtcDateTime


class SourceRecord(SnapshotRecord):
    id: RecordId
    backup_uid: UUID
    title: str = Field(min_length=1, max_length=250)
    source_type: SourceType
    summary_note: str
    created_at: UtcDateTime


class ConfusableRecord(SnapshotRecord):
    id: RecordId
    word_a_id: RecordId
    word_b_id: RecordId
    diff_explanation_vi: str
    cloze_a_hanzi: str
    cloze_a_answer: str = Field(max_length=100)
    cloze_b_hanzi: str
    cloze_b_answer: str = Field(max_length=100)
    hsk_level: HskLevel


class WordCharacterRecord(SnapshotRecord):
    word_id: RecordId
    character_id: RecordId
    position: NonNegativeInt


class SentenceWordRecord(SnapshotRecord):
    sentence_id: RecordId
    word_id: RecordId


class SourceWordRecord(SnapshotRecord):
    source_id: RecordId
    word_id: RecordId


class SourcePatternRecord(SnapshotRecord):
    source_id: RecordId
    pattern_id: RecordId


class SourceSentenceRecord(SnapshotRecord):
    source_id: RecordId
    sentence_id: RecordId


class FsrsState(SnapshotRecord):
    card_id: RecordId
    state: Literal[1, 2, 3]
    step: NonNegativeInt | None
    stability: Annotated[float, Field(gt=0)] | None
    difficulty: Annotated[float, Field(ge=1, le=10)] | None
    due: UtcDateTime
    last_review: UtcDateTime | None

    @field_validator("due", "last_review", mode="before")
    @classmethod
    def validate_card_timestamp(cls, value):
        if value is not None and (
            not isinstance(value, str) or datetime.fromisoformat(value).utcoffset() is None
        ):
            raise ValueError("Ngày giờ của thẻ FSRS phải gồm múi giờ.")
        return value


class CardRecord(SnapshotRecord):
    id: RecordId
    item_type: ItemType
    item_id: RecordId
    status: Literal["new", "learning", "review", "mastered", "ignored"]
    fsrs_state_json: dict[str, JsonValue] | None
    due: UtcDateTime
    wrong_count: NonNegativeInt
    reps: NonNegativeInt
    lapses: NonNegativeInt
    is_leech: bool

    @field_validator("fsrs_state_json")
    @classmethod
    def validate_fsrs(cls, value):
        if value is not None:
            FsrsState.model_validate(value)
        return value


class ReviewLogRecord(SnapshotRecord):
    id: RecordId
    backup_uid: UUID
    card_id: RecordId
    rating: int = Field(ge=1, le=4)
    drill_mode: str = Field(min_length=1, max_length=24)
    response_ms: NonNegativeInt
    reviewed_at: UtcDateTime
    review_token: str | None = Field(max_length=64)


class StoryRecord(SnapshotRecord):
    id: RecordId
    backup_uid: UUID
    target_words: list[str]
    text: str
    score: int = Field(ge=0, le=100)
    feedback: dict[str, JsonValue]
    created_at: UtcDateTime


def distinct(records: Iterable[T], key: Callable[[T], Hashable]) -> set:
    keys = set()
    for row in records:
        value = key(row)
        if value in keys:
            raise ValueError("Bản sao lưu có mục trùng lặp.")
        keys.add(value)
    return keys


class BackupSnapshot(SnapshotRecord):
    schema_version: Literal[1]
    exported_at: UtcDateTime
    words: list[WordRecord]
    characters: list[CharacterRecord]
    grammar_patterns: list[PatternRecord]
    sentences: list[SentenceRecord]
    confusable_pairs: list[ConfusableRecord]
    word_characters: list[WordCharacterRecord]
    sentence_words: list[SentenceWordRecord]
    sources: list[SourceRecord]
    source_words: list[SourceWordRecord]
    source_patterns: list[SourcePatternRecord]
    source_sentences: list[SourceSentenceRecord]
    user_cards: list[CardRecord]
    review_logs: list[ReviewLogRecord]
    story_attempts: list[StoryRecord]
    preferences: Preferences

    @model_validator(mode="after")
    def validate_graph(self):
        words = distinct(self.words, lambda word: word.id)
        characters = distinct(self.characters, lambda character: character.id)
        patterns = distinct(self.grammar_patterns, lambda pattern: pattern.id)
        sentences = distinct(self.sentences, lambda sentence: sentence.id)
        confusables = distinct(self.confusable_pairs, lambda pair: pair.id)
        sources = distinct(self.sources, lambda source: source.id)
        cards = distinct(self.user_cards, lambda card: card.id)
        distinct(self.review_logs, lambda log: log.id)
        distinct(self.story_attempts, lambda story: story.id)

        distinct(self.words, lambda word: word.simplified)
        distinct(self.characters, lambda character: character.char)
        distinct(self.grammar_patterns, lambda pattern: pattern.pattern_formula)
        distinct(self.sentences, lambda sentence: sentence.hanzi)
        distinct(self.confusable_pairs, lambda pair: (pair.word_a_id, pair.word_b_id))
        distinct(self.user_cards, lambda card: (card.item_type, card.item_id))
        distinct(self.sources, lambda source: source.backup_uid)
        distinct(self.review_logs, lambda log: log.backup_uid)
        distinct((log for log in self.review_logs if log.review_token is not None), lambda log: log.review_token)
        distinct(self.story_attempts, lambda story: story.backup_uid)
        distinct(self.word_characters, lambda link: (link.word_id, link.position))
        distinct(self.sentence_words, lambda link: (link.sentence_id, link.word_id))
        distinct(self.source_words, lambda link: (link.source_id, link.word_id))
        distinct(self.source_patterns, lambda link: (link.source_id, link.pattern_id))
        distinct(self.source_sentences, lambda link: (link.source_id, link.sentence_id))

        word_text = {word.id: word.simplified for word in self.words}
        character_text = {character.id: character.char for character in self.characters}
        catalog = {"word": words, "pattern": patterns, "confusable": confusables}
        checks = (
            (row.grammar_pattern_id is None or row.grammar_pattern_id in patterns for row in self.sentences),
            (row.word_a_id != row.word_b_id and row.word_a_id in words and row.word_b_id in words
             for row in self.confusable_pairs),
            (row.word_id in words and row.character_id in characters
             and row.position < len(word_text[row.word_id])
             and word_text[row.word_id][row.position] == character_text[row.character_id]
             for row in self.word_characters),
            (row.sentence_id in sentences and row.word_id in words for row in self.sentence_words),
            (row.source_id in sources and row.word_id in words for row in self.source_words),
            (row.source_id in sources and row.pattern_id in patterns for row in self.source_patterns),
            (row.source_id in sources and row.sentence_id in sentences for row in self.source_sentences),
            (row.item_id in catalog[row.item_type] for row in self.user_cards),
            (row.card_id in cards for row in self.review_logs),
        )
        if not all(all(check) for check in checks):
            raise ValueError("Bản sao lưu có liên kết đến mục bị thiếu hoặc không hợp lệ.")
        return self


class RestoreSummary(SnapshotRecord):
    words_created: int = 0
    words_updated: int = 0
    sources_created: int = 0
    sources_updated: int = 0
    cards_created: int = 0
    cards_updated: int = 0
    reviews_added: int = 0
    stories_added: int = 0
    preferences: Preferences
    message: str = ""
