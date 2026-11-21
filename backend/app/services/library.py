import re

import jieba
from pypinyin import lazy_pinyin, Style
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import UserCard, Word
from app.schemas.study import ReaderToken, WordPage, WordView

HANZI = re.compile(r"[\u3007\u3400-\u9fff\uf900-\ufaff\U00020000-\U000323af]")


def with_word_status():
    return select(Word, UserCard.status).outerjoin(
        UserCard, and_(UserCard.item_type == "word", UserCard.item_id == Word.id),
    )


def word_view(word: Word, status: str | None) -> WordView:
    return WordView.model_validate(word).model_copy(update={"status": status})


def filter_words(query, q: str, level: int | None):
    if level is not None:
        query = query.where(Word.hsk_level == (level or None))
    if q.strip():
        term = q.strip()
        query = query.where(or_(
            Word.simplified.icontains(term, autoescape=True),
            Word.traditional.icontains(term, autoescape=True),
            Word.pinyin.icontains(term, autoescape=True),
            Word.han_viet.icontains(term, autoescape=True),
            Word.meaning_vi.icontains(term, autoescape=True),
        ))
    return query


def word_page(db: Session, query, limit: int, offset: int) -> WordPage:
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    entries = db.execute(query.order_by(Word.hsk_level.nulls_last(), Word.id).limit(limit).offset(offset))
    return WordPage(items=[word_view(word, status) for word, status in entries], total=total)


def pinyin(text: str) -> str:
    return " ".join(lazy_pinyin(text, style=Style.TONE))


def segment_text(db: Session, text: str) -> list[ReaderToken]:
    chunks = list(jieba.cut(text))
    candidates = {chunk for chunk in chunks if HANZI.search(chunk)}
    entries = db.execute(with_word_status()
        .where(or_(Word.simplified.in_(candidates), Word.traditional.in_(candidates)))
        .order_by(Word.id))
    known = {}
    for word, status in entries:
        view = word_view(word, status)
        if word.traditional in candidates:
            known.setdefault(word.traditional, view)
        known[word.simplified] = view
    return [ReaderToken(text=chunk, word=known.get(chunk)) for chunk in chunks]
