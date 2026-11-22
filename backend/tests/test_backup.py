import json
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import backup
from app.db import Base, get_db
from app.models import (
    Character, ConfusablePair, GrammarPattern, ReviewLog, Sentence, SentenceWord, Source,
    SourcePattern, SourceSentence, SourceWord, StoryAttempt, UserCard, Word, WordCharacter,
)
from app.schemas.study import RatingRequest
from app.services.study import apply_rating

CREATED = datetime(2026, 10, 17, 4, 30, tzinfo=timezone.utc)


@contextmanager
def backup_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(backup.router, prefix="/api")

    def test_session():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = test_session
    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        engine.dispose()


def upload(client, payload):
    return client.post("/api/backup/import", files={
        "file": ("hoc-trung.json", json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json"),
    })


def exported(client):
    response = client.get("/api/backup/export")
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert re.fullmatch(
        r'attachment; filename="chinese-study-backup-\d{8}-\d{6}.json"',
        response.headers["Content-Disposition"],
    )
    assert response.content.startswith(b"{") and response.headers["Content-Type"] == "application/json"
    payload = response.json()
    payload.pop("exported_at")
    return payload


def build_history(engine):
    with Session(engine) as db, db.begin():
        term = Word(
            simplified="风说", pinyin="fēng shuō", meaning_vi="chuyện gió kể",
            han_viet="phong thuyết", mnemonic_vi="Nghe gió kể chuyện.",
        )
        known = Word(simplified="说", pinyin="shuō", meaning_vi="nói, kể", hsk_level=1)
        character = Character(char="风", pinyin="fēng", components_json=["几", "乂"])
        pattern = GrammarPattern(pattern_formula="话 + S", title_vi="Mẫu tự tạo", explanation_vi="Mẫu ghi chú.")
        sources = [Source(title="Trình bày", source_type="pptx", created_at=CREATED) for _ in range(2)]
        db.add_all([term, known, character, pattern, *sources])
        db.flush()
        sentence = Sentence(hanzi="风说了一个故事。", pinyin="Fēng shuō le yí ge gùshi.",
                            meaning_vi="Gió kể một câu chuyện.", grammar_pattern_id=pattern.id,
                            is_ai_generated=True, created_at=CREATED)
        pair = ConfusablePair(
            word_a_id=term.id, word_b_id=known.id, diff_explanation_vi="Hai cách diễn đạt.",
            cloze_a_hanzi="__了", cloze_a_answer="风说", cloze_b_hanzi="我__。", cloze_b_answer="说", hsk_level=1,
        )
        db.add_all([sentence, pair])
        db.flush()
        db.add_all([
            WordCharacter(word_id=term.id, character_id=character.id, position=0),
            SentenceWord(sentence_id=sentence.id, word_id=term.id),
            SourceWord(source_id=sources[0].id, word_id=term.id),
            SourceWord(source_id=sources[1].id, word_id=term.id),
            SourceWord(source_id=sources[1].id, word_id=known.id),
            SourcePattern(source_id=sources[0].id, pattern_id=pattern.id),
            SourceSentence(source_id=sources[0].id, sentence_id=sentence.id),
        ])
        cards = [
            UserCard(item_type="word", item_id=term.id, due=CREATED),
            UserCard(item_type="pattern", item_id=pattern.id, due=CREATED, status="ignored"),
            UserCard(item_type="confusable", item_id=pair.id, due=CREATED),
        ]
        db.add_all(cards)
        db.flush()
        for index in range(3):
            apply_rating(db, cards[0], RatingRequest(
                rating=1, drill_mode="passive", response_ms=104, review_token=f"record-{index}" if index == 0 else None,
            ), now=CREATED + timedelta(days=index))
        cards[0].is_leech = True
        db.add(StoryAttempt(
            target_words=["风说", "故事", "风", "话", "说"], text="风说了一个故事。", score=91,
            feedback={"summary": "Mạch lạc.", "used": ["风说", "故事"]}, created_at=CREATED,
        ))


def test_backup_round_trip_to_empty_database_and_idempotent_reimport():
    with backup_client() as (original, original_db), backup_client() as (target, _):
        build_history(original_db)
        assert original.get("/api/backup/preferences").json() is None
        assert original.patch("/api/backup/preferences", json={"theme": "dark"}).json() == {
            "theme": "dark", "pinyin": False,
        }
        original.patch("/api/backup/preferences", json={"pinyin": True}).raise_for_status()
        snapshot = exported(original)
        assert snapshot["schema_version"] == 1
        assert snapshot["user_cards"][0]["fsrs_state_json"]["last_review"].startswith("2026-10-19")
        assert len({source["backup_uid"] for source in snapshot["sources"]}) == 2

        snapshot["exported_at"] = CREATED.isoformat()
        restored = upload(target, snapshot)
        assert restored.status_code == 200, restored.text
        first = restored.json()
        assert (first["words_created"], first["sources_created"], first["cards_created"],
                first["reviews_added"], first["stories_added"]) == (2, 2, 3, 3, 1)
        assert first["preferences"] == {"theme": "dark", "pinyin": True}
        assert target.get("/api/backup/preferences").json() == first["preferences"]
        assert exported(target) == {key: value for key, value in snapshot.items() if key != "exported_at"}

        second = upload(target, snapshot)
        assert second.status_code == 200 and all(
            value == 0 for key, value in second.json().items() if key not in {"preferences", "message"}
        )


def test_restore_relinks_natural_ids_and_preserves_newer_reviews():
    with backup_client() as (original, original_db), backup_client() as (target, target_db):
        build_history(original_db)
        snapshot = exported(original)
        snapshot["exported_at"] = CREATED.isoformat()
        with Session(target_db) as db, db.begin():
            db.add_all([
                Word(id=1, simplified="东西", pinyin="dōngxi", meaning_vi="đồ vật"),
                Word(id=2, simplified="风说", pinyin="", meaning_vi="Sẽ được bổ sung"),
                Source(id=1, title="Nguồn hiện có", source_type="paste", created_at=CREATED),
            ])
        result = upload(target, snapshot)
        assert result.status_code == 200, result.text
        assert result.json()["words_updated"] == 1
        with Session(target_db) as db, db.begin():
            word = db.scalar(select(Word).where(Word.simplified == "风说"))
            card = db.scalar(select(UserCard).where(UserCard.item_type == "word", UserCard.item_id == word.id))
            assert word.id == 2 and word.meaning_vi == "chuyện gió kể" and card.reps == 3
            links = db.scalars(select(SourceWord).where(SourceWord.word_id == word.id)).all()
            assert len(links) == 2
            assert {db.get(Source, link.source_id).title for link in links} == {"Trình bày"}

            apply_rating(db, card, RatingRequest(
                rating=4, drill_mode="flashcard", response_ms=215, review_token="newer-review",
            ), now=CREATED + timedelta(days=10))
            latest_state = card.fsrs_state_json

        newer = upload(target, snapshot)
        assert newer.status_code == 200 and newer.json()["cards_updated"] == newer.json()["reviews_added"] == 0
        with Session(target_db) as db:
            card = db.scalar(select(UserCard).where(UserCard.item_type == "word", UserCard.item_id == 2))
            assert card.reps == 4 and card.fsrs_state_json == latest_state
            assert len(db.scalars(select(ReviewLog).where(ReviewLog.card_id == card.id)).all()) == 4
            assert db.get(Source, 1).title == "Nguồn hiện có"


def test_invalid_and_conflicting_snapshots_cannot_partially_overwrite_data():
    with backup_client() as (client, engine):
        build_history(engine)
        snapshot = exported(client)
        snapshot["exported_at"] = CREATED.isoformat()
        assert upload(client, {**snapshot, "schema_version": 2}).json()["detail"] == (
            "Phiên bản của tệp sao lưu chưa được hỗ trợ."
        )

        bad_link = {**snapshot, "source_words": [
            {"source_id": 99999, "word_id": snapshot["words"][0]["id"]},
        ]}
        assert upload(client, bad_link).status_code == 422
        bad_position = {**snapshot, "word_characters": [{**snapshot["word_characters"][0], "position": 2}]}
        assert upload(client, bad_position).status_code == 422

        snapshot["words"][0]["meaning_vi"] = "Đây là thay đổi phải được hoàn tác."
        snapshot["review_logs"][0]["rating"] = 4
        conflict = upload(client, snapshot)
        assert conflict.status_code == 409 and "lượt ôn xung đột" in conflict.json()["detail"]
        restored = exported(client)
        assert restored["words"][0]["meaning_vi"] == "chuyện gió kể"
        assert restored["review_logs"][0]["rating"] == 1
        assert client.get("/api/backup/preferences").json() is None


def test_merge_keeps_enriched_metadata_and_reuses_an_opposite_order_pair():
    with backup_client() as (original, original_db), backup_client() as (target, target_db):
        build_history(original_db)
        snapshot = exported(original)
        snapshot["exported_at"] = CREATED.isoformat()
        snapshot["words"][0].update(pinyin="", meaning_vi="", mnemonic_vi="")
        snapshot["sentences"][0]["grammar_pattern_id"] = None

        with Session(target_db) as db, db.begin():
            first = Word(simplified="说", pinyin="shuō", meaning_vi="nói")
            second = Word(simplified="风说", pinyin="fēng shuō", meaning_vi="Nghĩa đã sửa",
                          mnemonic_vi="Ghi chú hiện có.", hsk_level=4)
            pattern = GrammarPattern(pattern_formula="Mẫu hiện có", title_vi="Tên mẫu", explanation_vi="Chú giải")
            db.add_all([first, second, pattern])
            db.flush()
            sentence = Sentence(hanzi=snapshot["sentences"][0]["hanzi"], pinyin="",
                                meaning_vi="Ví dụ", grammar_pattern_id=pattern.id)
            pair = ConfusablePair(
                word_a_id=first.id, word_b_id=second.id, diff_explanation_vi="Đảo thứ tự",
                cloze_a_hanzi="我__。", cloze_a_answer="说", cloze_b_hanzi="__了", cloze_b_answer="风说", hsk_level=1,
            )
            db.add_all([sentence, pair])
            db.flush()
            card = UserCard(item_type="confusable", item_id=pair.id, due=CREATED)
            db.add(card)
            db.flush()
            card_id = card.id
            apply_rating(db, card, RatingRequest(rating=3, drill_mode="confusable", response_ms=130),
                         now=CREATED + timedelta(days=5))

        response = upload(target, snapshot)
        assert response.status_code == 200, response.text
        with Session(target_db) as db:
            restored = db.scalar(select(Word).where(Word.simplified == "风说"))
            assert (restored.pinyin, restored.meaning_vi, restored.mnemonic_vi, restored.hsk_level) == (
                "fēng shuō", "Nghĩa đã sửa", "Ghi chú hiện có.", None,
            )
            sentence = db.scalars(select(Sentence)).one()
            assert db.get(GrammarPattern, sentence.grammar_pattern_id).pattern_formula == "Mẫu hiện có"
            pair = db.scalars(select(ConfusablePair)).one()
            assert (pair.word_a_id, pair.cloze_a_answer, pair.cloze_a_hanzi) == (restored.id, "风说", "__了")
            card = db.scalars(select(UserCard).where(UserCard.item_type == "confusable")).one()
            assert card.id == card_id and card.item_id == pair.id and card.reps == 1
