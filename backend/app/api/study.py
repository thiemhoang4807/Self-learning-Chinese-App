from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ReviewLog, Source, UserCard
from app.schemas.study import QueueRequest, QueueResult, RatingRequest, RatingResult, SessionMode, StudySession
from app.services.drills import ITEM_MODELS, study_session
from app.services.study import apply_rating, enqueue_many

router = APIRouter(prefix="/study", tags=["study"])
Database = Annotated[Session, Depends(get_db)]


@router.get("/session", response_model=StudySession)
def session(
    response: Response, db: Database, size: Annotated[int, Query(ge=1, le=30)] = 8,
    mode: SessionMode = "mixed", source_id: Annotated[int | None, Query(gt=0)] = None,
    hsk_level: Annotated[int | None, Query(ge=1, le=5)] = None, leeches: bool = False,
):
    if source_id is not None and db.get(Source, source_id) is None:
        raise HTTPException(404, "Không tìm thấy tài liệu này.")
    result = study_session(db, size, mode, source_id, hsk_level, leeches)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return StudySession(cards=result)


@router.post("/queue", response_model=QueueResult)
def queue(payload: QueueRequest, db: Database):
    model = ITEM_MODELS[payload.item_type]
    ids = set(payload.item_ids)
    found = db.scalars(select(model.id).where(model.id.in_(ids))).all()
    if len(found) != len(ids):
        raise HTTPException(404, "Một số mục đã chọn không còn trong kho.")
    added = enqueue_many(db, payload.item_type, list(ids), reactivate=True)
    db.commit()
    return QueueResult(queued=added)


@router.post("/cards/{card_id}/review", response_model=RatingResult)
def review(card_id: int, payload: RatingRequest, db: Database):
    card = db.scalar(select(UserCard).where(UserCard.id == card_id).with_for_update())
    if card is None:
        raise HTTPException(404, "Không tìm thấy thẻ ôn.")
    if payload.review_token:
        previous = db.scalar(select(ReviewLog).where(ReviewLog.review_token == payload.review_token))
        if previous is not None:
            if (previous.card_id, previous.rating, previous.drill_mode) != (card.id, payload.rating, payload.drill_mode):
                raise HTTPException(409, "Mã đánh giá đã được dùng cho lượt ôn khác.")
            return card
    apply_rating(db, card, payload)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Mã đánh giá đã được dùng cho lượt ôn khác.") from error
    return card
