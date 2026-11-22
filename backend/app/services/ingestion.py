import csv
import io
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timedelta, timezone
from itertools import islice
from pathlib import Path
from time import monotonic
from typing import TypeVar

import pymupdf
import jieba
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.text.paragraph import Paragraph
from fastapi import HTTPException
from lxml.etree import XMLSyntaxError
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from PIL import Image, ImageOps
from pypinyin import lazy_pinyin
from pypinyin.constants import Style
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Character,
    GrammarPattern,
    Sentence,
    SentenceWord,
    Source,
    SourcePattern,
    SourceSentence,
    SourceWord,
    Word,
    WordCharacter,
)
from app.schemas.ingestion import (
    ExtractedMaterial,
    ExtractedSentence,
    ExtractedWord,
    SourceSummary,
    SourceType,
    StagedMaterial,
    is_hanzi,
)
from app.seeds.levels import hsk_level_for
from app.services import ai

Batch = TypeVar("Batch")
MAX_TEXT = 84_000
MAX_TEXT_LINES = 25_000
TEXT_BATCH = 14_000
MAX_DOCUMENT_SECONDS = 180
IMAGE_SIDE = 1600
IMAGES_PER_BATCH = 4
MAX_BATCH_IMAGE_BYTES = 12 * 1024 * 1024
MAX_EXPANDED_OFFICE_BYTES = 150 * 1024 * 1024
TRUNCATED_TEXT = "Tài liệu dài nên chỉ trích phần văn bản đầu. Hãy chia tệp để nạp phần còn lại."
TRUNCATED_TIME = "Đã xử lý một phần tài liệu trong thời gian cho phép. Hãy chia tệp để nạp phần còn lại."

FILE_TYPES: dict[str, SourceType] = {
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".pdf": "pdf",
    ".ppt": "pptx",
    ".pptx": "pptx",
    ".doc": "docx",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".csv": "text",
    ".txt": "text",
}


def file_source_type(filename: str) -> SourceType:
    source_type = FILE_TYPES.get(Path(filename).suffix.lower())
    if source_type is None:
        raise HTTPException(status_code=415, detail="Định dạng tệp này chưa được hỗ trợ.")
    return source_type


def pronunciation(text: str) -> str:
    return " ".join(lazy_pinyin(text, style=Style.TONE))


