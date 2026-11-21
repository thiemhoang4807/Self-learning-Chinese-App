import io
import json
from types import SimpleNamespace

import pymupdf
import pytest
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import ai as ai_api
from app.api import ingestion as ingestion_api
from app.config import settings
from app.db import Base, get_db
from app.models import Character, Sentence, SentenceWord, SourceWord, StoryAttempt, UserCard, Word
from app.services import ai

EXTRACTION = {
    "summary_note": "Luyện từ chỉ trái cây.",
    "words": [{
        "simplified": "苹果",
        "pinyin": "píngguǒ",
        "han_viet": "bình quả",
        "meaning_vi": "quả táo",
        "pos": "danh từ",
        "hsk_level": 5,
        "characters": [{
            "char": "果", "pinyin": "guǒ", "han_viet": "quả", "radical": "木",
            "components": ["田", "木"], "mnemonic_vi": "Trên cây có quả.",
        }],
    }],
    "grammar_patterns": [{
        "pattern_formula": "S + 有 + O",
        "title_vi": "Có một vật",
        "explanation_vi": "Đặt 有 trước vật đang có.",
        "hsk_level": 1,
    }],
    "sentences": [{
        "hanzi": "我有苹果。",
        "pinyin": "Wǒ yǒu píngguǒ.",
        "meaning_vi": "Tôi có táo.",
        "pattern_formula": "S + 有 + O",
    }],
}


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(ingestion_api.router, prefix="/api")
    app.include_router(ai_api.router, prefix="/api")

    def test_db():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as test:
        yield test, engine
    engine.dispose()


@pytest.fixture
def gemini(monkeypatch):
    def fake(*payloads):
        calls = []
        responses = iter(payloads)

        class Client:
            def __init__(self, **_):
                self.models = self

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def generate_content(self, **request):
                calls.append(request)
                return SimpleNamespace(text=json.dumps(next(responses), ensure_ascii=False))

        monkeypatch.setattr(settings, "gemini_api_key", SecretStr("pytest-only"))
        monkeypatch.setattr(ai.genai, "Client", Client)
        return calls

    return fake


def test_parse_paste_and_save_twice_preserves_card(api, gemini):
    client, engine = api
    calls = gemini(EXTRACTION, EXTRACTION)
    first = client.post("/api/ingestion/extract", data={"text": "我有苹果。"})
    assert first.status_code == 200, first.text
    material = first.json()
    assert material["source_type"] == "paste"
    assert material["words"][0]["hsk_level"] == 1
    assert material["words"][0]["existing"] is False
    schema = calls[0]["config"].response_json_schema
    assert schema["type"] == "object"
    assert "maxItems" not in json.dumps(schema)
    assert schema["$defs"]["ExtractedWord"]["properties"]["characters"]["type"] == "array"
    assert calls[0]["contents"][1].text == "我有苹果。"
    assert client.post("/api/ingestion/save", json=material).status_code == 201

    with Session(engine) as db:
        card = db.scalars(select(UserCard).where(UserCard.item_type == "word")).one()
        card.status = "review"
        card.reps = 7
        card.lapses = 2
        db.commit()

    second = client.post("/api/ingestion/extract", data={"text": "Tài liệu B: 苹果"})
    assert second.status_code == 200
    next_material = second.json()
    assert all(
        next_material[key][0]["existing"] for key in ("words", "grammar_patterns", "sentences")
    )
    next_material["title"] = "Tài liệu B"
    next_material["words"][0]["meaning_vi"] = "Phiên bản khác"
    assert client.post("/api/ingestion/save", json=next_material).status_code == 201

    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Word)) == 1
        assert db.scalar(select(func.count()).select_from(Character)) == 2
        assert db.scalar(select(func.count()).select_from(SourceWord)) == 2
        assert db.scalar(select(func.count()).select_from(SentenceWord)) == 1
        card = db.scalars(select(UserCard).where(UserCard.item_type == "word")).one()
        assert (card.status, card.reps, card.lapses) == ("review", 7, 2)
        assert db.scalars(select(Word)).one().meaning_vi == "quả táo"
    sources = client.get("/api/ingestion/sources").json()
    assert len(sources) == 2
    assert sources[0]["title"] == "Tài liệu B"
    assert all(source["word_count"] == source["pattern_count"] == source["sentence_count"] == 1 for source in sources)


