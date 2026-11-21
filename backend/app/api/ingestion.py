from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.schemas.ingestion import SourceSummary, StagedMaterial
from app.services import ingestion

router = APIRouter(prefix="/ingestion", tags=["ingestion"])
Database = Annotated[Session, Depends(get_db)]


@router.post("/extract", response_model=StagedMaterial)
def extract(
    db: Database,
    file: Annotated[UploadFile | None, File()] = None,
    text: Annotated[str | None, Form()] = None,
) -> StagedMaterial:
    if (file is None) == (text is None):
        raise HTTPException(status_code=422, detail="Hãy chọn một tệp hoặc dán một đoạn văn bản.")
    if file is not None:
        return ingestion.extract_file(
            db, file.filename or "", file.file.read(settings.max_upload_bytes + 1),
        )
    return ingestion.extract_paste(db, text or "")


@router.post("/save", response_model=SourceSummary, status_code=201)
def save(material: StagedMaterial, db: Database) -> SourceSummary:
    return ingestion.save_material(db, material)


@router.get("/sources", response_model=list[SourceSummary])
def list_sources(db: Database) -> list[SourceSummary]:
    return ingestion.source_summaries(db)
