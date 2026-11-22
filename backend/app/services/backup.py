from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import lock_catalog
from app.models import (
    Character, ConfusablePair, GrammarPattern, ReviewLog, Sentence, SentenceWord, Source,
    SourcePattern, SourceSentence, SourceWord, StoryAttempt, UserCard, UserPreference,
    Word, WordCharacter,
)
from app.schemas.backup import BackupSnapshot, PreferencePatch, Preferences, RestoreSummary, as_utc

BACKUP_TABLES = (
    ("words", Word), ("characters", Character), ("grammar_patterns", GrammarPattern),
    ("sentences", Sentence), ("confusable_pairs", ConfusablePair), ("word_characters", WordCharacter),
    ("sentence_words", SentenceWord), ("sources", Source), ("source_words", SourceWord),
    ("source_patterns", SourcePattern), ("source_sentences", SourceSentence),
    ("user_cards", UserCard), ("review_logs", ReviewLog), ("story_attempts", StoryAttempt),
)
UID_MODELS = {Source, ReviewLog, StoryAttempt}


class BackupConflict(Exception):
    pass


def get_preferences(db: Session) -> Preferences | None:
    saved = db.get(UserPreference, 1)
    return Preferences.model_validate(saved) if saved is not None else None


def update_preferences(db: Session, changes: PreferencePatch | Preferences) -> Preferences:
    saved = db.get(UserPreference, 1)
    values = changes.model_dump(exclude_unset=True)
    if saved is None:
        saved = UserPreference(id=1, **values)
        db.add(saved)
    else:
        set_changed(saved, values)
    db.flush()
    return Preferences.model_validate(saved)


def _uid(row: Source | ReviewLog | StoryAttempt) -> str:
    if row.backup_uid is not None:
        return row.backup_uid
    # Reserve a stable identity for valid rows written by an older client after migration.
    stamp = row.reviewed_at if isinstance(row, ReviewLog) else row.created_at
    return str(uuid5(NAMESPACE_URL, f"mandarin-study:{row.__tablename__}:{row.id}:{as_utc(stamp).isoformat()}"))


def export_backup(db: Session) -> BackupSnapshot:
    if db.get_bind().dialect.name == "postgresql":
        db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    else:
        connection = db.connection()
        # SQLite's legacy transaction mode does not start a transaction for SELECT.
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN")
    records = {}
    for field, model in BACKUP_TABLES:
        rows = db.scalars(select(model).order_by(*model.__table__.primary_key.columns))
        if model in UID_MODELS:
            records[field] = [
                {**{column.name: getattr(row, column.name) for column in model.__table__.columns},
                 "backup_uid": _uid(row)}
                for row in rows
            ]
        else:
            records[field] = list(rows)
    return BackupSnapshot(
        schema_version=1,
        exported_at=datetime.now(timezone.utc),
        preferences=get_preferences(db) or Preferences(theme="light", pinyin=False),
        **records,
    )


def same_value(existing, incoming) -> bool:
    if isinstance(existing, datetime) and isinstance(incoming, datetime):
        return as_utc(existing) == as_utc(incoming)
    return existing == incoming


def set_changed(row, values: dict) -> bool:
    changed = False
    for field, value in values.items():
        if not same_value(getattr(row, field), value):
            setattr(row, field, value)
            changed = True
    return changed


def _merge_entities(
    db: Session, model, records: Iterable[tuple[int, dict]], key_fields: tuple[str, ...],
) -> tuple[dict[int, int], int, int]:
    def key(values: dict) -> tuple:
        return tuple(values[field] for field in key_fields)

    existing = {}
    for row in db.scalars(select(model)):
        identity = (
            (_uid(row),) if key_fields == ("backup_uid",)
            else tuple(getattr(row, field) for field in key_fields)
        )
        existing[identity] = row
    incoming_pairs = set()
    if model is ConfusablePair:
        records = list(records)
        incoming_pairs = {key(payload) for _, payload in records}

    mapped = {}
    created = updated = 0
    for old_id, payload in records:
        identity = key(payload)
        row = existing.get(identity)
        if row is None and model is ConfusablePair:
            reversed_identity = identity[::-1]
            if reversed_identity not in incoming_pairs:
                row = existing.get(reversed_identity)
        if row is None:
            row = model(**payload)
            db.add(row)
            created += 1
        else:
            # Empty catalog fields carry no information during merge. A null HSK level is
            # meaningful because it explicitly places an item outside the leveled catalog.
            populated = {
                field: value for field, value in payload.items()
                if field == "hsk_level" or value not in (None, "", [], {})
            }
            updated += set_changed(row, populated)
        mapped[old_id] = row
    db.flush()
    return {old_id: row.id for old_id, row in mapped.items()}, created, updated


def _values(records, **translate: Callable) -> Iterable[tuple[int, dict]]:
    for record in records:
        values = record.model_dump(exclude={"id"})
        for field, converter in translate.items():
            values[field] = converter(values[field])
        yield record.id, values


def _merge_links(db: Session, model, records, **id_maps: dict[int, int]) -> None:
    primary_keys = tuple(column.name for column in model.__table__.primary_key.columns)
    existing = {
        tuple(getattr(row, field) for field in primary_keys): row for row in db.scalars(select(model))
    }
    for record in records:
        values = record.model_dump()
        for field, id_map in id_maps.items():
            values[field] = id_map[values[field]]
        primary_key = tuple(values[field] for field in primary_keys)
        row = existing.get(primary_key)
        if row is None:
            db.add(model(**values))
        else:
            set_changed(row, values)


def _latest_review(state: dict | None, from_log: datetime | None) -> datetime:
    value = state.get("last_review") if state else None
    dates = [datetime.min.replace(tzinfo=timezone.utc)]
    if value:
        dates.append(as_utc(datetime.fromisoformat(value)))
    if from_log is not None:
        dates.append(as_utc(from_log))
    return max(dates)


