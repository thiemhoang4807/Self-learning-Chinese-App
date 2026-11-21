from collections import defaultdict
from datetime import datetime, timezone
from random import Random
import re

import jieba
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Character, ConfusablePair, GrammarPattern, Sentence, SentenceWord, SourcePattern,
    SourceSentence, SourceWord, UserCard, Word, WordCharacter,
)
from app.schemas.study import CharacterView, DrillCard, SentenceView, SessionMode
from app.services.library import pinyin
from app.services.study import as_utc, enqueue_many

ITEM_MODELS = {"word": Word, "pattern": GrammarPattern, "confusable": ConfusablePair}


def _catalog(db: Session, mode: SessionMode, source_id: int | None, level: int | None):
    full = {}
    if mode in {"mixed", "flashcard", "listening", "cloze"}:
        query = select(Word)
        if source_id is not None:
            query = query.where(or_(
                select(SourceWord).where(SourceWord.word_id == Word.id, SourceWord.source_id == source_id).exists(),
                select(SentenceWord).join(SourceSentence, SourceSentence.sentence_id == SentenceWord.sentence_id)
                .where(SentenceWord.word_id == Word.id, SourceSentence.source_id == source_id).exists(),
            ))
        if mode == "cloze":
            query = query.where(select(SentenceWord).where(SentenceWord.word_id == Word.id).exists())
        if level is not None:
            query = query.where(Word.hsk_level == level)
        elif source_id is None:
            # Imported extension words enter the daily queue through explicit enrollment.
            query = query.where(or_(Word.hsk_level.is_not(None), select(UserCard).where(
                UserCard.item_type == "word", UserCard.item_id == Word.id,
            ).exists()))
        full.update({("word", word.id): word for word in db.scalars(query)})
    if mode in {"mixed", "reorder", "reverse"}:
        query = select(GrammarPattern)
        if mode != "mixed":
            query = query.where(select(Sentence).where(Sentence.grammar_pattern_id == GrammarPattern.id).exists())
        if source_id is not None:
            query = query.where(or_(
                select(SourcePattern).where(
                    SourcePattern.pattern_id == GrammarPattern.id, SourcePattern.source_id == source_id,
                ).exists(),
                select(Sentence).join(SourceSentence, SourceSentence.sentence_id == Sentence.id)
                .where(Sentence.grammar_pattern_id == GrammarPattern.id, SourceSentence.source_id == source_id).exists(),
            ))
        if level is not None:
            query = query.where(GrammarPattern.hsk_level == level)
        full.update({("pattern", row.id): row for row in db.scalars(query)})
    if source_id is None and mode in {"mixed", "confusable"}:
        query = select(ConfusablePair)
        if level is not None:
            query = query.where(ConfusablePair.hsk_level == level)
        if mode == "mixed":
            query = query.where(select(UserCard).where(
                UserCard.item_type == "confusable", UserCard.item_id == ConfusablePair.id,
            ).exists())
        full.update({("confusable", row.id): row for row in db.scalars(query)})
    return full


def _terms(db: Session, word_ids: list[int]) -> dict[int, list[CharacterView]]:
    result = defaultdict(list)
    rows = db.execute(select(WordCharacter.word_id, Character)
        .join(Character, Character.id == WordCharacter.character_id)
        .where(WordCharacter.word_id.in_(word_ids)).order_by(WordCharacter.position))
    for word_id, row in rows:
        result[word_id].append(CharacterView.model_validate(row))
    return result


def _sentences(db: Session, word_ids: list[int], pattern_ids: list[int]):
    by_key = defaultdict(list)
    words = db.execute(select(SentenceWord.word_id, Sentence)
        .join(Sentence, Sentence.id == SentenceWord.sentence_id)
        .where(SentenceWord.word_id.in_(word_ids)).order_by(Sentence.id.desc()))
    for word_id, sentence in words:
        if len(by_key["word", word_id]) < 6:
            by_key["word", word_id].append(SentenceView.model_validate(sentence))
    patterns = db.scalars(select(Sentence).where(Sentence.grammar_pattern_id.in_(pattern_ids))
        .order_by(Sentence.id.desc()))
    for sentence in patterns:
        key = ("pattern", sentence.grammar_pattern_id)
        if len(by_key[key]) < 6:
            by_key[key].append(SentenceView.model_validate(sentence))
    return by_key


def _choices(db: Session, word: Word, random: Random) -> list[str]:
    options = [word.simplified]
    paired = db.scalars(select(ConfusablePair).where(or_(
        ConfusablePair.word_a_id == word.id, ConfusablePair.word_b_id == word.id,
    )).order_by(ConfusablePair.id))
    alternatives = [row.word_b_id if row.word_a_id == word.id else row.word_a_id for row in paired]
    options.extend(db.scalars(select(Word.simplified).where(Word.id.in_(alternatives)).limit(3)))
    if len(options) < 4:
        candidates = db.scalars(select(Word.simplified).where(
            Word.hsk_level == word.hsk_level, Word.simplified.not_in(options),
        ).order_by(Word.id).limit(50)).all()
        options.extend(random.sample(candidates, k=min(4 - len(options), len(candidates))))
    if len(options) < 4:
        options.extend(db.scalars(select(Word.simplified).where(Word.simplified.not_in(options))
            .order_by(Word.hsk_level.nulls_last(), Word.id).limit(4 - len(options))))
    random.shuffle(options)
    return options


