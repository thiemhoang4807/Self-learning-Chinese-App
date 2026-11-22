import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Word
from app.services.ai import check_readiness
from app.services.audio import cached_audio_count

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def service_status(response: Response, db: Annotated[Session, Depends(get_db)]):
    database = "ok"
    word_count: int | None = None
    try:
        word_count = db.scalar(select(func.count()).select_from(Word).where(Word.hsk_level.is_not(None)))
    except SQLAlchemyError as error:
        logger.warning("Database health query failed: %s", type(error).__name__)
        database = "unavailable"
        response.status_code = 503
    response.headers["Cache-Control"] = "no-store"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "hsk_word_count": word_count,
        "tts_cache_count": cached_audio_count(),
        "gemini_configured": bool(settings.gemini_api_key.get_secret_value().strip()),
        "gemini_model": settings.gemini_model,
    }


@router.post("/gemini")
def gemini_status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"status": "ok", "model": check_readiness()}
