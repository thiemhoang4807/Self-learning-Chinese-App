from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fsrs import Card, State
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import ingestion, manage, study
from app.db import Base, get_db
from app.models import (
    GrammarPattern, ReviewLog, Sentence, SentenceWord, SourcePattern, SourceSentence,
    SourceWord, UserCard, Word,
)
from app.services.study import as_utc

MATERIAL = {
    "title": "Bài một",
    "source_type": "paste",
    "summary_note": "Từ chỉ trái cây.",
    "words": [
        {"simplified": "苹果", "pinyin": "píngguǒ", "meaning_vi": "quả táo"},
        {"simplified": "云猫", "pinyin": "yúnmāo", "meaning_vi": "mèo mây"},
    ],
    "grammar_patterns": [{
        "pattern_formula": "S + 有 + O", "title_vi": "Có một vật",
        "explanation_vi": "Đặt 有 trước vật đang có.",
    }],
    "sentences": [{
        "hanzi": "我有苹果。", "pinyin": "Wǒ yǒu píngguǒ.", "meaning_vi": "Tôi có táo.",
        "pattern_formula": "S + 有 + O",
    }],
}
REVIEWED = datetime(2024, 4, 14, 10, 20, tzinfo=timezone.utc)
DUE = REVIEWED + timedelta(days=42)


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    app = FastAPI()
    for module in (ingestion, manage, study):
        app.include_router(module.router, prefix="/api")

    def test_db():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as client:
        yield client, engine
    engine.dispose()


@pytest.fixture
def saved(api):
    client, engine = api
    first = client.post("/api/ingestion/save", json=MATERIAL)
    second = client.post("/api/ingestion/save", json={
        **MATERIAL, "title": "Bài hai", "words": MATERIAL["words"][:1],
    })
    assert first.status_code == second.status_code == 201

    with Session(engine) as db:
        word = db.scalar(select(Word).where(Word.simplified == "苹果"))
        custom = db.scalar(select(Word).where(Word.simplified == "云猫"))
        pattern = db.scalars(select(GrammarPattern)).one()
        sentence = db.scalars(select(Sentence)).one()
        card = db.scalar(select(UserCard).where(UserCard.item_type == "word", UserCard.item_id == word.id))
        state = Card(
            card_id=card.id, state=State.Review, stability=24, difficulty=5, due=DUE, last_review=REVIEWED,
        ).to_dict()
        card.status = "mastered"
        card.fsrs_state_json = state
        card.due = DUE
        card.reps = 8
        card.wrong_count = 1
        card.lapses = 1
        db.add(ReviewLog(
            card_id=card.id, rating=4, drill_mode="flashcard", response_ms=250,
            reviewed_at=REVIEWED, review_token="before-manage",
        ))
        ids = {
            "first": first.json()["id"], "second": second.json()["id"], "word": word.id,
            "custom": custom.id, "pattern": pattern.id, "sentence": sentence.id, "card": card.id,
        }
        db.commit()
    return client, engine, ids, state


def assert_schedule(db, card_id, state, status="mastered"):
    card = db.get(UserCard, card_id)
    assert card.status == status
    assert card.fsrs_state_json == state
    assert as_utc(card.due) == DUE
    assert (card.reps, card.lapses, card.wrong_count) == (8, 1, 1)
    review = db.scalars(select(ReviewLog).where(ReviewLog.card_id == card_id)).one()
    assert as_utc(review.reviewed_at) == REVIEWED
    assert (review.rating, review.response_ms, review.review_token) == (4, 250, "before-manage")


