from __future__ import annotations

import json

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.config import get_settings
from app.db.session import Base, engine, get_db
from app.schemas.candidate import (
    BatchUploadResult,
    JDMatchRequest,
    RebuildVectorsResponse,
    ReviewUpdateRequest,
    SearchRequest,
    UploadResult,
)
from app.services.dedup import build_duplicate_key, file_sha256
from app.services.matching import JDMatcher
from app.services.parser_orchestrator import ParserOptions, ParserOrchestrator
from app.services.parsers import UnsupportedFileTypeError, extract_text
from app.services.query_parser import QueryPlanner
from app.services.repository import CandidateRepository, to_candidate_summary
from app.services.search import search_candidates
from app.services.vector_store import CandidateVectorStore

settings = get_settings()
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.api_base_url,
        settings.streamlit_base_url,
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

parser_orchestrator = ParserOrchestrator()
planner = QueryPlanner()


def _validate_upload(file_bytes: bytes, filename: str) -> None:
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large. Max size is {settings.max_upload_size_mb}MB")
    if not filename:
        raise HTTPException(status_code=400, detail="Missing filename")


def _sync_candidate_vector(db: Session, candidate) -> None:
    if not candidate.vector_document:
        return
    vector_store = CandidateVectorStore(db)
    vector_store.upsert_candidate_vector(
        candidate=candidate,
        vector_text=candidate.vector_document,
        metadata=json.loads(candidate.vector_metadata_json or "{}"),
    )
    db.commit()


def _parse_and_normalize(raw_text: str, filename: str, parser_meta: dict, parser_options: ParserOptions):
    return parser_orchestrator.parse_and_normalize(
        raw_text,
        filename=filename,
        parser_meta=parser_meta,
        options=parser_options,
    )


def _process_file(file_bytes: bytes, filename: str, db: Session, parser_options: ParserOptions) -> UploadResult:
    _validate_upload(file_bytes, filename)
    repo = CandidateRepository(db)
    digest = file_sha256(file_bytes)
    existing_document = repo.get_by_file_hash(digest)
    if existing_document and existing_document.candidate_id:
        existing_candidate = repo.get(existing_document.candidate_id)
        if not existing_candidate:
            raise HTTPException(status_code=500, detail="Document duplicate points to missing candidate")
        extraction_run = existing_candidate.extraction_runs[-1] if existing_candidate.extraction_runs else None
        return UploadResult(
            candidate=to_candidate_summary(existing_candidate),
            extraction=json.loads(extraction_run.raw_extraction_json) if extraction_run else {},
            audit=json.loads(extraction_run.audit_json) if extraction_run else {},
            warnings=["duplicate_file_skipped"],
        )

    parse_result = extract_text(file_bytes, filename)
    if len(parse_result.text.strip()) < settings.min_text_length:
        raise HTTPException(status_code=422, detail="Extracted text is too short for reliable CV parsing")

    extraction, audit, normalized = _parse_and_normalize(parse_result.text, filename, parse_result.parser_meta, parser_options)
    candidate = repo.create_candidate_bundle(
        normalized=normalized,
        extraction_json=extraction.model_dump(),
        audit_json=audit.model_dump(),
        file_info={
            "filename": filename,
            "mime_type": parse_result.mime_type,
            "file_hash": digest,
            "raw_text": parse_result.text,
            "used_ocr": parse_result.parser_meta.get("used_ocr", False),
            "parser_engine": parse_result.parser_meta.get("parser"),
            "parser_meta": parse_result.parser_meta,
            "duplicate_group": build_duplicate_key(
                normalized.get("full_name"),
                normalized.get("primary_email"),
                normalized.get("primary_phone"),
            ),
        },
    )
    _sync_candidate_vector(db, candidate)

    return UploadResult(
        candidate=to_candidate_summary(candidate),
        extraction=extraction,
        audit=audit,
        warnings=normalized.get("review_reasons", []),
    )


