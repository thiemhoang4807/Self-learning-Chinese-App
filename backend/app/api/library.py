from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db, lock_catalog
from app.models import Character, SourceWord, Word, WordCharacter
from app.schemas.study import (
    CharacterTree, CharacterView, DashboardView, ReaderLookup, ReaderResult, ReaderText, WordPage, WordView,
)
from app.seeds.levels import compounds_containing
from app.seeds.seed_data import import_words
from app.services import ai, ingestion
from app.services.analytics import dashboard
from app.services.audio import SpeechUnavailable, audio_file
from app.services.library import HANZI, filter_words, pinyin, segment_text, with_word_status, word_page, word_view

router = APIRouter()
Database = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/vault/words", response_model=WordPage)
def vault_words(
    db: Database, q: Annotated[str, Query(max_length=100)] = "",
    level: Annotated[int | None, Query(ge=0, le=5)] = None, limit: Limit = 24, offset: Offset = 0,
):
    return word_page(db, filter_words(with_word_status(), q, level), limit, offset)


@router.get("/vault/characters/{char}", response_model=CharacterTree)
def character_tree(char: str, db: Database):
    if not HANZI.fullmatch(char):
        raise HTTPException(422, "Chọn một chữ Hán để mở cây chữ.")
    saved = db.scalar(select(Character).where(Character.char == char))
    if saved is None and settings.gemini_api_key.get_secret_value():
        try:
            payload = ai.lookup_word(char)
            lock_catalog(db)
            ingestion.upsert_word(db, payload, enrich_existing=True)
            db.commit()
        except HTTPException:
            db.rollback()
        saved = db.scalar(select(Character).where(Character.char == char))
    compounds = compounds_containing(char)
    known = set(db.scalars(select(Word.simplified).where(Word.simplified.in_(compounds))))
    if len(known) < len(compounds):
        lock_catalog(db)
        import_words(db, (
            {"simplified": word, "hsk_level": level}
            for word, level in compounds.items() if word not in known
        ))
        db.commit()
        saved = db.scalar(select(Character).where(Character.char == char))
    if saved is None:
        character = CharacterView(id=0, char=char, pinyin=pinyin(char), han_viet="", radical="",
                                  components_json=[], mnemonic_vi="", hsk_level=None)
        return CharacterTree(character=character, words=[])
    query = with_word_status().where(select(WordCharacter).where(
        WordCharacter.word_id == Word.id, WordCharacter.character_id == saved.id,
    ).exists()).order_by(Word.hsk_level.nulls_last(), Word.simplified)
    return CharacterTree(character=CharacterView.model_validate(saved),
                         words=[word_view(word, status) for word, status in db.execute(query)])


@router.post("/reader/segment", response_model=ReaderResult)
def reader_segment(payload: ReaderText, db: Database):
    if not HANZI.search(payload.text):
        raise HTTPException(422, "Hãy dán một đoạn văn có chữ Hán.")
    return ReaderResult(tokens=segment_text(db, payload.text))


@router.post("/reader/lookup", response_model=WordView)
def reader_lookup(payload: ReaderLookup, db: Database):
    name = payload.word.strip()
    if not all(HANZI.fullmatch(char) for char in name) or not name:
        raise HTTPException(422, "Chọn một từ tiếng Trung để tra nghĩa.")
    query = with_word_status()
    known = db.execute(query.where(or_(Word.simplified == name, Word.traditional == name))
        .order_by((Word.simplified == name).desc(), Word.id)).first()
    if known is not None and (known[0].meaning_vi or not settings.gemini_api_key.get_secret_value()):
        return word_view(*known)
    details = ai.lookup_word(name)
    lock_catalog(db)
    word = ingestion.upsert_word(db, details, enrich_existing=True)
    db.commit()
    return word_view(word, known[1] if known is not None else None)


@router.get("/dashboard", response_model=DashboardView)
def metrics(db: Database):
    return dashboard(db)


@router.get("/dashboard/gaps/{level}", response_model=WordPage)
def gap_words(level: int, db: Database, limit: Limit = 24, offset: Offset = 0):
    if not 1 <= level <= 5:
        raise HTTPException(422, "Chọn một cấp HSK từ 1 đến 5.")
    query = with_word_status().where(Word.hsk_level == level,
        ~select(SourceWord).where(SourceWord.word_id == Word.id).exists())
    return word_page(db, query, limit, offset)


@router.get("/settings")
def preferences():
    return {"gemini_configured": bool(settings.gemini_api_key.get_secret_value().strip()),
            "gemini_model": settings.gemini_model}


@router.get("/audio/tts", response_class=FileResponse)
async def tts(
    request: Request,
    text: Annotated[str, Query(min_length=1, max_length=600)],
    rate: Annotated[float, Query(ge=0.5, le=2.0)] = 1.0,
    voice: Literal["zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural"] = "zh-CN-XiaoxiaoNeural",
):
    try:
        file = await audio_file(text, voice, rate)
        stats = file.stat()
    except (SpeechUnavailable, OSError):
        return JSONResponse({"detail": "Không thể tạo âm thanh lúc này", "fallback": "web_speech"},
                            status_code=503, headers={"Cache-Control": "no-store"})

    response = FileResponse(file, stat_result=stats, media_type="audio/mpeg",
                            headers={"Cache-Control": "private, max-age=31536000, immutable"})
    matches = {etag.strip().removeprefix("W/") for etag in request.headers.get("if-none-match", "").split(",")}
    if "*" in matches or response.headers["etag"] in matches:
        return Response(status_code=304, headers={"ETag": response.headers["etag"],
                                                  "Cache-Control": response.headers["cache-control"]})
    return response
