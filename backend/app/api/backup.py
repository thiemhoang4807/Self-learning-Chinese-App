from datetime import timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy.exc import DataError, IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.backup import BackupSnapshot, PreferencePatch, Preferences, RestoreSummary
from app.services.backup import (
    BackupConflict, export_backup, get_preferences, lock_backup_write, restore_backup, update_preferences,
)

MAX_BACKUP_BYTES = 64 * 1024 * 1024

router = APIRouter(prefix="/backup", tags=["backup"])
Database = Annotated[Session, Depends(get_db)]


@router.get("/export", response_class=Response)
def download_backup(db: Database) -> Response:
    try:
        snapshot = export_backup(db)
    except OperationalError as error:
        raise HTTPException(503, "Chưa kết nối được với cơ sở dữ liệu để tạo bản sao lưu.") from error
    except ValidationError as error:
        raise HTTPException(409, "Dữ liệu học có liên kết chưa hợp lệ. Chưa thể tạo bản sao lưu.") from error
    timestamp = snapshot.exported_at.astimezone(timezone(timedelta(hours=7))).strftime("%Y%m%d-%H%M%S")
    return Response(
        snapshot.model_dump_json(),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="chinese-study-backup-{timestamp}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/import", response_model=RestoreSummary)
def upload_backup(file: Annotated[UploadFile, File()], db: Database) -> RestoreSummary:
    data = file.file.read(MAX_BACKUP_BYTES + 1)
    if len(data) > MAX_BACKUP_BYTES:
        raise HTTPException(413, "Tệp sao lưu vượt giới hạn 64 MiB.")
    try:
        snapshot = BackupSnapshot.model_validate_json(data)
    except ValidationError as error:
        first_error = error.errors(include_context=False, include_input=False, include_url=False)[0]
        if first_error["type"] == "json_invalid":
            detail = "Tệp sao lưu không phải là JSON hợp lệ."
        elif first_error["loc"] == ("schema_version",):
            detail = "Phiên bản của tệp sao lưu chưa được hỗ trợ."
        else:
            detail = "Tệp sao lưu có dữ liệu hoặc liên kết không hợp lệ."
        raise HTTPException(422, detail) from error

    try:
        with db.begin():
            result = restore_backup(db, snapshot)
        return result
    except BackupConflict as error:
        raise HTTPException(409, str(error)) from error
    except (IntegrityError, DataError) as error:
        raise HTTPException(409, "Dữ liệu xung đột trong khi khôi phục. Dữ liệu hiện có vẫn được giữ nguyên.") from error
    except OperationalError as error:
        raise HTTPException(503, "Chưa thể ghi cơ sở dữ liệu. Hãy thử khôi phục lại sau.") from error


@router.get("/preferences", response_model=Preferences | None)
def read_preferences(response: Response, db: Database) -> Preferences | None:
    response.headers["Cache-Control"] = "no-store"
    return get_preferences(db)


@router.patch("/preferences", response_model=Preferences)
def save_preferences(payload: PreferencePatch, db: Database) -> Preferences:
    with db.begin():
        lock_backup_write(db)
        result = update_preferences(db, payload)
    return result