def _reparse_candidate(candidate_id: int, db: Session, parser_options: ParserOptions):
    repo = CandidateRepository(db)
    row = repo.get(candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not row.documents:
        raise HTTPException(status_code=422, detail="Candidate has no source document to reparse")

    document = sorted(row.documents, key=lambda item: item.created_at, reverse=True)[0]
    parser_meta = json.loads(document.parser_meta_json or "{}") if document.parser_meta_json else {}
    extraction, audit, normalized = _parse_and_normalize(document.raw_text, document.source_filename, parser_meta, parser_options)
    updated = repo.reparse_candidate_bundle(
        candidate_id=candidate_id,
        normalized=normalized,
        extraction_json=extraction.model_dump(),
        audit_json=audit.model_dump(),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _sync_candidate_vector(db, updated)
    return {
        "candidate": to_candidate_summary(updated).model_dump(),
        "audit": audit.model_dump(),
        "warnings": normalized.get("review_reasons", []),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": settings.app_version, "default_parser_strategy": settings.default_parser_strategy}


@app.get("/api/v1/query-plan")
def preview_query_plan(query: str):
    return planner.plan(query).model_dump()


@app.post("/api/v1/candidates/upload")
async def upload_candidate(
    file: UploadFile = File(...),
    parser_strategy: str = Form("local"),
    gemini_api_key: str | None = Form(None),
    gemini_model: str | None = Form(None),
    db: Session = Depends(get_db),
):
    parser_options = ParserOptions.from_inputs(
        parser_strategy=parser_strategy,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
    )
    try:
        file_bytes = await file.read()
        result = _process_file(file_bytes, file.filename or "uploaded_cv", db, parser_options)
        return result.model_dump()
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {exc}") from exc


@app.post("/api/v1/candidates/upload-batch")
async def upload_batch(
    files: list[UploadFile] = File(...),
    parser_strategy: str = Form("local"),
    gemini_api_key: str | None = Form(None),
    gemini_model: str | None = Form(None),
    db: Session = Depends(get_db),
):
    parser_options = ParserOptions.from_inputs(
        parser_strategy=parser_strategy,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
    )
    results: list[BatchUploadResult] = []
    for file in files:
        try:
            file_bytes = await file.read()
            result = _process_file(file_bytes, file.filename or "uploaded_cv", db, parser_options)
            results.append(
                BatchUploadResult(
                    filename=file.filename or "uploaded_cv",
                    status="processed",
                    candidate_id=result.candidate.id,
                    review_status=result.candidate.review_status,
                    confidence_score=result.candidate.confidence_score,
                    warnings=result.warnings,
                )
            )
        except Exception as exc:
            results.append(BatchUploadResult(filename=file.filename or "uploaded_cv", status="failed", error=str(exc)))
    return [item.model_dump() for item in results]


@app.post("/api/v1/candidates/reparse-all")
def reparse_all(
    parser_strategy: str = "local",
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    db: Session = Depends(get_db),
):
    parser_options = ParserOptions.from_inputs(
        parser_strategy=parser_strategy,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
    )
    repo = CandidateRepository(db)
    updated = 0
    failed: list[dict] = []
    rows = repo.list_all()
    for candidate in rows:
        try:
            _reparse_candidate(candidate.id, db, parser_options)
            updated += 1
        except Exception as exc:
            failed.append({"candidate_id": candidate.id, "error": str(exc)})
    return {"total_candidates": len(rows), "reparsed": updated, "failed": failed}


@app.post("/api/v1/candidates/{candidate_id}/reparse")
def reparse_candidate(
    candidate_id: int,
    parser_strategy: str = "local",
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    db: Session = Depends(get_db),
):
    parser_options = ParserOptions.from_inputs(
        parser_strategy=parser_strategy,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
    )
    return _reparse_candidate(candidate_id, db, parser_options)


@app.post("/api/v1/candidates/rebuild-vectors")
def rebuild_vectors(db: Session = Depends(get_db)):
    repo = CandidateRepository(db)
    vector_store = CandidateVectorStore(db)
    rows = repo.list_all()
    rebuilt = 0
    skipped = 0
    for row in rows:
        if not row.vector_document:
            skipped += 1
            continue
        vector_store.upsert_candidate_vector(
            candidate=row,
            vector_text=row.vector_document,
            metadata=json.loads(row.vector_metadata_json or "{}"),
        )
        rebuilt += 1
    db.commit()
    response = RebuildVectorsResponse(
        total_candidates=len(rows),
        rebuilt_vectors=rebuilt,
        skipped_vectors=skipped,
        model_name=vector_store.model_name,
    )
    return response.model_dump()


@app.get("/api/v1/candidates")
def list_candidates(db: Session = Depends(get_db)):
    repo = CandidateRepository(db)
    return [to_candidate_summary(row).model_dump() for row in repo.list_all()]


@app.get("/api/v1/candidates/{candidate_id}")
def get_candidate(candidate_id: int, db: Session = Depends(get_db)):
    repo = CandidateRepository(db)
    row = repo.get(candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    extraction_run = row.extraction_runs[-1] if row.extraction_runs else None
    return {
        "candidate": to_candidate_summary(row).model_dump(),
        "extraction": json.loads(extraction_run.raw_extraction_json) if extraction_run else {},
        "normalized_profile": json.loads(extraction_run.normalized_profile_json) if extraction_run else {},
        "audit": json.loads(extraction_run.audit_json) if extraction_run else {},
    }


@app.get("/api/v1/review-queue")
def review_queue(db: Session = Depends(get_db)):
    repo = CandidateRepository(db)
    return [to_candidate_summary(row).model_dump() for row in repo.list_by_review_status("needs_review")]


@app.post("/api/v1/review/{candidate_id}")
def update_review(candidate_id: int, payload: ReviewUpdateRequest, db: Session = Depends(get_db)):
    repo = CandidateRepository(db)
    row = repo.update_review(candidate_id, payload.review_status, payload.review_reason)
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return to_candidate_summary(row).model_dump()


@app.get("/api/v1/duplicates")
def duplicate_groups(db: Session = Depends(get_db)):
    repo = CandidateRepository(db)
    return repo.duplicate_groups()


@app.get("/api/v1/analytics")
def analytics(db: Session = Depends(get_db)):
    repo = CandidateRepository(db)
    return repo.analytics()


@app.get("/api/v1/export.csv", response_class=PlainTextResponse)
def export_csv(db: Session = Depends(get_db)):
    repo = CandidateRepository(db)
    return repo.export_csv()


@app.post("/api/v1/search")
def search(request: SearchRequest, db: Session = Depends(get_db)):
    return [item.model_dump() for item in search_candidates(db, request)]


@app.post("/api/v1/match/jd")
def match_jd(request: JDMatchRequest, db: Session = Depends(get_db)):
    matcher = JDMatcher(db)
    return matcher.match(request).model_dump()
