from datetime import date, datetime, timedelta, timezone

import pytest
from fsrs import Card, Rating, State
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.library import character_tree
from app.db import Base
from app.models import ReviewLog, Source, SourceWord, UserCard, Word
from app.schemas.study import RatingRequest
from app.seeds.levels import compounds_containing
from app.services.analytics import dashboard
from app.services.library import segment_text
from app.services.study import apply_rating, as_utc

NOW = datetime(2026, 11, 22, 18, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_fsrs_transitions_persist_and_four_review_lapses_flag_leech(db):
    word = Word(simplified="经验", pinyin="jīngyàn", meaning_vi="kinh nghiệm", hsk_level=4)
    db.add(word)
    db.flush()
    card = UserCard(item_type="word", item_id=word.id, due=NOW)
    db.add(card)
    db.flush()
    card_id = card.id

    def rate(value, number):
        due = as_utc(card.due)
        apply_rating(db, card, RatingRequest(
            rating=value, drill_mode="flashcard", response_ms=320,
            review_token=f"experience-{number}",
        ), now=due)
        assert card.due > due

    rate(Rating.Good, 1)
    assert card.status == "learning"
    assert Card.from_dict(card.fsrs_state_json).state == State.Learning

    rate(Rating.Good, 2)
    assert card.status == "review"
    assert Card.from_dict(card.fsrs_state_json).state == State.Review

    for lapse in range(1, 5):
        rate(Rating.Again, lapse * 2 + 1)
        assert card.lapses == lapse
        assert card.wrong_count == lapse
        assert card.status == "learning"
        assert card.is_leech is (lapse == 4)
        if lapse < 4:
            rate(Rating.Good, lapse * 2 + 2)

    db.commit()
    db.expire_all()
    saved = db.get(UserCard, card_id)
    fsrs = Card.from_dict(saved.fsrs_state_json)
    assert fsrs.due == as_utc(saved.due)
    assert fsrs.state == State.Relearning
    assert (saved.reps, saved.lapses, saved.wrong_count, saved.is_leech) == (9, 4, 4, True)
    logs = db.scalars(select(ReviewLog).where(ReviewLog.card_id == card_id).order_by(ReviewLog.id)).all()
    assert [entry.rating for entry in logs] == [3, 3, 1, 3, 1, 3, 1, 3, 1]
    assert all(entry.drill_mode == "flashcard" and entry.response_ms == 320 for entry in logs)
    assert as_utc(logs[0].reviewed_at) == NOW
    assert as_utc(logs[-1].reviewed_at) == fsrs.last_review


def test_reader_segments_full_text_and_attaches_known_study_status(db):
    studying = Word(simplified="学习", traditional="學習", pinyin="xuéxí", meaning_vi="học tập", hsk_level=1)
    mastered = Word(simplified="汉语", traditional="漢語", pinyin="Hànyǔ", meaning_vi="tiếng Trung", hsk_level=1)
    db.add_all([studying, mastered])
    db.flush()
    db.add_all([
        UserCard(item_type="word", item_id=studying.id, status="learning"),
        UserCard(item_type="word", item_id=mastered.id, status="mastered"),
    ])

    paragraph = "今天学习汉语。\n我喜欢熊猫！"
    tokens = segment_text(db, paragraph)
    assert "".join(token.text for token in tokens) == paragraph
    by_text = {token.text: token.word for token in tokens}
    assert by_text["学习"].id == studying.id
    assert by_text["学习"].status == "learning"
    assert by_text["汉语"].pinyin == "Hànyǔ"
    assert by_text["汉语"].status == "mastered"
    assert by_text["熊猫"] is None
    assert by_text["。"] is None


def test_coverage_and_rolling_pace_use_distinct_words(db):
    frequent = Word(simplified="经验", pinyin="jīngyàn", meaning_vi="kinh nghiệm", hsk_level=4)
    earlier = Word(simplified="感受", pinyin="gǎnshòu", meaning_vi="cảm nhận", hsk_level=5)
    extension = Word(simplified="必需", pinyin="bìxū", meaning_vi="thiết yếu")
    slides = [Source(title=title, source_type="pptx") for title in ("Bài 1", "Bài 2")]
    db.add_all([frequent, earlier, extension, *slides])
    db.flush()
    db.add_all(SourceWord(source_id=source.id, word_id=frequent.id) for source in slides)
    db.add(SourceWord(source_id=slides[0].id, word_id=extension.id))

    recent_card = UserCard(item_type="word", item_id=frequent.id, status="mastered")
    earlier_card = UserCard(item_type="word", item_id=earlier.id, status="learning", is_leech=True, wrong_count=6)
    extension_card = UserCard(item_type="word", item_id=extension.id, status="ignored", is_leech=True, wrong_count=9)
    pattern_card = UserCard(item_type="pattern", item_id=earlier.id, status="mastered")
    db.add_all([recent_card, earlier_card, extension_card, pattern_card])
    db.flush()
    db.add_all(ReviewLog(
        card_id=card.id, rating=rating, drill_mode="flashcard", response_ms=250,
        reviewed_at=NOW - timedelta(days=days_ago),
    ) for card, rating, days_ago in [
        (recent_card, 1, 10), (recent_card, 3, 3), (recent_card, 4, 1),
        (earlier_card, 3, 8), (earlier_card, 3, 1), (extension_card, 4, 1), (pattern_card, 4, 2),
    ])

    result = dashboard(db, now=NOW)
    levels = {row.level: row for row in result.levels}
    assert [row.total for row in result.levels] == [150, 150, 300, 600, 1300]
    assert (levels[4].mastered, levels[4].ingested, levels[4].available) == (1, 1, 1)
    assert (levels[5].mastered, levels[5].ingested, levels[5].available) == (0, 0, 1)
    assert result.pace.words_per_day == 0.14
    assert result.pace.remaining == 2498
    assert result.pace.projected_date == date(2026, 11, 23) + timedelta(days=2498 * 7)
    assert [(word.word_id, word.wrong_count) for word in result.leeches] == [(earlier.id, 6)]


def test_new_dashboard_has_no_projection_without_review_activity(db):
    result = dashboard(db, now=NOW)
    assert result.pace.words_per_day == 0
    assert result.pace.remaining == 2500
    assert result.pace.projected_date is None
    assert result.leeches == []


def test_character_tree_includes_unimported_official_compounds_without_queuing_them(db, monkeypatch):
    from pydantic import SecretStr

    from app.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", SecretStr(""))
    expected = compounds_containing("情")
    result = character_tree("情", db)
    assert "事情" in expected
    assert result.character.char == "情"
    assert {word.simplified: word.hsk_level for word in result.words} == expected
    assert not list(db.scalars(select(UserCard)))
    assert [(word.id, word.simplified) for word in character_tree("情", db).words] == [
        (word.id, word.simplified) for word in result.words
    ]


def test_homograph_covers_its_syllabus_entries_with_one_card(db):
    word = Word(simplified="长", pinyin="cháng", meaning_vi="dài", hsk_level=2)
    db.add(word)
    db.flush()
    card = UserCard(item_type="word", item_id=word.id, status="mastered")
    db.add(card)
    db.flush()
    db.add(ReviewLog(card_id=card.id, rating=3, drill_mode="flashcard", response_ms=600, reviewed_at=NOW))
    result = dashboard(db, now=NOW)
    assert [level.mastered for level in result.levels] == [0, 1, 1, 0, 0]
    assert result.pace.remaining == 2498
    assert result.pace.words_per_day == 0.14
