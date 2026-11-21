from datetime import datetime, timedelta, timezone
from math import ceil

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models import ReviewLog, SourceWord, UserCard, Word
from app.schemas.study import CoverageLevel, DashboardView, LeechView, Pace
from app.services.study import as_utc

HSK_TARGET = {1: 150, 2: 150, 3: 300, 4: 600, 5: 1300}
VIETNAM_TIME = timezone(timedelta(hours=7))


def dashboard(db: Session, *, now: datetime | None = None) -> DashboardView:
    now = as_utc(now) if now is not None else datetime.now(timezone.utc)
    catalog_counts = dict(db.execute(select(Word.hsk_level, func.count())
        .where(Word.hsk_level.is_not(None)).group_by(Word.hsk_level)).all())
    ingested_counts = dict(db.execute(select(Word.hsk_level, func.count(distinct(Word.id)))
        .join(SourceWord, SourceWord.word_id == Word.id)
        .where(Word.hsk_level.is_not(None)).group_by(Word.hsk_level)).all())
    mastered_counts = dict(db.execute(select(Word.hsk_level, func.count())
        .join(UserCard, UserCard.item_id == Word.id)
        .where(Word.hsk_level.is_not(None), UserCard.item_type == "word", UserCard.status == "mastered")
        .group_by(Word.hsk_level)).all())
    coverage = [
        CoverageLevel(
            level=level, total=total, mastered=mastered_counts.get(level, 0),
            ingested=ingested_counts.get(level, 0), available=catalog_counts.get(level, 0),
        )
        for level, total in HSK_TARGET.items()
    ]

    first_successes = select(UserCard.id, func.min(ReviewLog.reviewed_at).label("first_at")).join(
        ReviewLog, ReviewLog.card_id == UserCard.id,
    ).join(Word, Word.id == UserCard.item_id).where(
        UserCard.item_type == "word", Word.hsk_level.is_not(None), ReviewLog.rating >= 3,
        ReviewLog.reviewed_at <= now,
    ).group_by(UserCard.id).subquery()
    covered = db.scalar(select(func.count()).select_from(first_successes)) or 0
    recent = db.scalar(select(func.count()).select_from(first_successes)
        .where(first_successes.c.first_at > now - timedelta(days=7))) or 0
    remaining = max(sum(HSK_TARGET.values()) - covered, 0)
    today = now.astimezone(VIETNAM_TIME).date()
    projection = None
    if remaining == 0:
        projection = today
    elif recent:
        projection = today + timedelta(days=ceil(remaining * 7 / recent))

    missed = db.execute(select(UserCard, Word).join(Word, Word.id == UserCard.item_id)
        .where(UserCard.item_type == "word", UserCard.is_leech.is_(True), UserCard.status != "ignored")
        .order_by(UserCard.wrong_count.desc(), UserCard.id).limit(20))
    return DashboardView(
        levels=coverage, pace=Pace(words_per_day=round(recent / 7, 2), remaining=remaining, projected_date=projection),
        leeches=[
            LeechView(card_id=card.id, word_id=word.id, simplified=word.simplified,
                      pinyin=word.pinyin, meaning_vi=word.meaning_vi, wrong_count=card.wrong_count)
            for card, word in missed
        ],
    )
