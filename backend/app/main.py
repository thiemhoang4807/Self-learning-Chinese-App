from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api import ai, backup, health, ingestion, library, manage, study
from app.config import settings
from app.db import SessionLocal, lock_catalog
from app.seeds.seed_data import seed_database


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with SessionLocal.begin() as session:
        lock_catalog(session)
        seed_database(session, full_hsk=settings.seed_full_hsk)
    yield


app = FastAPI(title="Mandarin Study", lifespan=lifespan)
for module in (ai, backup, health, ingestion, library, manage, study):
    app.include_router(module.router, prefix="/api")


@app.exception_handler(RequestValidationError)
async def invalid_input(_request: Request, _error: RequestValidationError) -> JSONResponse:
    return JSONResponse({"detail": "Dữ liệu gửi lên thiếu hoặc sai định dạng. Hãy kiểm tra và thử lại."}, status_code=422)


@app.exception_handler(HTTPException)
async def http_error(_request: Request, error: HTTPException) -> JSONResponse:
    messages = {
        "Not Found": "Không tìm thấy nội dung này.",
        "Method Not Allowed": "Thao tác này không khả dụng.",
        "There was an error parsing the body": "Không đọc được nội dung gửi lên.",
    }
    detail = messages.get(error.detail, error.detail) if isinstance(error.detail, str) else error.detail
    return JSONResponse({"detail": detail}, status_code=error.status_code, headers=error.headers)
