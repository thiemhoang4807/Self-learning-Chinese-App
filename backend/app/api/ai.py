import random
import re
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.orm import Session, aliased

from app.db import get_db
from app.models import ConfusablePair, GrammarPattern, ReviewLog, Sentence, SentenceWord, StoryAttempt, UserCard, Word
from app.schemas.ai import (
    ConfusableRequest,
    ConfusableResult,
    ExamplesRequest,
    ExamplesResult,
    ReverseTranslationRequest,
    SentenceResult,
    StoryRequest,
    StoryResult,
    StoryWords,
    TranslationGrade,
)
from app.schemas.ingestion import is_hanzi
from app.services import ai, ingestion
from app.services.study import enqueue

router = APIRouter(prefix="/ai", tags=["ai"])
Database = Annotated[Session, Depends(get_db)]
GRAMMAR_PLACEHOLDERS = {
    "主语", "宾语", "动词", "形容词", "名词", "谓语", "处所", "时间", "数量", "程度",
    "数词", "地点", "方位词", "副词", "代词", "补语", "状态", "结果补语", "趋向补语",
    "助词", "成分", "句子", "程度补语", "比较对象",
}


@router.post("/reverse-translation", response_model=TranslationGrade)
def reverse_translation(payload: ReverseTranslationRequest, db: Database) -> TranslationGrade:
    sentence = db.get(Sentence, payload.sentence_id)
    if sentence is None:
        raise HTTPException(status_code=404, detail="Chưa tìm thấy câu cần dịch.")
    pattern = db.get(GrammarPattern, sentence.grammar_pattern_id) if sentence.grammar_pattern_id else None
    return ai.grade_translation(
        sentence.meaning_vi, sentence.hanzi, payload.answer, pattern.pattern_formula if pattern else None,
    )


def _grammar_markers(formula: str) -> list[str]:
    # A formula's Hanzi runs are literal markers unless they name a grammatical slot.
    words = "".join(char if is_hanzi(char) else " " for char in formula).split()
    return [word for word in words if word not in GRAMMAR_PLACEHOLDERS]


def _word_path(hanzi: str, allowed: set[str], markers: list[str]) -> list[str] | None:
    max_length = max(map(len, allowed), default=0)
    # Keep a segmentation for each number of required markers matched in order.
    paths: list[dict[int, list[str]]] = [{} for _ in range(len(hanzi) + 1)]
    paths[0][0] = []
    for index, char in enumerate(hanzi):
        for matched, path in paths[index].items():
            if not is_hanzi(char) and (char.isspace() or not char.isalnum()):
                paths[index + 1].setdefault(matched, path)
            for length in range(min(max_length, len(hanzi) - index), 0, -1):
                word = hanzi[index:index + length]
                if word not in allowed:
                    continue
                next_marker = matched + 1 if matched < len(markers) and markers[matched] == word else matched
                paths[index + length].setdefault(next_marker, [*path, word])
    return paths[-1].get(len(markers))


def _canonical_sentence(sentence: str) -> str:
    return "".join(char for char in sentence if is_hanzi(char) or char.isalnum())


