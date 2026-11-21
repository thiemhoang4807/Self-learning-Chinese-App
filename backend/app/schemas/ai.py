from datetime import datetime
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator

from app.schemas.ingestion import BoundedText, DocumentModel, ExtractedSentence, WordText, is_hanzi

Score = Annotated[int, Field(ge=0, le=100)]


class ReverseTranslationRequest(DocumentModel):
    sentence_id: Annotated[int, Field(gt=0)]
    answer: BoundedText


class TranslationCorrection(DocumentModel):
    original: str
    correction: str
    explanation_vi: BoundedText


class TranslationGrade(DocumentModel):
    score: Score
    feedback_vi: BoundedText
    corrections: list[TranslationCorrection]
    corrected_hanzi: BoundedText


class ExamplesRequest(DocumentModel):
    item_type: Literal["word", "pattern"]
    item_id: Annotated[int, Field(gt=0)]


class GeneratedExamples(DocumentModel):
    sentences: list[ExtractedSentence]


class SentenceResult(DocumentModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    hanzi: str
    pinyin: str
    meaning_vi: str
    grammar_pattern_id: int | None
    is_ai_generated: bool


class ExamplesResult(DocumentModel):
    sentences: list[SentenceResult]


class ConfusableRequest(DocumentModel):
    word_a_id: Annotated[int, Field(gt=0)]
    word_b_id: Annotated[int, Field(gt=0)]


class GeneratedConfusable(DocumentModel):
    diff_explanation_vi: BoundedText
    cloze_a_hanzi: BoundedText
    cloze_b_hanzi: BoundedText

    @field_validator("cloze_a_hanzi", "cloze_b_hanzi")
    @classmethod
    def check_blank(cls, value: str) -> str:
        if value.count("___") != 1 or not any(is_hanzi(char) for char in value):
            raise ValueError("Câu điền từ cần có đúng một chỗ trống ___.")
        return value


class ConfusableResult(DocumentModel):
    id: int
    word_a_id: int
    word_b_id: int
    word_a: str
    word_b: str
    diff_explanation_vi: str
    cloze_a_hanzi: str
    cloze_a_answer: str
    cloze_b_hanzi: str
    cloze_b_answer: str
    hsk_level: int | None


class StoryWords(DocumentModel):
    words: list[str]


class StoryRequest(DocumentModel):
    target_words: list[WordText] = Field(min_length=5, max_length=5)
    text: BoundedText

    @field_validator("target_words")
    @classmethod
    def check_distinct_words(cls, words: list[str]) -> list[str]:
        if len(set(words)) != 5:
            raise ValueError("Bài viết cần năm từ mục tiêu khác nhau.")
        return words


class StoryWordFeedback(DocumentModel):
    word: WordText
    correct: bool
    feedback_vi: BoundedText


class StoryFeedback(DocumentModel):
    usage: list[StoryWordFeedback]
    grammar_vi: BoundedText
    naturalness_vi: BoundedText
    rewrite_hanzi: BoundedText


class StoryGrade(StoryFeedback):
    score: Score


class StoryResult(DocumentModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    target_words: list[str]
    text: str
    score: Score
    feedback: StoryFeedback
    created_at: datetime
