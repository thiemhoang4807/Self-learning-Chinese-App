from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, with_config
from typing_extensions import TypedDict

from app.schemas.ingestion import BoundedText, HskLevel, ShortText
from app.schemas.study import SentenceView

Pronunciation = Annotated[str, StringConstraints(max_length=200)]
Notes = Annotated[str, StringConstraints(max_length=4000)]
PATCH_CONFIG = ConfigDict(extra="forbid", str_strip_whitespace=True)


@with_config(PATCH_CONFIG)
class WordPatch(TypedDict, total=False):
    pinyin: Pronunciation
    han_viet: Pronunciation
    meaning_vi: Notes
    pos: Annotated[str, StringConstraints(max_length=100)]
    hsk_level: HskLevel | None
    mnemonic_vi: Notes
    usage_note_vi: Notes
    status: Literal["ignored", "active"]


@with_config(PATCH_CONFIG)
class PatternPatch(TypedDict, total=False):
    title_vi: ShortText
    explanation_vi: BoundedText
    hsk_level: HskLevel | None
    structure_notes_vi: Notes


@with_config(PATCH_CONFIG)
class SentencePatch(TypedDict, total=False):
    pinyin: Notes
    meaning_vi: BoundedText


@with_config(PATCH_CONFIG)
class SourcePatch(TypedDict, total=False):
    title: ShortText
    summary_note: Notes


class PatternView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pattern_formula: str
    title_vi: str
    explanation_vi: str
    hsk_level: int | None
    structure_notes_vi: str


class PatternPage(BaseModel):
    items: list[PatternView]
    total: int


class SentencePage(BaseModel):
    items: list[SentenceView]
    total: int