def test_docx_passes_paragraph_and_table_text_to_gemini(api, gemini):
    client, _ = api
    calls = gemini(EXTRACTION)
    document = Document()
    document.add_paragraph("我有苹果。")
    document.add_table(rows=1, cols=1).cell(0, 0).text = "quả táo"
    content = io.BytesIO()
    document.save(content)
    response = client.post("/api/ingestion/extract", files={"file": ("bai.docx", content.getvalue())})
    assert response.status_code == 200, response.text
    assert response.json()["source_type"] == "docx"
    assert calls[0]["contents"][1].text == "我有苹果。\nquả táo\n"


def test_pdf_renders_limited_pages_into_visual_request(api, gemini, monkeypatch):
    client, _ = api
    calls = gemini(EXTRACTION)
    monkeypatch.setattr(settings, "max_visual_pages", 2)
    with pymupdf.open() as doc:
        for _ in range(3):
            doc.new_page(width=60, height=80)
        content = doc.tobytes()
    response = client.post("/api/ingestion/extract", files={"file": ("slide.pdf", content)})
    assert response.status_code == 200, response.text
    assert "2 trang đầu" in response.json()["notice_vi"]
    images = calls[0]["contents"][1:]
    assert len(images) == 2
    for img in images:
        assert img.inline_data.mime_type == "image/png"
        with Image.open(io.BytesIO(img.inline_data.data)) as png:
            assert png.size == (120, 160)


def test_missing_key_and_invalid_payload_are_localized(api, gemini, monkeypatch):
    client, _ = api
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr(""))
    missing = client.post("/api/ingestion/extract", data={"text": "苹果"})
    assert missing.status_code == 503 and "GEMINI_API_KEY" in missing.json()["detail"]
    gemini({"words": []})
    invalid = client.post("/api/ingestion/extract", data={"text": "苹果"})
    assert invalid.status_code == 502 and "định dạng" in invalid.json()["detail"]


def test_reverse_translation_uses_stored_reference_and_validates_score(api, gemini):
    client, engine = api
    with Session(engine) as db:
        sentence = Sentence(hanzi="我有苹果。", pinyin="Wǒ yǒu píngguǒ.", meaning_vi="Tôi có táo.")
        db.add(sentence)
        db.flush()
        sentence_id = sentence.id
        db.commit()
    grade = {
        "score": 80,
        "feedback_vi": "Thêm động từ sở hữu.",
        "corrections": [{"original": "我苹果", "correction": "我有苹果", "explanation_vi": "Dùng 有 để nói sở hữu."}],
        "corrected_hanzi": "我有苹果。",
    }
    calls = gemini(grade, {**grade, "score": 101})
    body = {"sentence_id": sentence_id, "answer": "我苹果。"}
    response = client.post("/api/ai/reverse-translation", json=body)
    assert response.status_code == 200
    assert response.json() == grade
    prompt = json.loads(calls[0]["contents"][1].text)
    assert prompt["prompt_vi"] == "Tôi có táo." and prompt["reference_hanzi"] == "我有苹果。"
    assert client.post("/api/ai/reverse-translation", json=body).status_code == 502


def test_examples_use_known_words_and_store_only_valid_new_sentences(api, gemini):
    client, engine = api
    with Session(engine) as db:
        words = [Word(simplified=word, pinyin="pinyin", meaning_vi="nghĩa", hsk_level=1) for word in
                 ("我", "喜欢", "爱", "苹果")]
        db.add_all(words)
        db.flush()
        for word in words[:3]:
            db.add(UserCard(item_type="word", item_id=word.id, status="review"))
        target_id = words[-1].id
        db.commit()

    calls = gemini({"sentences": [
        {"hanzi": "我喜欢苹果。", "pinyin": "Wǒ xǐhuan píngguǒ.", "meaning_vi": "Tôi thích táo."},
        {"hanzi": "我爱苹果。", "pinyin": "Wǒ ài píngguǒ.", "meaning_vi": "Tôi mê táo."},
        {"hanzi": "我喜欢北京苹果。", "pinyin": "Wǒ xǐhuan Běijīng píngguǒ.", "meaning_vi": "Tôi thích táo Bắc Kinh."},
    ]})
    response = client.post("/api/ai/examples", json={"item_type": "word", "item_id": target_id})
    assert response.status_code == 200, response.text
    assert [row["hanzi"] for row in response.json()["sentences"]] == ["我喜欢苹果。", "我爱苹果。"]
    assert all(row["is_ai_generated"] for row in response.json()["sentences"])
    assert set(json.loads(calls[0]["contents"][1].text)["known_words"]) == {"我", "喜欢", "爱"}
    with Session(engine) as db:
        assert len(list(db.scalars(select(SentenceWord).where(SentenceWord.word_id == target_id)))) == 2


