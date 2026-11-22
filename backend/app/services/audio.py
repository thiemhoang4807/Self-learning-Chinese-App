import asyncio
from contextlib import suppress
from hashlib import sha256
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from weakref import WeakValueDictionary

import edge_tts
from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)
TTS_TIMEOUT_SECONDS = 10
_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
_parallel = asyncio.Semaphore(4)


class SpeechUnavailable(Exception):
    pass


def cached_audio_count() -> int | None:
    try:
        if not settings.audio_dir.exists():
            return 0
        return sum(file.is_file() and file.suffix == ".mp3" for file in settings.audio_dir.iterdir())
    except OSError:
        logger.warning("Could not read TTS cache directory")
        return None


async def _generate(text: str, voice: str, percent: str, path: Path, lock: asyncio.Lock) -> None:
    async with lock:
        if path.is_file() and path.stat().st_size:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
        try:
            async with _parallel:
                await edge_tts.Communicate(text, voice, rate=percent).save(str(temporary))
            if not temporary.stat().st_size:
                raise OSError("Empty speech audio")
            temporary.replace(path)
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


async def audio_file(text: str, voice: str, rate: float) -> Path:
    normalized = " ".join(text.split())
    if not normalized:
        raise HTTPException(422, "Nhập chữ hoặc câu cần phát âm.")
    percent = f"{round((rate - 1) * 100):+d}%"
    key = sha256(repr((normalized, voice, percent)).encode("utf-8")).hexdigest()
    path = settings.audio_dir / f"{key}.mp3"
    try:
        if not (path.is_file() and path.stat().st_size):
            lock = _locks.setdefault(key, asyncio.Lock())
            async with asyncio.timeout(TTS_TIMEOUT_SECONDS):
                await _generate(normalized, voice, percent, path, lock)
    except Exception as error:
        logger.warning("TTS generation failed: %s", type(error).__name__)
        raise SpeechUnavailable from error
    return path