def _restore_reviews(db: Session, snapshot: BackupSnapshot, ids: dict, summary: RestoreSummary) -> None:
    existing_cards = {
        (row.item_type, row.item_id): row
        for row in db.scalars(select(UserCard).order_by(UserCard.id).with_for_update())
    }
    existing_logs = list(db.scalars(select(ReviewLog)))
    current_last = _latest_logs(existing_logs)
    incoming_last = _latest_logs(snapshot.review_logs)
    cards = {}
    for incoming in snapshot.user_cards:
        item_id = ids[incoming.item_type][incoming.item_id]
        values = incoming.model_dump(exclude={"id", "item_id", "item_type"})
        row = existing_cards.get((incoming.item_type, item_id))
        if row is None:
            row = UserCard(item_type=incoming.item_type, item_id=item_id, **values)
            db.add(row)
            summary.cards_created += 1
        else:
            current_rank = (_latest_review(row.fsrs_state_json, current_last.get(row.id)), row.reps)
            incoming_rank = (_latest_review(incoming.fsrs_state_json, incoming_last.get(incoming.id)), incoming.reps)
            if incoming_rank >= current_rank:
                summary.cards_updated += set_changed(row, values)
        cards[incoming.id] = row
    db.flush()

    by_uid = {_uid(log): log for log in existing_logs}
    by_token = {log.review_token: log for log in existing_logs if log.review_token is not None}
    for log in snapshot.review_logs:
        values = log.model_dump(exclude={"id", "backup_uid", "card_id"})
        values["card_id"] = cards[log.card_id].id
        uid = str(log.backup_uid)
        same_id = by_uid.get(uid)
        same_token = by_token.get(log.review_token)
        row = same_id or same_token
        if row is None:
            db.add(ReviewLog(backup_uid=uid, **values))
            summary.reviews_added += 1
        elif (same_id is not None and same_token is not None and same_id.id != same_token.id) or any(
            not same_value(getattr(row, field), value) for field, value in values.items()
        ):
            raise BackupConflict("Bản sao lưu chứa lượt ôn xung đột với lịch sử hiện có.")


def _latest_logs(logs: Iterable) -> dict[int, datetime]:
    result: dict[int, datetime] = {}
    for row in logs:
        reviewed = as_utc(row.reviewed_at)
        if row.card_id not in result or reviewed > result[row.card_id]:
            result[row.card_id] = reviewed
    return result


def _restore_stories(db: Session, snapshot: BackupSnapshot) -> int:
    existing = {_uid(row): row for row in db.scalars(select(StoryAttempt))}
    added = 0
    for story in snapshot.story_attempts:
        values = story.model_dump(exclude={"id", "backup_uid"})
        uid = str(story.backup_uid)
        row = existing.get(uid)
        if row is None:
            db.add(StoryAttempt(backup_uid=uid, **values))
            added += 1
        elif any(not same_value(getattr(row, field), value) for field, value in values.items()):
            raise BackupConflict("Bản sao lưu chứa bài viết xung đột với lịch sử hiện có.")
    return added


def lock_backup_write(db: Session) -> None:
    lock_catalog(db)
    if db.get_bind().dialect.name == "sqlite":
        # Serialize the read-then-write merge with other restores and study writes.
        connection = db.connection()
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")


def restore_backup(db: Session, snapshot: BackupSnapshot) -> RestoreSummary:
    lock_backup_write(db)
    words, words_created, words_updated = _merge_entities(db, Word, _values(snapshot.words), ("simplified",))
    characters, _, _ = _merge_entities(db, Character, _values(snapshot.characters), ("char",))
    patterns, _, _ = _merge_entities(db, GrammarPattern, _values(snapshot.grammar_patterns), ("pattern_formula",))
    sentences, _, _ = _merge_entities(db, Sentence, _values(
        snapshot.sentences, grammar_pattern_id=lambda value: patterns[value] if value is not None else None,
    ), ("hanzi",))
    confusables, _, _ = _merge_entities(db, ConfusablePair, _values(
        snapshot.confusable_pairs, word_a_id=words.__getitem__, word_b_id=words.__getitem__,
    ), ("word_a_id", "word_b_id"))
    sources, sources_created, sources_updated = _merge_entities(
        db, Source, _values(snapshot.sources, backup_uid=str), ("backup_uid",),
    )

    _merge_links(db, WordCharacter, snapshot.word_characters, word_id=words, character_id=characters)
    _merge_links(db, SentenceWord, snapshot.sentence_words, sentence_id=sentences, word_id=words)
    _merge_links(db, SourceWord, snapshot.source_words, source_id=sources, word_id=words)
    _merge_links(db, SourcePattern, snapshot.source_patterns, source_id=sources, pattern_id=patterns)
    _merge_links(db, SourceSentence, snapshot.source_sentences, source_id=sources, sentence_id=sentences)
    summary = RestoreSummary(
        words_created=words_created, words_updated=words_updated,
        sources_created=sources_created, sources_updated=sources_updated,
        preferences=update_preferences(db, snapshot.preferences),
    )
    _restore_reviews(db, snapshot, {"word": words, "pattern": patterns, "confusable": confusables}, summary)
    summary.stories_added = _restore_stories(db, snapshot)
    summary.message = (
        f"Đã thêm {summary.words_created} từ, {summary.sources_created} nguồn, "
        f"{summary.cards_created} thẻ, {summary.reviews_added} lượt ôn và {summary.stories_added} bài viết. "
        f"Đã cập nhật {summary.words_updated} từ, {summary.sources_updated} nguồn và {summary.cards_updated} thẻ."
    )
    return summary