def test_story_grade_records_five_words_and_caps_score_for_omission(api, gemini):
    client, engine = api
    words = ["经历", "经验", "讨论", "计划", "坚持"]
    with Session(engine) as db:
        db.add_all(Word(simplified=word, pinyin="pinyin", meaning_vi="nghĩa", hsk_level=4) for word in words)
        db.commit()
    assert set(client.get("/api/ai/story/words").json()["words"]) == set(words)
    gemini({
        "score": 96,
        "usage": [{"word": word, "correct": True, "feedback_vi": "Dùng đúng."} for word in reversed(words)],
        "grammar_vi": "Các vế đã có liên kết.",
        "naturalness_vi": "Có thể thêm ngữ cảnh cho câu cuối.",
        "rewrite_hanzi": "这段经历让我积累了经验。我们讨论计划，也会坚持下去。",
    })
    text = "这段经历让我积累了经验。我们讨论了计划。"
    response = client.post("/api/ai/story", json={"target_words": words, "text": text})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["score"] == 90
    assert [item["word"] for item in result["feedback"]["usage"]] == words
    assert result["feedback"]["usage"][-1]["correct"] is False
    assert client.get("/api/ai/story").json() == [result]
    with Session(engine) as db:
        assert db.scalars(select(StoryAttempt)).one().text == text


def test_tabular_uploads_extract_rows_with_unicode(api, gemini):
    client, _ = api
    calls = gemini(EXTRACTION, EXTRACTION)
    workbook = Workbook()
    workbook.active.title = "Từ vựng"
    workbook.active.append(["苹果", "quả táo"])
    workbook_data = io.BytesIO()
    workbook.save(workbook_data)
    response = client.post("/api/ingestion/extract", files={"file": ("tu-vung.xlsx", workbook_data.getvalue())})
    assert response.status_code == 200, response.text
    assert "苹果\tquả táo" in calls[0]["contents"][1].text

    response = client.post(
        "/api/ingestion/extract",
        files={"file": ("tu-vung.csv", '苹果;"quả táo, trái táo"\n'.encode("utf-16"))},
    )
    assert response.status_code == 200, response.text
    assert "苹果\tquả táo, trái táo" in calls[1]["contents"][1].text


def test_generated_confusable_reuses_pair_in_reverse_order(api, gemini):
    client, engine = api
    with Session(engine) as db:
        words = [
            Word(simplified="经历", pinyin="jīnglì", meaning_vi="trải qua", hsk_level=4),
            Word(simplified="经验", pinyin="jīngyàn", meaning_vi="kinh nghiệm", hsk_level=4),
        ]
        db.add_all(words)
        db.flush()
        first, second = [word.id for word in words]
        db.commit()

    calls = gemini({
        "diff_explanation_vi": "经历 là trải qua. 经验 là kỹ năng tích lũy từ thực tế.",
        "cloze_a_hanzi": "他去年___了一场事故。",
        "cloze_b_hanzi": "这份工作要求三年的教学___。",
    })
    response = client.post("/api/ai/confusables", json={"word_a_id": first, "word_b_id": second})
    assert response.status_code == 200, response.text
    pair = response.json()
    assert (pair["word_a"], pair["word_b"]) == ("经历", "经验")
    reverse = client.post("/api/ai/confusables", json={"word_a_id": second, "word_b_id": first})
    assert reverse.json() == pair
    assert len(calls) == 1
    assert client.get("/api/ai/confusables").json() == [pair]


def test_resaving_sentence_fills_a_missing_pattern_link(api):
    client, engine = api
    sentence = dict(EXTRACTION["sentences"][0])
    initial = {
        "title": "Câu riêng",
        "source_type": "paste",
        "words": [],
        "grammar_patterns": [],
        "sentences": [dict(sentence, pattern_formula=None)],
    }
    assert client.post("/api/ingestion/save", json=initial).status_code == 201
    with Session(engine) as db:
        assert db.scalars(select(Sentence)).one().grammar_pattern_id is None

    second = {
        **initial,
        "title": "Câu kèm mẫu",
        "grammar_patterns": EXTRACTION["grammar_patterns"],
        "sentences": [sentence],
    }
    assert client.post("/api/ingestion/save", json=second).status_code == 201
    with Session(engine) as db:
        retained = db.scalars(select(Sentence)).one()
        assert retained.grammar_pattern_id is not None