def test_edit_knowledge_items_without_changing_existing_relationships(saved):
    client, engine, ids, state = saved
    word_path = f'/api/words/{ids["word"]}'
    edits = {
        "pinyin": "píng guǒ", "han_viet": "bình quả", "meaning_vi": "trái táo", "pos": "danh từ",
        "hsk_level": None, "mnemonic_vi": "Quả trên cây.", "usage_note_vi": "Dùng với 个.",
    }
    word = client.patch(word_path, json=edits)
    assert word.status_code == 200
    assert all(word.json()[field] == value for field, value in edits.items())
    assert client.get(word_path).json() == word.json()
    assert word.json()["simplified"] == "苹果"
    assert client.patch(word_path, json={"simplified": "梨"}).status_code == 422
    assert client.patch(word_path, json={"pinyin": None}).status_code == 422
    assert client.patch(word_path, json={"hsk_level": 6}).status_code == 422

    pattern_path = f'/api/patterns/{ids["pattern"]}'
    revised_pattern = client.patch(pattern_path, json={
        "title_vi": " Diễn đạt sở hữu ", "explanation_vi": "Đặt 有 trước danh từ chỉ vật.",
        "hsk_level": 2, "structure_notes_vi": "Có thể dùng 没有 để phủ định.",
    })
    assert revised_pattern.status_code == 200
    assert revised_pattern.json()["title_vi"] == "Diễn đạt sở hữu"
    assert revised_pattern.json()["pattern_formula"] == MATERIAL["grammar_patterns"][0]["pattern_formula"]
    assert client.get(pattern_path).json() == revised_pattern.json()
    patterns = client.get("/api/patterns", params={"q": "sở hữu", "source_id": ids["second"]}).json()
    assert patterns == {"items": [revised_pattern.json()], "total": 1}

    sentence_path = f'/api/sentences/{ids["sentence"]}'
    updated_sentence = client.patch(sentence_path, json={"pinyin": "Wǒ yǒu píng guǒ.", "meaning_vi": "Tôi có quả táo."})
    assert updated_sentence.status_code == 200
    assert updated_sentence.json()["hanzi"] == MATERIAL["sentences"][0]["hanzi"]
    assert updated_sentence.json()["grammar_pattern_id"] == ids["pattern"]
    assert client.get(sentence_path).json() == updated_sentence.json()
    sentences = client.get("/api/sentences", params={"q": "quả táo", "source_id": ids["first"]}).json()
    assert sentences == {"items": [updated_sentence.json()], "total": 1}
    assert client.get("/api/sentences", params={"q": "quả táo", "offset": 1}).json() == {"items": [], "total": 1}

    with Session(engine) as db:
        assert_schedule(db, ids["card"], state)
        link = db.scalars(select(SentenceWord).where(SentenceWord.word_id == ids["word"])).one()
        assert link.sentence_id == ids["sentence"]


def test_rename_and_delete_source_keep_shared_items_and_review_history(saved):
    client, engine, ids, state = saved
    path = f'/api/sources/{ids["first"]}'
    assert client.patch(path, json={"title": " "}).status_code == 422
    renamed = client.patch(path, json={"title": "Bài táo", "summary_note": "Ghi chú mới"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Bài táo"
    assert renamed.json()["summary_note"] == "Ghi chú mới"
    assert renamed.json()["word_count"] == 2
    assert renamed.json()["pattern_count"] == renamed.json()["sentence_count"] == 1
    assert client.get(path).json() == renamed.json()

    deleted = client.delete(path)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(path).status_code == 404
    assert client.get("/api/study/session", params={"source_id": ids["first"]}).status_code == 404
    second = client.get(f'/api/sources/{ids["second"]}').json()
    assert second["word_count"] == second["pattern_count"] == second["sentence_count"] == 1
    with Session(engine) as db:
        assert db.get(Word, ids["word"]).hsk_level == 1
        assert db.get(Word, ids["custom"]) is not None
        assert db.get(GrammarPattern, ids["pattern"]) is not None
        assert db.get(Sentence, ids["sentence"]) is not None
        for model in (SourceWord, SourcePattern, SourceSentence):
            assert db.scalars(select(model.source_id)).all() == [ids["second"]]
        assert_schedule(db, ids["card"], state)


def test_archiving_is_reversible_and_blocks_review_from_stale_sessions(saved):
    client, engine, ids, state = saved
    path = f'/api/words/{ids["word"]}'
    archived = client.patch(path, json={"status": "ignored"})
    assert archived.status_code == 200
    assert archived.json()["status"] == "ignored"
    study_list = client.get("/api/study/session", params={"mode": "flashcard", "source_id": ids["second"]}).json()
    assert study_list["cards"] == []

    stale = client.post(f'/api/study/cards/{ids["card"]}/review', json={
        "rating": 3, "drill_mode": "flashcard", "response_ms": 200,
    })
    assert stale.status_code == 409
    with Session(engine) as db:
        assert_schedule(db, ids["card"], state, status="ignored")
    assert client.patch(path, json={"status": "active"}).json()["status"] == "mastered"

    client.patch(path, json={"status": "ignored"})
    assert client.post("/api/study/queue", json={"item_type": "word", "item_ids": [ids["word"]]}).json() == {"queued": 1}
    with Session(engine) as db:
        assert_schedule(db, ids["card"], state)


def test_archiving_word_without_card_keeps_it_out_of_new_sessions(api):
    client, engine = api
    with Session(engine) as db:
        word = Word(simplified="苹果", pinyin="píngguǒ", meaning_vi="trái táo", hsk_level=1)
        db.add(word)
        db.flush()
        word_id = word.id
        db.commit()

    path = f"/api/words/{word_id}"
    assert client.patch(path, json={"status": "ignored"}).json()["status"] == "ignored"
    assert client.get("/api/study/session", params={"mode": "flashcard"}).json() == {"cards": []}
    assert client.patch(path, json={"status": "active"}).json()["status"] == "new"
    cards = client.get("/api/study/session", params={"mode": "flashcard"}).json()["cards"]
    assert [card["item_id"] for card in cards] == [word_id]
