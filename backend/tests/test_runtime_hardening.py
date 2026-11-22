import asyncio
import io
from pathlib import Path
from types import SimpleNamespace

import httpx
import pymupdf
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.genai import errors
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import health, ingestion as intake, library
from app.config import settings
from app.db import Base, get_db
from app.models import ReviewLog, UserCard, Word
from app.schemas.ingestion import ExtractedMaterial, ExtractedWord
from app.seeds.levels import catalog_entries
from app.seeds.seed_data import seed_database
from app.services import ai, audio, ingestion


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "audio_dir", tmp_path / "audio")
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr(""))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    app = FastAPI()
    for module in (health, intake, library):
        app.include_router(module.router, prefix="/api")

    def database():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, engine
    engine.dispose()


def test_audio_timeout_requests_web_speech_and_removes_partial_cache(app_client, monkeypatch):
    client, _ = app_client
    monkeypatch.setattr(audio, "TTS_TIMEOUT_SECONDS", 0.01)

    class OfflineVoice:
        def __init__(self, *_args, **_kwargs):
            pass

        async def save(self, path):
            Path(path).write_bytes(b"partial data")
            await asyncio.sleep(0.1)

    monkeypatch.setattr(audio.edge_tts, "Communicate", OfflineVoice)
    response = client.get("/api/audio/tts", params={"text": "你好"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Không thể tạo âm thanh lúc này", "fallback": "web_speech"}
    assert response.headers["cache-control"] == "no-store"
    assert list(settings.audio_dir.iterdir()) == []


def test_cached_mp3_and_etag_work_without_edge_tts(app_client, monkeypatch):
    client, _ = app_client
    calls = []

    class Voice:
        def __init__(self, text, voice, rate):
            calls.append((text, voice, rate))

        async def save(self, path):
            Path(path).write_bytes(b"ID3 test audio")

    monkeypatch.setattr(audio.edge_tts, "Communicate", Voice)
    params = {"text": "你好", "rate": 1.2}
    first = client.get("/api/audio/tts", params=params)
    assert first.status_code == 200 and first.content == b"ID3 test audio"

    def fail(*_args, **_kwargs):
        pytest.fail("A cached file should avoid another Edge TTS request")

    monkeypatch.setattr(audio.edge_tts, "Communicate", fail)
    cached = client.get("/api/audio/tts", params=params, headers={"If-None-Match": first.headers["etag"]})
    assert cached.status_code == 304 and not cached.content
    assert calls == [("你好", "zh-CN-XiaoxiaoNeural", "+20%")]
    assert client.get("/api/health").json()["tts_cache_count"] == 1


def test_large_pdf_batches_are_bounded_and_merged(app_client, monkeypatch):
    client, _ = app_client
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-only"))
    calls = []

    def extract(batch):
        for png in batch:
            with Image.open(io.BytesIO(png)) as image:
                assert max(image.size) <= 1600
        terms = [ExtractedWord(simplified="汉语", meaning_vi="tiếng Trung")]
        if not calls:
            terms.append(ExtractedWord(simplified="学习", meaning_vi="học tập"))
        if len(calls) == 8:
            terms.append(ExtractedWord(simplified="书", meaning_vi="sách"))
        calls.append(len(batch))
        return ExtractedMaterial(summary_note="Từ vựng trong tài liệu.", words=terms, grammar_patterns=[], sentences=[])

    monkeypatch.setattr(ai, "extract_images", extract)
    with pymupdf.open() as document:
        for _ in range(33):
            document.new_page(width=2831, height=1234)
        payload = document.tobytes()
    response = client.post("/api/ingestion/extract", files={"file": ("bai-hoc.pdf", payload, "application/pdf")})
    assert response.status_code == 200, response.text
    assert calls == [4] * 8 + [1]
    assert [word["simplified"] for word in response.json()["words"]] == ["汉语", "学习", "书"]
    assert response.json()["notice_vi"] is None


def test_office_conversions_use_independent_profiles(monkeypatch, tmp_path):
    profiles = []
    monkeypatch.setattr(ingestion.shutil, "which", lambda _binary: "libreoffice")
    monkeypatch.setattr(ingestion.tempfile, "tempdir", str(tmp_path))

    def convert(arguments, *, cwd, timeout, **_kwargs):
        assert "--headless" in arguments and timeout > 0
        profiles.append(arguments[1])
        (cwd / "document.pdf").write_bytes(b"%PDF-test")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ingestion.subprocess, "run", convert)
    assert ingestion._office_pdf(b"presentation", ".pptx") == b"%PDF-test"
    assert ingestion._office_pdf(b"document", ".doc") == b"%PDF-test"
    assert all(profile.startswith("-env:UserInstallation=file:") and profile.endswith("/lo_profile") for profile in profiles)
    assert profiles[0] != profiles[1]


def test_full_hsk_seed_and_health_preserve_existing_study(app_client):
    client, engine = app_client
    with Session(engine) as db:
        seed_database(db)
        word = db.scalar(select(Word).where(Word.simplified == "爱"))
        word.meaning_vi = "Nghĩa đã sửa"
        word.hsk_level = None
        card = UserCard(item_type="word", item_id=word.id, status="ignored", reps=1)
        db.add(card)
        db.flush()
        db.add(ReviewLog(card_id=card.id, rating=3, drill_mode="flashcard", response_ms=300))
        db.commit()
        seed_database(db, full_hsk=True)
        seed_database(db, full_hsk=True)
        db.commit()
        assert word.meaning_vi == "Nghĩa đã sửa" and word.hsk_level is None
        assert card.status == "ignored" and card.reps == 1
        assert db.scalar(select(func.count()).select_from(ReviewLog)) == 1
        lexical_count = db.scalar(select(func.count()).select_from(Word).where(Word.hsk_level.is_not(None)))
        assert set(dict(catalog_entries())) <= set(db.scalars(select(Word.simplified)))
    result = client.get("/api/health")
    assert result.status_code == 200
    assert result.json() == {"status": "ok", "database": "ok", "hsk_word_count": lexical_count,
                             "tts_cache_count": 0, "gemini_configured": False, "gemini_model": settings.gemini_model}


@pytest.mark.parametrize(("error", "status", "message"), [
    (errors.ClientError(401, {}), 502, "kiểm tra khóa API"),
    (errors.ClientError(403, {}), 502, "kiểm tra khóa API"),
    (errors.ClientError(400, {"error": {"details": [{"reason": "API_KEY_INVALID"}]}}), 502, "kiểm tra khóa API"),
    (errors.ClientError(429, {}), 503, "hết hạn mức"),
    (httpx.ReadTimeout("test timeout"), 504, "phản hồi quá lâu"),
])
def test_gemini_errors_are_actionable_and_readiness_has_a_short_timeout(app_client, monkeypatch, error, status, message):
    client, _ = app_client
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-only"))

    class UnavailableGemini:
        def __init__(self, *, http_options, **_kwargs):
            assert http_options.timeout == 8000
            assert http_options.retry_options.attempts == 1
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, *, model):
            assert model == settings.gemini_model
            raise error

    monkeypatch.setattr(ai.genai, "Client", UnavailableGemini)
    response = client.post("/api/health/gemini")
    assert response.status_code == status
    assert message in response.json()["detail"]
    assert "test-only" not in response.text


def test_compose_persists_both_volumes_and_installs_cjk_font_support():
    repo = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((repo / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert "postgres_data:/var/lib/postgresql/data" in services["postgres"]["volumes"]
    assert "audio_data:/app/data/audio" in services["backend"]["volumes"]
    assert set(compose["volumes"]) >= {"postgres_data", "audio_data"}
    assert "pg_isready" in " ".join(services["postgres"]["healthcheck"]["test"])
    assert services["backend"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["frontend"]["ports"][0]["host_ip"] == "${WEB_BIND_HOST:-0.0.0.0}"
    dockerfile = (repo / "backend" / "Dockerfile").read_text(encoding="utf-8")
    for package in ("libreoffice-impress", "libreoffice-writer", "libreoffice-common", "fontconfig", "fonts-noto-cjk"):
        assert package in dockerfile
    assert "fc-cache -fv" in dockerfile and "alembic upgrade head" in dockerfile