@router.post("/examples", response_model=ExamplesResult)
def examples(payload: ExamplesRequest, db: Database) -> ExamplesResult:
    known = list(db.scalars(
        select(Word.simplified)
        .join(UserCard, and_(UserCard.item_id == Word.id, UserCard.item_type == "word"))
        .where(UserCard.status.in_(["learning", "review", "mastered"]))
        .order_by(Word.hsk_level.asc().nulls_last(), Word.id.asc())
    ))
    marks: list[str] = []
    grammar_id = None
    previous_examples = select(Sentence.hanzi).order_by(Sentence.id.desc()).limit(35)
    if payload.item_type == "word":
        word = db.get(Word, payload.item_id)
        if word is None:
            raise HTTPException(status_code=404, detail="Chưa tìm thấy từ cần tạo câu.")
        target = word.simplified
        marks = [target]
        meaning = word.meaning_vi
        previous_examples = previous_examples.join(SentenceWord).where(SentenceWord.word_id == word.id)
    else:
        pattern = db.get(GrammarPattern, payload.item_id)
        if pattern is None:
            raise HTTPException(status_code=404, detail="Chưa tìm thấy mẫu ngữ pháp cần tạo câu.")
        target = pattern.pattern_formula
        meaning = pattern.explanation_vi
        grammar_id = pattern.id
        marks = _grammar_markers(target)
        previous_examples = previous_examples.where(Sentence.grammar_pattern_id == pattern.id)

    if not set(known).difference({target}):
        raise HTTPException(
            status_code=422, detail="Hãy ôn thêm một vài từ để có đủ từ vựng cho câu ví dụ i+1.",
        )
    previous = list(db.scalars(previous_examples))
    allowed = set(known)
    allowed.update(marks)
    seen = {_canonical_sentence(sentence) for sentence in previous}

    chosen = {}
    for _ in range(2):
        generated = ai.generate_examples(payload.item_type, target, meaning, known, [*previous, *chosen])
        for example in generated.sentences:
            key = _canonical_sentence(example.hanzi)
            if key in seen:
                continue
            tokens = _word_path(example.hanzi, allowed, marks)
            if not tokens:
                continue
            if db.scalar(select(Sentence.id).where(Sentence.hanzi == example.hanzi)) is not None:
                continue
            chosen[example.hanzi] = (example, tokens)
            seen.add(key)
            if len(chosen) == 3:
                break
        if len(chosen) >= 2:
            break

    if len(chosen) < 2:
        raise HTTPException(
            status_code=422,
            detail="Chưa tạo đủ câu mới chỉ dùng vốn từ đang học. Hãy ôn thêm vài từ hoặc thử lại.",
        )
    sentences = [
        ingestion.upsert_sentence(db, example, grammar_id, generated=True, related_words=tokens)
        for example, tokens in chosen.values()
    ]
    db.commit()
    return ExamplesResult(sentences=[SentenceResult.model_validate(sentence) for sentence in sentences])


def _pair_result(pair: ConfusablePair, word_a: str, word_b: str) -> ConfusableResult:
    return ConfusableResult(
        id=pair.id,
        word_a_id=pair.word_a_id,
        word_b_id=pair.word_b_id,
        word_a=word_a,
        word_b=word_b,
        diff_explanation_vi=pair.diff_explanation_vi,
        cloze_a_hanzi=re.sub(r"_{2,}|＿{2,}", "___", pair.cloze_a_hanzi),
        cloze_a_answer=pair.cloze_a_answer,
        cloze_b_hanzi=re.sub(r"_{2,}|＿{2,}", "___", pair.cloze_b_hanzi),
        cloze_b_answer=pair.cloze_b_answer,
        hsk_level=pair.hsk_level,
    )


@router.get("/confusables", response_model=list[ConfusableResult])
def confusables(db: Database) -> list[ConfusableResult]:
    word_a = aliased(Word)
    word_b = aliased(Word)
    rows = db.execute(
        select(ConfusablePair, word_a.simplified, word_b.simplified)
        .join(word_a, word_a.id == ConfusablePair.word_a_id)
        .join(word_b, word_b.id == ConfusablePair.word_b_id)
        .order_by(ConfusablePair.hsk_level, ConfusablePair.id)
    )
    return [_pair_result(pair, name_a, name_b) for pair, name_a, name_b in rows]


