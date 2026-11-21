from datetime import datetime
from typing import Annotated, Literal
from unicodedata import normalize

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

SourceType = Literal["image", "pdf", "pptx", "docx", "xlsx", "text", "paste"]
HskLevel = Annotated[int, Field(ge=1, le=5)]
WordText = Annotated[str, StringConstraints(min_length=1, max_length=100)]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=250)]
BoundedText = Annotated[str, StringConstraints(min_length=1, max_length=4000)]


def is_hanzi(value: str) -> bool:
    code = ord(value)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2FA1F
        or 0x30000 <= code <= 0x323AF
        or value == "〇"
    )


class DocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ExtractedCharacter(DocumentModel):
    char: Annotated[str, StringConstraints(min_length=1, max_length=1)]
    pinyin: Annotated[str, StringConstraints(max_length=50)] = ""
    han_viet: Annotated[str, StringConstraints(max_length=80)] = ""
    radical: Annotated[str, StringConstraints(max_length=30)] = ""
    components: list[str] = Field(default_factory=list, max_length=20)
    mnemonic_vi: str = ""

    @field_validator("char")
    @classmethod
    def check_character(cls, value: str) -> str:
        if not is_hanzi(value):
            raise ValueError("Vui lòng nhập một chữ Hán.")
        return value


class ExtractedWord(DocumentModel):
    simplified: WordText
    traditional: WordText | None = None
    pinyin: Annotated[str, StringConstraints(max_length=200)] = ""
    han_viet: Annotated[str, StringConstraints(max_length=200)] = ""
    meaning_vi: BoundedText
    pos: Annotated[str, StringConstraints(max_length=80)] = ""
    hsk_level: HskLevel | None = None
    mnemonic_vi: str = ""
    usage_note_vi: str = ""
    characters: list[ExtractedCharacter] = Field(default_factory=list, max_length=100)

    @field_validator("traditional", mode="before")
    @classmethod
    def normalize_optional_traditional(cls, value: str | None) -> str | None:
        return value if not isinstance(value, str) or value.strip() else None

    @field_validator("simplified")
    @classmethod
    def check_word(cls, value: str) -> str:
        if not any(is_hanzi(char) for char in value):
            raise ValueError("Từ vựng cần có chữ Hán.")
        return normalize("NFC", "".join(value.split()))


class ExtractedPattern(DocumentModel):
    pattern_formula: ShortText
    title_vi: ShortText
    explanation_vi: BoundedText
    hsk_level: HskLevel | None = None
    structure_notes_vi: str = ""


class ExtractedSentence(DocumentModel):
    hanzi: Annotated[str, StringConstraints(min_length=1, max_length=600)]
    pinyin: str = ""
    meaning_vi: BoundedText
    pattern_formula: ShortText | None = None

    @field_validator("pattern_formula", mode="before")
    @classmethod
    def normalize_optional_formula(cls, value: str | None) -> str | None:
        return value if not isinstance(value, str) or value.strip() else None

    @field_validator("hanzi")
    @classmethod
    def check_sentence(cls, value: str) -> str:
        if not any(is_hanzi(char) for char in value):
            raise ValueError("Câu ví dụ cần có chữ Hán.")
        return value


class ExtractedMaterial(DocumentModel):
    summary_note: str
    words: list[ExtractedWord]
    grammar_patterns: list[ExtractedPattern]
    sentences: list[ExtractedSentence]


class StagedWord(ExtractedWord):
    existing: bool = False


class StagedPattern(ExtractedPattern):
    existing: bool = False


class StagedSentence(ExtractedSentence):
    existing: bool = False


class StagedMaterial(DocumentModel):
    title: ShortText
    source_type: SourceType
    summary_note: str = ""
    words: list[StagedWord] = Field(max_length=1200)
    grammar_patterns: list[StagedPattern] = Field(max_length=400)
    sentences: list[StagedSentence] = Field(max_length=1200)
    notice_vi: str | None = None


class SourceSummary(DocumentModel):
    id: int
    title: str
    source_type: SourceType
    summary_note: str
    created_at: datetime
    word_count: int
    pattern_count: int
    sentence_count: int