def _word_drill(db: Session, item, mode, sentences, characters, random: Random) -> DrillCard:
    card = DrillCard(
        item_type="word", item_id=item.id, mode=mode,
        hanzi=item.simplified, pinyin=item.pinyin, han_viet=item.han_viet,
        meaning_vi=item.meaning_vi, mnemonic_vi=item.mnemonic_vi, usage_note_vi=item.usage_note_vi,
        audio_text=item.simplified, characters=characters, sentences=sentences, answer=item.simplified,
    )
    if mode == "cloze":
        context = next((row for row in sentences if item.simplified in row.hanzi), None)
        if context is None:
            card.mode = "flashcard"
        else:
            card.sentence_id = context.id
            card.prompt = context.hanzi.replace(item.simplified, "＿＿", 1)
            card.hanzi = context.hanzi
            card.pinyin = context.pinyin
            card.audio_text = context.hanzi
            card.choices = _choices(db, item, random)
    return card


def _pattern_drill(item, mode, sentences, random: Random) -> DrillCard:
    if not sentences:
        return DrillCard(item_type="pattern", item_id=item.id, mode="flashcard", hanzi=item.pattern_formula,
                         meaning_vi=item.explanation_vi, grammar_hint=item.pattern_formula,
                         usage_note_vi=item.structure_notes_vi)
    sentence = sentences[0]
    tiles = [token for token in jieba.cut(sentence.hanzi) if token.strip()]
    shuffled = tiles.copy()
    random.shuffle(shuffled)
    if shuffled == tiles and len(tiles) > 1:
        shuffled = tiles[1:] + tiles[:1]
    return DrillCard(
        item_type="pattern", item_id=item.id, mode=mode, hanzi=sentence.hanzi, pinyin=sentence.pinyin,
        meaning_vi=sentence.meaning_vi, usage_note_vi=item.explanation_vi, grammar_hint=item.pattern_formula,
        audio_text=sentence.hanzi, sentences=sentences, sentence_id=sentence.id, prompt=sentence.meaning_vi,
        answer=sentence.hanzi, tiles=shuffled if mode in {"reorder", "reverse"} else [],
    )


def _confusable_drill(pair: ConfusablePair, random: Random) -> DrillCard:
    choices = [pair.cloze_a_answer, pair.cloze_b_answer]
    random.shuffle(choices)
    a = re.sub(r"[_＿]{2,}", "＿＿", pair.cloze_a_hanzi)
    b = re.sub(r"[_＿]{2,}", "＿＿", pair.cloze_b_hanzi)
    filled = "\n".join((a.replace("＿＿", pair.cloze_a_answer), b.replace("＿＿", pair.cloze_b_answer)))
    return DrillCard(item_type="confusable", item_id=pair.id, mode="confusable", hanzi=filled, pinyin=pinyin(filled),
        meaning_vi=pair.diff_explanation_vi, prompt="\n".join((a, b)),
        answer="\n".join((pair.cloze_a_answer, pair.cloze_b_answer)), choices=choices, audio_text=filled.replace("\n", " "))


def study_session(
    db: Session, size: int, mode: SessionMode, source_id: int | None, level: int | None, leeches: bool,
) -> list[DrillCard]:
    catalog = _catalog(db, mode, source_id, level)
    if not catalog:
        return []
    now = datetime.now(timezone.utc)
    record = {(row.item_type, row.item_id): row for row in db.scalars(select(UserCard))
        if (row.item_type, row.item_id) in catalog}
    due = sorted(
        (key for key, row in record.items()
         if row.status not in {"new", "ignored"} and (row.is_leech or as_utc(row.due) <= now)
         and (not leeches or row.is_leech)),
        key=lambda key: (not record[key].is_leech, as_utc(record[key].due), -record[key].wrong_count),
    )
    fresh = sorted(
        (key for key in catalog if key not in record or record[key].status == "new"),
        key=lambda key: (key not in record, catalog[key].hsk_level or 6,
                         key[1] * (3 if key[0] == "pattern" and mode == "mixed" else 1), key[0] != "word"),
    ) if not leeches else []
    new_target = min(3, size // 3, len(fresh)) if due else size
    keys = due[:size - new_target] + fresh[:new_target]
    keys += (due[size - new_target:] + fresh[new_target:])[:size - len(keys)]
    if not keys:
        return []

    new = defaultdict(list)
    for key in keys:
        if key not in record:
            new[key[0]].append(key[1])
    for item_type, ids in new.items():
        enqueue_many(db, item_type, ids)
        for row in db.scalars(select(UserCard).where(UserCard.item_type == item_type, UserCard.item_id.in_(ids))):
            record[item_type, row.item_id] = row
    word_ids = [item_id for item_type, item_id in keys if item_type == "word"]
    pattern_ids = [item_id for item_type, item_id in keys if item_type == "pattern"]
    examples = _sentences(db, word_ids, pattern_ids)
    characters = _terms(db, word_ids)
    output = []
    pattern_index = 0
    for index, key in enumerate(keys):
        saved = record[key]
        item = catalog[key]
        random = Random(f"{saved.id}:{saved.reps}:{index}")
        if key[0] == "word":
            word_modes = ["flashcard", "listening"] + (["cloze"] if examples[key] else [])
            actual = word_modes[(index + saved.reps) % len(word_modes)] if mode == "mixed" else mode
            card = _word_drill(db, item, actual, examples[key], characters[key[1]], random)
        elif key[0] == "pattern":
            actual = ["reorder", "reverse"][(pattern_index + saved.reps) % 2] if mode == "mixed" else mode
            card = _pattern_drill(item, actual, examples[key], random)
            pattern_index += 1
        else:
            card = _confusable_drill(item, random)
        output.append(card.model_copy(update={"id": saved.id, "status": saved.status}))
    return output