@router.post("/confusables", response_model=ConfusableResult)
def create_confusable(payload: ConfusableRequest, db: Database) -> ConfusableResult:
    if payload.word_a_id == payload.word_b_id:
        raise HTTPException(status_code=422, detail="Hãy chọn hai từ khác nhau để so sánh.")
    first = db.get(Word, payload.word_a_id)
    second = db.get(Word, payload.word_b_id)
    if first is None or second is None:
        raise HTTPException(status_code=404, detail="Chưa tìm thấy một trong hai từ đã chọn.")
    words = {first.id: first, second.id: second}
    existing = db.scalars(select(ConfusablePair).where(
        tuple_(ConfusablePair.word_a_id, ConfusablePair.word_b_id).in_([(first.id, second.id), (second.id, first.id)])
    ).order_by(ConfusablePair.id)).first()
    if existing:
        return _pair_result(existing, words[existing.word_a_id].simplified, words[existing.word_b_id].simplified)

    first, second = sorted((first, second), key=lambda word: word.id)
    result = ai.generate_confusable(first.simplified, first.meaning_vi, second.simplified, second.meaning_vi)
    ingestion.insert_missing(
        db,
        ConfusablePair,
        {
            "word_a_id": first.id,
            "word_b_id": second.id,
            **result.model_dump(),
            "cloze_a_answer": first.simplified,
            "cloze_b_answer": second.simplified,
            "hsk_level": max(first.hsk_level or 0, second.hsk_level or 0) or 5,
        },
        [ConfusablePair.word_a_id, ConfusablePair.word_b_id],
    )
    pair = db.scalars(select(ConfusablePair).where(
        ConfusablePair.word_a_id == first.id, ConfusablePair.word_b_id == second.id,
    )).one()
    enqueue(db, "confusable", pair.id)
    db.commit()
    return _pair_result(pair, first.simplified, second.simplified)


@router.get("/story/words", response_model=StoryWords)
def story_words(db: Database) -> StoryWords:
    recent_reviews = (
        select(ReviewLog.card_id, func.max(ReviewLog.reviewed_at).label("last_seen"))
        .group_by(ReviewLog.card_id).subquery()
    )
    candidates = db.execute(
        select(Word.simplified, UserCard.is_leech, recent_reviews.c.last_seen)
        .outerjoin(UserCard, and_(UserCard.item_id == Word.id, UserCard.item_type == "word"))
        .outerjoin(recent_reviews, recent_reviews.c.card_id == UserCard.id)
        .where(Word.hsk_level.in_([4, 5]))
        .where((UserCard.status != "ignored") | UserCard.status.is_(None))
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    leeches, recent, remaining = [], [], []
    for name, is_leech, last_seen in candidates:
        if is_leech:
            leeches.append(name)
        elif last_seen and (last_seen if last_seen.tzinfo else last_seen.replace(tzinfo=timezone.utc)) >= cutoff:
            recent.append(name)
        else:
            remaining.append(name)

    preferred = leeches + recent
    if len(preferred) >= 5:
        chosen = random.sample(preferred, 5)
        if leeches and not set(chosen).intersection(leeches):
            chosen[0] = random.choice(leeches)
    else:
        chosen = preferred + random.sample(remaining, min(5 - len(preferred), len(remaining)))
    if len(chosen) < 5:
        raise HTTPException(status_code=422, detail="Kho cần ít nhất năm từ HSK 4–5 để tạo đề viết.")
    random.shuffle(chosen)
    return StoryWords(words=chosen)


@router.post("/story", response_model=StoryResult, status_code=201)
def grade_story(payload: StoryRequest, db: Database) -> StoryResult:
    known = set(db.scalars(select(Word.simplified).where(
        Word.simplified.in_(payload.target_words), Word.hsk_level.in_([4, 5]),
    )))
    if known != set(payload.target_words):
        raise HTTPException(status_code=422, detail="Hãy lấy đề mới gồm năm từ HSK 4–5 trong kho.")
    if not any(is_hanzi(char) for char in payload.text):
        raise HTTPException(status_code=422, detail="Hãy viết một đoạn bằng chữ Hán trước khi chấm.")
    grade = ai.grade_story(payload.target_words, payload.text)
    attempt = StoryAttempt(
        target_words=payload.target_words,
        text=payload.text,
        score=grade.score,
        feedback=grade.model_dump(exclude={"score"}),
    )
    db.add(attempt)
    db.commit()
    return StoryResult.model_validate(attempt)


@router.get("/story", response_model=list[StoryResult])
def story_history(
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[StoryResult]:
    rows = db.scalars(
        select(StoryAttempt).order_by(StoryAttempt.created_at.desc(), StoryAttempt.id.desc()).offset(offset).limit(limit)
    )
    return [StoryResult.model_validate(row) for row in rows]
