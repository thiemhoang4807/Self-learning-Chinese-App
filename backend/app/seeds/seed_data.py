from collections.abc import Iterable, Iterator, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any
import re

import jieba
from pypinyin import lazy_pinyin, Style
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Character, ConfusablePair, GrammarPattern, Sentence, SentenceWord, Word, WordCharacter


def _rows(name: str) -> Iterator[list[str]]:
    for line in Path(__file__).with_name(f"{name}.txt").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            yield line.split("|")


@lru_cache(maxsize=1)
def _character_catalog() -> dict[str, dict[str, Any]]:
    return {
        char: {
            "pinyin": pinyin,
            "han_viet": han_viet,
            "radical": radical,
            "components_json": components.split(";") if ";" in components else components.split(),
            "mnemonic_vi": mnemonic,
        }
        for char, pinyin, han_viet, radical, components, mnemonic in _rows("characters")
    }


def _hanzi_positions(text: str) -> list[tuple[int, str]]:
    return [(match.start(), match[0]) for match in re.finditer(r"[\u3007\u3400-\u9fff\U00020000-\U000323af]", text)]


def _pinyin(text: str) -> str:
    return " ".join(lazy_pinyin(text, style=Style.TONE))


def import_words(session: Session, records: Iterable[Mapping[str, Any]]) -> dict[str, Word]:
    """Populate the catalog, preserving word IDs and all study state."""
    entries = {record["simplified"]: record for record in records}
    if not entries:
        return {}

    catalog = _character_catalog()
    positions = {name: _hanzi_positions(name) for name in entries}
    used_characters: dict[str, int | None] = {}
    for name, locations in positions.items():
        level = entries[name].get("hsk_level")
        for _, char in locations:
            previous = used_characters.get(char)
            if previous is None or (level is not None and level < previous):
                used_characters[char] = level

    characters = {
        row.char: row
        for row in session.scalars(select(Character).where(Character.char.in_(used_characters)))
    }
    for char, level in used_characters.items():
        character = characters.get(char)
        if character is None:
            fields = catalog.get(char) or {"pinyin": _pinyin(char)}
            character = Character(char=char, hsk_level=level, **fields)
            session.add(character)
            characters[char] = character
        elif level is not None and (character.hsk_level is None or level < character.hsk_level):
            character.hsk_level = level

    words = {row.simplified: row for row in session.scalars(select(Word).where(Word.simplified.in_(entries)))}
    for name, record in entries.items():
        word = words.get(name)
        if word is None:
            values = dict(record)
            values["pinyin"] = values.get("pinyin") or _pinyin(name)
            values["meaning_vi"] = values.get("meaning_vi") or ""
            if not values.get("han_viet") and positions[name]:
                readings = [(characters[char].han_viet or "") for _, char in positions[name]]
                if all(readings):
                    values["han_viet"] = " ".join(readings)
            word = Word(**values)
            session.add(word)
            words[name] = word
        else:
            for field, value in record.items():
                if value and not getattr(word, field):
                    setattr(word, field, value)

    session.flush()
    links = set(session.execute(select(WordCharacter.word_id, WordCharacter.position).where(
        WordCharacter.word_id.in_([word.id for word in words.values()]),
    )))
    for name, word in words.items():
        for position, char in positions[name]:
            if (word.id, position) not in links:
                session.add(WordCharacter(word_id=word.id, character_id=characters[char].id, position=position))
    return words


def _seed_patterns(session: Session, words: dict[str, Word]) -> None:
    data = list(_rows("patterns"))
    patterns = {
        row.pattern_formula: row for row in session.scalars(select(GrammarPattern).where(
            GrammarPattern.pattern_formula.in_([row[0] for row in data]),
        ))
    }
    sentences = {
        row.hanzi: row for row in session.scalars(select(Sentence).where(
            Sentence.hanzi.in_([row[5] for row in data]),
        ))
    }
    for formula, level, title, explanation, notes, hanzi, pinyin, meaning in data:
        pattern = patterns.get(formula)
        if pattern is None:
            pattern = GrammarPattern(
                pattern_formula=formula, title_vi=title, explanation_vi=explanation,
                hsk_level=int(level), structure_notes_vi=notes,
            )
            session.add(pattern)
            session.flush()
        sentence = sentences.get(hanzi)
        if sentence is None:
            sentence = Sentence(
                hanzi=hanzi, pinyin=pinyin, meaning_vi=meaning, grammar_pattern_id=pattern.id,
            )
            session.add(sentence)
            session.flush()
        elif sentence.grammar_pattern_id is None:
            sentence.grammar_pattern_id = pattern.id
        linked_ids = set(session.scalars(select(SentenceWord.word_id).where(SentenceWord.sentence_id == sentence.id)))
        for token in set(jieba.cut(hanzi)) & words.keys():
            word_id = words[token].id
            if word_id not in linked_ids:
                session.add(SentenceWord(sentence_id=sentence.id, word_id=word_id))


def _seed_confusables(session: Session, words: dict[str, Word]) -> None:
    existing = {
        frozenset(pair) for pair in session.execute(select(ConfusablePair.word_a_id, ConfusablePair.word_b_id))
    }
    for word_a, word_b, level, explanation, cloze_a, cloze_b in _rows("confusables"):
        a, b = words[word_a], words[word_b]
        if frozenset((a.id, b.id)) in existing:
            continue
        session.add(ConfusablePair(
            word_a_id=a.id, word_b_id=b.id, hsk_level=int(level), diff_explanation_vi=explanation,
            cloze_a_hanzi=cloze_a, cloze_a_answer=word_a, cloze_b_hanzi=cloze_b, cloze_b_answer=word_b,
        ))


def seed_database(session: Session) -> None:
    words = import_words(session, (
        {
            "simplified": simplified, "pinyin": pinyin, "han_viet": reading, "meaning_vi": meaning,
            "pos": part_of_speech, "hsk_level": int(level) or None, "mnemonic_vi": mnemonic,
        }
        for level, simplified, pinyin, reading, part_of_speech, meaning, mnemonic in _rows("vocabulary")
    ))
    _seed_patterns(session, words)
    _seed_confusables(session, words)
