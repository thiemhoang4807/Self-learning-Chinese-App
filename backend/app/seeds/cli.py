"""Import HSK 2.0 terms from JSON or CSV into the app's existing catalog."""

import argparse
from collections.abc import Iterator, Mapping
import csv
from io import TextIOWrapper
import json
from pathlib import Path
import re
import sys
from typing import Any

from app.db import SessionLocal, lock_catalog
from app.seeds.levels import hsk_level_for
from app.seeds.seed_data import import_words


def value(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if row.get(name) not in (None, "", [], {}):
            return row[name]
    return None


def as_text(item: Any, separator: str = ", ") -> str:
    if isinstance(item, list):
        return separator.join(str(part).strip() for part in item)
    return str(item).strip() if item is not None else ""


def parse_level(raw: Any) -> int | None:
    if isinstance(raw, list):
        parsed = [level for entry in raw if (level := parse_level(entry)) is not None]
        return min(parsed, default=None)
    match = re.fullmatch(r"(?:old[ -]?|hsk\s*[- ]?)?(\d+)", as_text(raw).lower())
    return int(match[1]) if match else None


def json_rows(document: Any, inherited_level: int | None = None) -> Iterator[dict[str, Any]]:
    if isinstance(document, list):
        for row in document:
            if isinstance(row, str):
                yield {"simplified": row, "hsk_level": inherited_level}
            elif isinstance(row, dict):
                yield {"hsk_level": inherited_level, **row} if inherited_level else row
            else:
                raise ValueError("Mỗi mục JSON phải là một từ hoặc một đối tượng từ vựng.")
        return
    if isinstance(document, dict):
        envelope = value(document, "words", "vocabulary", "data", "entries")
        if envelope is not None:
            yield from json_rows(envelope, parse_level(value(document, "hsk_level", "level")) or inherited_level)
            return
        groups = [(parse_level(key), items) for key, items in document.items()]
        if groups and all(level is not None and isinstance(items, list) for level, items in groups):
            for level, items in groups:
                yield from json_rows(items, level)
            return
    raise ValueError("JSON cần là danh sách từ hoặc các nhóm từ theo cấp HSK.")


def rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        if path.suffix.lower() == ".json":
            yield from json_rows(json.load(stream))
        else:
            sample = stream.read(8192)
            stream.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            yield from csv.DictReader(stream, dialect=dialect)


def normalize(row: Mapping[str, Any], fallback_level: int | None, meaning_field: str | None) -> dict | None:
    fields = {str(key).strip().lower(): item for key, item in row.items() if key is not None}
    name = as_text(value(fields, "simplified", "word", "hanzi", "chinese", "词语", "简体", "s", "w"))
    name = name.split("（", 1)[0].strip()
    if not name:
        raise ValueError("Mục từ vựng thiếu chữ Hán giản thể.")
    if len(name) > 100 or not re.search(r"[\u3007\u3400-\u9fff\U00020000-\U000323af]", name):
        raise ValueError(f"Chữ Hán giản thể không hợp lệ: {name!r}.")

    supplied_level = parse_level(value(fields, "hsk_level", "level", "hsk", "等级", "l"))
    level = hsk_level_for(name) or supplied_level or fallback_level
    if level is None or not 1 <= level <= 5:
        return None

    forms = value(fields, "forms", "f")
    form = forms[0] if isinstance(forms, list) and forms and isinstance(forms[0], dict) else {}
    readings = value(form, "transcriptions", "i") or {}
    pinyin = value(fields, "pinyin", "pin_yin", "拼音") or value(readings, "pinyin", "y")
    meaning_keys = [meaning_field] if meaning_field else ["meaning_vi", "vietnamese", "nghĩa", "nghĩa tiếng việt"]
    return {
        "simplified": name,
        "traditional": as_text(value(fields, "traditional", "繁体") or value(form, "traditional", "t")) or None,
        "pinyin": as_text(pinyin, " "),
        "meaning_vi": as_text(value(fields, *meaning_keys)),
        "han_viet": as_text(value(fields, "han_viet", "hán-việt", "âm hán việt")),
        "pos": as_text(value(fields, "pos", "part_of_speech", "词性", "p"), " / "),
        "hsk_level": level,
        "mnemonic_vi": as_text(value(fields, "mnemonic_vi")),
        "usage_note_vi": as_text(value(fields, "usage_note_vi")),
    }


def main() -> None:
    for output in (sys.stdout, sys.stderr):
        if isinstance(output, TextIOWrapper):
            output.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Nhập từ HSK 1–5 từ tệp JSON hoặc CSV.")
    parser.add_argument("input", type=Path, help="Tệp từ vựng UTF-8 dạng JSON hoặc CSV")
    parser.add_argument("--level", type=int, choices=range(1, 6), help="Cấp mặc định nếu mục từ chưa ghi cấp")
    parser.add_argument("--meaning-field", type=str.lower, help="Tên cột hoặc trường chứa nghĩa tiếng Việt")
    args = parser.parse_args()
    if args.input.suffix.lower() not in {".csv", ".json"}:
        parser.error("Chọn tệp .csv hoặc .json.")
    try:
        imported = {}
        for index, row in enumerate(rows(args.input), start=1):
            try:
                record = normalize(row, args.level, args.meaning_field)
            except ValueError as error:
                raise ValueError(f"Mục {index}: {error}") from error
            if record:
                imported.setdefault(record["simplified"], record)
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        parser.error(str(error))
    if not imported:
        parser.error("Tệp không có từ nào thuộc HSK 1–5. Thêm --level nếu tệp chưa có thông tin về cấp độ.")
    with SessionLocal.begin() as session:
        lock_catalog(session)
        import_words(session, imported.values())
    print(f"Đã nhập hoặc đối chiếu {len(imported):,} mục từ HSK 1–5.")


if __name__ == "__main__":
    main()
