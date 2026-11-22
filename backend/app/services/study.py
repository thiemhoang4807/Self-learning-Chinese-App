from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler, State
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import ReviewLog, UserCard
from app.schemas.study import RatingRequest

scheduler = Scheduler()


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _scheduled_status(state: State | int, stability: float | None) -> str:
    if state != State.Review:
        return "learning"
    return "mastered" if (stability or 0) >= 14 else "review"


def restored_card_status(card: UserCard) -> str:
    state = card.fsrs_state_json
    if state:
        return _scheduled_status(state["state"], state.get("stability"))
    return "review" if card.reps else "new"


def enqueue_many(db: Session, item_type: str, item_ids: list[int], *, reactivate: bool = False) -> int:
    if not item_ids:
        return 0
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    statement = insert(UserCard).values([
        {"item_type": item_type, "item_id": item_id} for item_id in sorted(set(item_ids))
    ])
    statement = statement.on_conflict_do_nothing(index_elements=[UserCard.item_type, UserCard.item_id])
    inserted = len(db.scalars(statement.returning(UserCard.id)).all())
    if not reactivate:
        return inserted
    archived = db.scalars(select(UserCard).where(
        UserCard.item_type == item_type, UserCard.item_id.in_(item_ids), UserCard.status == "ignored",
    ).order_by(UserCard.item_id).with_for_update()).all()
    for card in archived:
        card.status = restored_card_status(card)
    return inserted + len(archived)


def enqueue(db: Session, item_type: str, item_id: int) -> UserCard:
    enqueue_many(db, item_type, [item_id])
    return db.scalars(select(UserCard).where(UserCard.item_type == item_type, UserCard.item_id == item_id)).one()


def apply_rating(
    db: Session, card: UserCard, review: RatingRequest, *, now: datetime | None = None,
) -> None:
    now = as_utc(now) if now is not None else datetime.now(timezone.utc)
    previous = Card.from_dict(card.fsrs_state_json) if card.fsrs_state_json else Card(
        card_id=card.id, due=as_utc(card.due),
    )
    updated, _ = scheduler.review_card(previous, Rating(review.rating), now, review.response_ms)
    if review.rating == Rating.Again:
        card.wrong_count += 1
        if previous.state == State.Review:
            card.lapses += 1
    card.reps += 1
    card.is_leech = card.lapses >= 4 or (card.wrong_count >= 4 and card.wrong_count / card.reps >= 0.4)
    card.status = _scheduled_status(updated.state, updated.stability)
    card.fsrs_state_json = updated.to_dict()
    card.due = updated.due
    db.add(ReviewLog(
        card_id=card.id,
        rating=review.rating,
        drill_mode=review.drill_mode,
        response_ms=review.response_ms,
        reviewed_at=now,
        review_token=review.review_token,
    ))