def _guard_office_archive(data: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        if sum(member.file_size for member in members) > MAX_EXPANDED_OFFICE_BYTES or len(members) > 10_000:
            raise HTTPException(status_code=413, detail="Tài liệu Office quá lớn sau khi giải nén.")
        if any(member.flag_bits & 1 for member in members):
            raise HTTPException(status_code=422, detail="Hãy bỏ mật khẩu của tài liệu rồi thử lại.")


def _decode_text(data: bytes) -> str:
    encodings = ["utf-16"] if data.startswith((b"\xff\xfe", b"\xfe\xff")) else ["utf-8-sig", "gb18030"]
    for encoding in encodings:
        try:
            value = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\x00" not in value:
            return value
    raise HTTPException(status_code=422, detail="Không đọc được mã chữ của tệp. Hãy lưu lại dưới định dạng UTF-8.")


def _office_text(data: bytes, suffix: str) -> Iterable[str]:
    if suffix == ".docx":
        document = Document(io.BytesIO(data))
        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                yield block.text
            else:
                for row in block.rows:
                    yield "\t".join(cell.text for cell in row.cells)
        return

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
    try:
        for sheet in workbook.worksheets:
            yield sheet.title
            sheet.reset_dimensions()
            for row in sheet.iter_rows(values_only=True):
                yield "\t".join(str(value) if value is not None else "" for value in row).rstrip("\t")
    finally:
        workbook.close()


def _csv_text(data: bytes) -> Iterable[str]:
    content = _decode_text(data)
    try:
        dialect = csv.Sniffer().sniff(content[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = "excel"
    for row in csv.reader(io.StringIO(content, newline=""), dialect=dialect):
        yield "\t".join(row)


def _limited_text(lines: Iterable[str]) -> tuple[str, bool]:
    output = io.StringIO()
    for number, line in enumerate(lines):
        if number >= MAX_TEXT_LINES:
            return output.getvalue(), True
        line = line.strip()
        if not line:
            continue
        room = MAX_TEXT - output.tell()
        if len(line) + 1 > room:
            output.write(line[:room])
            return output.getvalue(), True
        output.write(line)
        output.write("\n")
    return output.getvalue(), False


def _text_batches(text: str) -> Iterable[str]:
    while text:
        cut = min(len(text), TEXT_BATCH)
        if cut < len(text):
            newline = text.rfind("\n", TEXT_BATCH // 2, cut)
            if newline != -1:
                cut = newline + 1
        yield text[:cut]
        text = text[cut:]


def _image_png(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as source:
        if source.format not in {"PNG", "JPEG", "WEBP"}:
            raise HTTPException(status_code=422, detail="Ảnh cần ở định dạng PNG, JPEG hoặc WebP.")
        if source.width * source.height > 32_000_000:
            raise HTTPException(status_code=413, detail="Ảnh quá lớn. Hãy thu nhỏ kích thước ảnh rồi thử lại.")
        image = ImageOps.exif_transpose(source)
        if "transparency" in image.info:
            image = image.convert("RGBA")
        image.thumbnail((IMAGE_SIDE, IMAGE_SIDE), Image.Resampling.LANCZOS)
        if "A" in image.getbands():
            opaque = Image.new("RGB", image.size, "white")
            opaque.paste(image, mask=image.getchannel("A"))
            image = opaque
        output = io.BytesIO()
        image.convert("RGB").save(output, format="PNG")
        return output.getvalue()


def _office_pdf(data: bytes, suffix: str) -> bytes:
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice:
        raise HTTPException(status_code=503, detail="Cần cài LibreOffice để đọc tệp trình chiếu hoặc tệp DOC.")
    with tempfile.TemporaryDirectory(prefix="mandarin-convert-") as temp:
        directory = Path(temp)
        source = directory / f"document{suffix}"
        source.write_bytes(data)
        result = subprocess.run(
            [
                soffice,
                f"-env:UserInstallation={(directory / 'lo_profile').as_uri()}",
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                str(directory),
                str(source),
            ],
            cwd=directory,
            capture_output=True,
            timeout=55,
            check=False,
        )
        output = directory / "document.pdf"
        if result.returncode or not output.is_file():
            raise HTTPException(status_code=422, detail="LibreOffice không chuyển được tài liệu này sang PDF.")
        if output.stat().st_size > MAX_EXPANDED_OFFICE_BYTES:
            raise HTTPException(status_code=413, detail="Tài liệu sau khi đổi sang PDF quá lớn.")
        return output.read_bytes()


def _pdf_batches(document: pymupdf.Document) -> Iterable[list[bytes]]:
    batch: list[bytes] = []
    batch_bytes = 0
    for number in range(min(len(document), settings.max_visual_pages)):
        page = document[number]
        side = max(page.rect.width, page.rect.height)
        scale = min(2.0, IMAGE_SIDE / side) if side > 0 else 1.0
        png = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")
        if batch and (len(batch) == IMAGES_PER_BATCH or batch_bytes + len(png) > MAX_BATCH_IMAGE_BYTES):
            yield batch
            batch = []
            batch_bytes = 0
        batch.append(png)
        batch_bytes += len(png)
    if batch:
        yield batch


def _run_batches(
    batches: Iterable[Batch], extractor: Callable[[Batch], ExtractedMaterial], deadline: float,
) -> tuple[list[ExtractedMaterial], bool]:
    extracted = []
    for batch in batches:
        if extracted and monotonic() >= deadline:
            return extracted, True
        extracted.append(extractor(batch))
    return extracted, False


def extract_file(db: Session, filename: str, data: bytes) -> StagedMaterial:
    source_type = file_source_type(filename)
    if not data:
        raise HTTPException(status_code=422, detail="Tệp trống. Hãy chọn tệp có nội dung học.")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Tệp vượt quá dung lượng cho phép.")
    ai.gemini_key()
    suffix = Path(filename).suffix.lower()
    deadline = monotonic() + MAX_DOCUMENT_SECONDS
    notice = None
    try:
        if suffix in {".docx", ".xlsx", ".pptx"}:
            _guard_office_archive(data)
        if source_type == "image":
            extracted = [ai.extract_images([_image_png(data)])]
        elif source_type in {"pdf", "pptx"} or suffix == ".doc":
            pdf = data if suffix == ".pdf" else _office_pdf(data, suffix)
            with pymupdf.open(stream=pdf, filetype="pdf") as document:
                if document.needs_pass:
                    raise HTTPException(status_code=422, detail="Hãy bỏ mật khẩu của PDF rồi thử lại.")
                if len(document) > settings.max_visual_pages:
                    notice = f"Đã chọn {settings.max_visual_pages} trang đầu. Hãy chia tệp để nạp các trang còn lại."
                extracted, timed_out = _run_batches(_pdf_batches(document), ai.extract_images, deadline)
                if timed_out:
                    notice = TRUNCATED_TIME
        else:
            if suffix in {".docx", ".xlsx"}:
                text, truncated = _limited_text(_office_text(data, suffix))
            elif suffix == ".csv":
                text, truncated = _limited_text(_csv_text(data))
            else:
                raw_text = _decode_text(data)
                text, truncated = raw_text[:MAX_TEXT], len(raw_text) > MAX_TEXT
            if not text.strip():
                raise HTTPException(status_code=422, detail="Không tìm thấy văn bản trong tài liệu.")
            extracted, timed_out = _run_batches(_text_batches(text), ai.extract_text, deadline)
            if truncated or timed_out:
                notice = TRUNCATED_TIME if timed_out else TRUNCATED_TEXT
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=422, detail="Tài liệu mất quá lâu để chuyển đổi. Hãy chia nhỏ tệp rồi thử lại.") from exc
    except (
        pymupdf.FileDataError,
        OSError,
        ValueError,
        KeyError,
        csv.Error,
        zipfile.BadZipFile,
        InvalidFileException,
        PackageNotFoundError,
        XMLSyntaxError,
        Image.DecompressionBombError,
    ) as exc:
        raise HTTPException(status_code=422, detail="Không đọc được tệp. Hãy kiểm tra nội dung và định dạng.") from exc

    title = Path(filename.replace("\\", "/")).name[:250] or "Tài liệu học"
    return _stage(db, title, source_type, extracted, notice)


def extract_paste(db: Session, content: str) -> StagedMaterial:
    content = content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Vui lòng dán đoạn văn cần trích xuất.")
    chunks = _text_batches(content[:MAX_TEXT])
    batches, timed_out = _run_batches(chunks, ai.extract_text, monotonic() + MAX_DOCUMENT_SECONDS)
    notice = None
    if len(content) > MAX_TEXT or timed_out:
        notice = TRUNCATED_TIME if timed_out else TRUNCATED_TEXT
    timestamp = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M")
    return _stage(db, f"Nội dung đã dán · {timestamp}", "paste", batches, notice)


def _stage(
    db: Session, title: str, source_type: SourceType, batches: list[ExtractedMaterial], notice: str | None
) -> StagedMaterial:
    words = {word.simplified: word for batch in batches for word in batch.words}
    patterns = {pattern.pattern_formula: pattern for batch in batches for pattern in batch.grammar_patterns}
    sentences = {sentence.hanzi: sentence for batch in batches for sentence in batch.sentences}
    if not words and not patterns and not sentences:
        raise HTTPException(status_code=422, detail="Chưa thấy từ, mẫu ngữ pháp hoặc câu tiếng Trung trong tài liệu.")
    known_words = dict(db.execute(select(Word.simplified, Word.hsk_level).where(Word.simplified.in_(words))).all())
    known_patterns = set(db.scalars(select(GrammarPattern.pattern_formula).where(GrammarPattern.pattern_formula.in_(patterns))))
    known_sentences = set(db.scalars(select(Sentence.hanzi).where(Sentence.hanzi.in_(sentences))))
    summaries = list(dict.fromkeys(batch.summary_note for batch in batches if batch.summary_note))
    if not notice and (len(words) > 1200 or len(patterns) > 400 or len(sentences) > 1200):
        notice = "Tài liệu có nhiều mục. Hãy chia tệp để nạp các mục chưa hiển thị."
    return StagedMaterial(
        title=title,
        source_type=source_type,
        summary_note=" ".join(summaries)[:4000],
        words=[
            word.model_dump() | {"existing": key in known_words, "hsk_level": hsk_level_for(key) or known_words.get(key)}
            for key, word in islice(words.items(), 1200)
        ],
        grammar_patterns=[
            pattern.model_dump() | {"existing": key in known_patterns}
            for key, pattern in islice(patterns.items(), 400)
        ],
        sentences=[
            sentence.model_dump() | {"existing": key in known_sentences}
            for key, sentence in islice(sentences.items(), 1200)
        ],
        notice_vi=notice,
    )


def insert_missing(db: Session, model: type, values: dict, keys: Sequence) -> bool:
    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    statement = insert(model).values(**values).on_conflict_do_nothing(index_elements=list(keys))
    return db.execute(statement).rowcount == 1


def _fill_missing(model, values: dict) -> None:
    for name, value in values.items():
        if value and not getattr(model, name):
            setattr(model, name, value)


def upsert_word(db: Session, payload: ExtractedWord, *, enrich_existing: bool = False) -> Word:
    values = payload.model_dump(exclude={"characters", "existing"})
    values["pinyin"] = payload.pinyin or pronunciation(payload.simplified)[:200]
    values["hsk_level"] = hsk_level_for(payload.simplified)
    created = insert_missing(db, Word, values, [Word.simplified])
    query = select(Word).where(Word.simplified == payload.simplified)
    word = db.scalars(query.with_for_update() if enrich_existing else query).one()
    if not created and not enrich_existing and word.meaning_vi:
        return word
    if not created:
        _fill_missing(word, values)

    details = {item.char: item for item in payload.characters}
    chars = sorted({char for char in word.simplified if is_hanzi(char)})
    for char in chars:
        item = details.get(char)
        insert_missing(
            db,
            Character,
            {
                "char": char,
                "pinyin": item.pinyin if item and item.pinyin else pronunciation(char),
                "han_viet": item.han_viet if item else "",
                "radical": item.radical if item else "",
                "components_json": item.components if item else [],
                "mnemonic_vi": item.mnemonic_vi if item else "",
                "hsk_level": word.hsk_level,
            },
            [Character.char],
        )

    rows = {row.char: row for row in db.scalars(select(Character).where(Character.char.in_(chars)))}
    if not created:
        for char, row in rows.items():
            if char in details:
                values = details[char].model_dump(exclude={"char", "components"})
                values["components_json"] = details[char].components
                _fill_missing(row, values)
    for index, char in enumerate(word.simplified):
        if char in rows:
            insert_missing(
                db, WordCharacter, {"word_id": word.id, "character_id": rows[char].id, "position": index},
                [WordCharacter.word_id, WordCharacter.position],
            )
    return word


def upsert_sentence(
    db: Session,
    payload: ExtractedSentence,
    grammar_pattern_id: int | None = None,
    generated: bool = False,
    related_words: Sequence[str] = (),
) -> Sentence:
    insert_missing(
        db,
        Sentence,
        {
            "hanzi": payload.hanzi,
            "pinyin": payload.pinyin or pronunciation(payload.hanzi),
            "meaning_vi": payload.meaning_vi,
            "grammar_pattern_id": grammar_pattern_id,
            "is_ai_generated": generated,
        },
        [Sentence.hanzi],
    )
    sentence = db.scalars(select(Sentence).where(Sentence.hanzi == payload.hanzi)).one()
    if grammar_pattern_id is not None and sentence.grammar_pattern_id is None:
        db.execute(
            update(Sentence)
            .where(Sentence.id == sentence.id, Sentence.grammar_pattern_id.is_(None))
            .values(grammar_pattern_id=grammar_pattern_id)
        )
        db.refresh(sentence, attribute_names=["grammar_pattern_id"])
    tokens = set(jieba.cut(sentence.hanzi, HMM=False))
    tokens.update(related_words)
    word_ids = sorted(db.scalars(select(Word.id).where(Word.simplified.in_(tokens))))
    for word_id in word_ids:
        insert_missing(
            db, SentenceWord, {"sentence_id": sentence.id, "word_id": word_id},
            [SentenceWord.sentence_id, SentenceWord.word_id],
        )
    return sentence


def save_material(db: Session, material: StagedMaterial) -> SourceSummary:
    from app.db import lock_catalog
    from app.services.study import enqueue

    words = {item.simplified: item for item in material.words}
    patterns = {item.pattern_formula: item for item in material.grammar_patterns}
    sentences = {item.hanzi: item for item in material.sentences}
    if not words and not patterns and not sentences:
        raise HTTPException(status_code=422, detail="Hãy chọn ít nhất một mục để lưu vào kho ôn.")

    lock_catalog(db)
    source = Source(title=material.title, source_type=material.source_type, summary_note=material.summary_note)
    db.add(source)
    db.flush()
    for key in sorted(words):
        word = upsert_word(db, words[key])
        db.add(SourceWord(source_id=source.id, word_id=word.id))
        enqueue(db, "word", word.id)

    for key in sorted(patterns):
        insert_missing(
            db, GrammarPattern, patterns[key].model_dump(exclude={"existing"}), [GrammarPattern.pattern_formula],
        )
        pattern = db.scalars(select(GrammarPattern).where(GrammarPattern.pattern_formula == key)).one()
        db.add(SourcePattern(source_id=source.id, pattern_id=pattern.id))
        enqueue(db, "pattern", pattern.id)

    formulas = {sentence.pattern_formula for sentence in sentences.values() if sentence.pattern_formula}
    pattern_ids = dict(
        db.execute(select(GrammarPattern.pattern_formula, GrammarPattern.id).where(GrammarPattern.pattern_formula.in_(formulas))).all()
    )
    for key in sorted(sentences):
        item = sentences[key]
        related_words = [word for word in words if len(word) > 1 and word in item.hanzi]
        sentence = upsert_sentence(db, item, pattern_ids.get(item.pattern_formula), related_words=related_words)
        db.add(SourceSentence(source_id=source.id, sentence_id=sentence.id))

    db.commit()
    return SourceSummary(
        id=source.id, title=source.title, source_type=source.source_type,
        summary_note=source.summary_note, created_at=source.created_at, word_count=len(words),
        pattern_count=len(patterns), sentence_count=len(sentences),
    )


def source_summaries(db: Session, *, source_id: int | None = None) -> list[SourceSummary]:
    def counts(model):
        return select(func.count()).select_from(model).where(model.source_id == Source.id).scalar_subquery()

    statement = select(Source, counts(SourceWord), counts(SourcePattern), counts(SourceSentence))
    if source_id is not None:
        statement = statement.where(Source.id == source_id)
    rows = db.execute(statement.order_by(Source.created_at.desc(), Source.id.desc()))
    return [
        SourceSummary(
            id=source.id, title=source.title, source_type=source.source_type, summary_note=source.summary_note,
            created_at=source.created_at, word_count=words, pattern_count=patterns, sentence_count=sentences,
        )
        for source, words, patterns, sentences in rows
    ]
