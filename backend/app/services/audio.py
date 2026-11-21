import asyncio
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from weakref import WeakValueDictionary

import edge_tts
from fastapi import HTTPException

from app.config import settings

_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
_parallel = asyncio.Semaphore(4)


async def audio_file(text: str, voice: str, rate: float) -> Path:
    normalized = " ".join(text.split())
    if not normalized:
        raise HTTPException(422, "Nhập chữ hoặc câu cần phát âm.")
    percent = f"{round((rate - 1) * 100):+d}%"
    key = sha256(repr((normalized, voice, percent)).encode("utf-8")).hexdigest()
    lock = _locks.setdefault(key, asyncio.Lock())
    path = settings.audio_dir / f"{key}.mp3"
    if path.is_file():
        return path
    async with lock:
        if path.is_file():
            return path
        temporary: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
            async with _parallel, asyncio.timeout(30):
                await edge_tts.Communicate(normalized, voice, rate=percent).save(str(temporary))
            if not temporary.stat().st_size:
                raise OSError("Empty speech audio")
            temporary.replace(path)
        except Exception as error:
            raise HTTPException(503, "Chưa tải được giọng đọc. Bạn có thể tiếp tục học và thử lại sau.") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return path
