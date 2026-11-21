from functools import lru_cache
from pathlib import Path
import re


@lru_cache(maxsize=1)
def _membership() -> dict[str, int]:
    path = Path(__file__).with_name("hsk_levels.txt")
    levels: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        level, entries = line.split("|", 1)
        for entry in entries.split():
            levels.setdefault(entry, int(level))
            # The syllabus groups connective pairs and disambiguates homographs.
            for word in re.findall(r"[\u3400-\u9fff]+", entry.split("（", 1)[0]):
                levels.setdefault(word, int(level))
    return levels


def hsk_level_for(text: str) -> int | None:
    """Return the first HSK 2.0 level listing the simplified form."""
    return _membership().get(text.strip())
