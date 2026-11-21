from collections import Counter
from datetime import datetime, timedelta, timezone
from math import ceil

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import ReviewLog, SourceWord, UserCard, Word
from app.schemas.study import CoverageLevel, DashboardView, LeechView, Pace
from app.seeds.levels import target_levels
from app.services.study import as_utc

HSK_TARGET = {1: 150, 2: 150, 3: 300, 4: 600, 5: 1300}
VIETNAM_TIME = timezone(timedelta(hours=7))


def dashboard(db: Session, *, now: datetime | None = None) -> DashboardView:
    now = as_utc(now) if now is not None else datetime.now(timezone.utc)
    first_successes = select(ReviewLog.card_id, func.min(ReviewLog.reviewed_at).label("first_at")).where(
        ReviewLog.rating >= 3, ReviewLog.reviewed_at <= now,
    ).group_by(ReviewLog.card_id).subquery()
    ingested = select(SourceWord).where(SourceWord.word_id == Word.id).exists()
    entries = db.execute(select(Word.simplified, Word.hsk_level, UserCard.status, ingested, first_successes.c.first_at)
        .outerjoin(UserCard, and_(UserCard.item_id == Word.id, UserCard.item_type == "word"))
        .outerjoin(first_successes, first_successes.c.card_id == UserCard.id)
        .where(Word.hsk_level.is_not(None)))
    catalog_counts: Counter[int] = Counter()
    ingested_counts: Counter[int] = Counter()
    mastered_counts: Counter[int] = Counter()
    covered: Counter[int] = Counter()
    recent = 0
    window_start = now - timedelta(days=7)
    for name, level, status, from_source, first_at in entries:
        levels = target_levels(name) or (level,)
        catalog_counts.update(levels)
        if from_source:
            ingested_counts.update(levels)
        if status == "mastered":
            mastered_counts.update(levels)
        if first_at is not None:
            covered.update(levels)
            if as_utc(first_at) > window_start:
                recent += 1
    coverage = [
        CoverageLevel(
            level=level, total=total, mastered=mastered_counts.get(level, 0),
            ingested=ingested_counts.get(level, 0), available=catalog_counts.get(level, 0),
        )
        for level, total in HSK_TARGET.items()
    ]

    remaining = sum(max(total - covered[level], 0) for level, total in HSK_TARGET.items())
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
