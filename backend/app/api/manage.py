from collections.abc import Mapping
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.db import Base, get_db, lock_catalog
from app.models import GrammarPattern, Sentence, Source, SourcePattern, SourceSentence, UserCard, Word
from app.schemas.ingestion import SourceSummary
from app.schemas.manage import PatternPage, PatternPatch, PatternView, SentencePage, SentencePatch, SourcePatch, WordPatch
from app.schemas.study import SentenceView, WordView
from app.services.ingestion import source_summaries
from app.services.library import with_word_status, word_view
from app.services.study import enqueue_many, restored_card_status

router = APIRouter(tags=["manage"])
Database = Annotated[Session, Depends(get_db)]
ItemId = Annotated[int, Path(gt=0)]
SourceFilter = Annotated[int | None, Query(gt=0)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]
SearchText = Annotated[str, Query(max_length=200)]
Entity = TypeVar("Entity", bound=Base)


def _update(item: Base, changes: Mapping[str, object]) -> None:
    for name, value in changes.items():
        setattr(item, name, value)


def _page(db: Session, statement: Select[tuple[Entity]], limit: int, offset: int):
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    return db.scalars(statement.limit(limit).offset(offset)).all(), total


def _source(db: Session, source_id: int) -> SourceSummary:
    summaries = source_summaries(db, source_id=source_id)
    if not summaries:
        raise HTTPException(404, "Không tìm thấy tài liệu này.")
    return summaries[0]


@router.get("/words/{word_id}", response_model=WordView)
def get_word(word_id: ItemId, db: Database) -> WordView:
    found = db.execute(with_word_status().where(Word.id == word_id)).one_or_none()
    if found is None:
        raise HTTPException(404, "Không tìm thấy từ này.")
    return word_view(*found)


@router.patch("/words/{word_id}", response_model=WordView)
def update_word(word_id: ItemId, changes: WordPatch, db: Database) -> WordView:
    lock_catalog(db)
    word = db.get(Word, word_id)
    if word is None:
        raise HTTPException(404, "Không tìm thấy từ này.")

    status = changes.get("status")
    if status is not None:
        enqueue_many(db, "word", [word.id])
    card_query = select(UserCard).where(UserCard.item_type == "word", UserCard.item_id == word.id)
    card = db.scalar(card_query.with_for_update() if status is not None else card_query)
    if card is not None and status == "ignored":
        card.status = "ignored"
    elif card is not None and status == "active" and card.status == "ignored":
        card.status = restored_card_status(card)

    _update(word, {name: value for name, value in changes.items() if name != "status"})
    result = word_view(word, card.status if card is not None else None)
    db.commit()
    return result


@router.get("/patterns", response_model=PatternPage)
def list_patterns(
    db: Database, q: SearchText = "", source_id: SourceFilter = None, limit: Limit = 24, offset: Offset = 0,
) -> PatternPage:
    query = select(GrammarPattern).order_by(GrammarPattern.hsk_level.nulls_last(), GrammarPattern.id)
    if q := q.strip():
        query = query.where(or_(
            GrammarPattern.pattern_formula.icontains(q, autoescape=True),
            GrammarPattern.title_vi.icontains(q, autoescape=True),
            GrammarPattern.explanation_vi.icontains(q, autoescape=True),
        ))
    if source_id is not None:
        query = query.where(select(SourcePattern).where(
            SourcePattern.pattern_id == GrammarPattern.id, SourcePattern.source_id == source_id,
        ).exists())
    rows, total = _page(db, query, limit, offset)
    return PatternPage(items=[PatternView.model_validate(row) for row in rows], total=total)


@router.get("/patterns/{pattern_id}", response_model=PatternView)
def get_pattern(pattern_id: ItemId, db: Database) -> PatternView:
    pattern = db.get(GrammarPattern, pattern_id)
    if pattern is None:
        raise HTTPException(404, "Không tìm thấy mẫu ngữ pháp này.")
    return PatternView.model_validate(pattern)


@router.patch("/patterns/{pattern_id}", response_model=PatternView)
def update_pattern(pattern_id: ItemId, changes: PatternPatch, db: Database) -> PatternView:
    lock_catalog(db)
    pattern = db.get(GrammarPattern, pattern_id)
    if pattern is None:
        raise HTTPException(404, "Không tìm thấy mẫu ngữ pháp này.")
    _update(pattern, changes)
    result = PatternView.model_validate(pattern)
    db.commit()
    return result


@router.get("/sentences", response_model=SentencePage)
def list_sentences(
    db: Database, q: SearchText = "", source_id: SourceFilter = None, limit: Limit = 24, offset: Offset = 0,
) -> SentencePage:
    query = select(Sentence).order_by(Sentence.id.desc())
    if q := q.strip():
        query = query.where(or_(
            Sentence.hanzi.icontains(q, autoescape=True),
            Sentence.pinyin.icontains(q, autoescape=True),
            Sentence.meaning_vi.icontains(q, autoescape=True),
        ))
    if source_id is not None:
        query = query.where(select(SourceSentence).where(
            SourceSentence.sentence_id == Sentence.id, SourceSentence.source_id == source_id,
        ).exists())
    rows, total = _page(db, query, limit, offset)
    return SentencePage(items=[SentenceView.model_validate(row) for row in rows], total=total)


@router.get("/sentences/{sentence_id}", response_model=SentenceView)
def get_sentence(sentence_id: ItemId, db: Database) -> SentenceView:
    sentence = db.get(Sentence, sentence_id)
    if sentence is None:
        raise HTTPException(404, "Không tìm thấy câu ví dụ này.")
    return SentenceView.model_validate(sentence)


@router.patch("/sentences/{sentence_id}", response_model=SentenceView)
def update_sentence(sentence_id: ItemId, changes: SentencePatch, db: Database) -> SentenceView:
    lock_catalog(db)
    sentence = db.get(Sentence, sentence_id)
    if sentence is None:
        raise HTTPException(404, "Không tìm thấy câu ví dụ này.")
    _update(sentence, changes)
    result = SentenceView.model_validate(sentence)
    db.commit()
    return result


@router.get("/sources/{source_id}", response_model=SourceSummary)
def get_source(source_id: ItemId, db: Database) -> SourceSummary:
    return _source(db, source_id)


@router.patch("/sources/{source_id}", response_model=SourceSummary)
def update_source(source_id: ItemId, changes: SourcePatch, db: Database) -> SourceSummary:
    lock_catalog(db)
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "Không tìm thấy tài liệu này.")
    _update(source, changes)
    result = _source(db, source_id)
    db.commit()
    return result


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: ItemId, db: Database) -> Response:
    lock_catalog(db)
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "Không tìm thấy tài liệu này.")
    db.delete(source)
    db.commit()
    return Response(status_code=204)
