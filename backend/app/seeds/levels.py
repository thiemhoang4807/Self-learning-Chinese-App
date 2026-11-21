from functools import lru_cache
from pathlib import Path
import re

_HANZI = re.compile(r"[\u3007\u3400-\u9fff\uf900-\ufaff\U00020000-\U000323af]+")


@lru_cache(maxsize=1)
def _syllabus() -> tuple[tuple[str, int], ...]:
    path = Path(__file__).with_name("hsk_levels.txt")
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        level, entries = line.split("|", 1)
        result.extend((entry, int(level)) for entry in entries.split())
    return tuple(result)


@lru_cache(maxsize=1)
def _membership() -> dict[str, int]:
    levels: dict[str, int] = {}
    for entry, level in _syllabus():
        levels.setdefault(entry, level)
        # The syllabus groups connective pairs and disambiguates homographs.
        for word in _HANZI.findall(entry.split("（", 1)[0]):
            levels.setdefault(word, level)
    return levels


def hsk_level_for(text: str) -> int | None:
    """Return the first HSK 2.0 level listing the simplified form."""
    return _membership().get(text.strip())


@lru_cache(maxsize=1)
def _target_levels() -> dict[str, tuple[int, ...]]:
    levels: dict[str, list[int]] = {}
    for entry, level in _syllabus():
        levels.setdefault(entry.split("（", 1)[0], []).append(level)
    return {entry: tuple(values) for entry, values in levels.items()}


def target_levels(text: str) -> tuple[int, ...]:
    return _target_levels().get(text, ())


def compounds_containing(char: str) -> dict[str, int]:
    return {
        entry: levels[0] for entry, levels in _target_levels().items()
        if len(entry) > 1 and char in entry and "…" not in entry
    }
