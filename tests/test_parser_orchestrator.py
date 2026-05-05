from __future__ import annotations

import json

from app.schemas.candidate import CandidateExtraction, ExtractedField
from app.services.gemini_parser import GeminiStructuredParser
from app.services.normalizer import normalize_candidate
from app.services.parser_orchestrator import ParserOptions, ParserOrchestrator


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def test_normalize_candidate_infers_city_from_address():
    extraction = CandidateExtraction(
        full_name=ExtractedField(value="Nguyen Tung", confidence=0.9),
        primary_email=ExtractedField(value="tung@example.com", confidence=0.9),
        primary_phone=ExtractedField(value="0901234567", confidence=0.9),
        date_of_birth=ExtractedField(value=None, confidence=0.0),
        address=ExtractedField(value="123 Nguyen Trai, Thanh Xuan, Ha Noi", confidence=0.88),
        summary=ExtractedField(value="Backend engineer with RAG experience", confidence=0.7),
        current_title=ExtractedField(value="Backend Engineer", confidence=0.84),
        current_company=ExtractedField(value="G Link", confidence=0.8),
        skills=[],
        experiences=[],
        educations=[],
        projects=[],
        social_links=[],
        sections_detected=["header"],
    )

    normalized = normalize_candidate(extraction)

    assert normalized["city"] == "ha noi"
    assert "ha noi" in normalized["searchable_text"]
    assert "ha noi" in normalized["vector_metadata"]["locations"]


def test_parser_orchestrator_falls_back_to_local_when_gemini_quota_exhausted():
    def requester(url, headers, json, timeout):
        return _FakeResponse(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}})

    orchestrator = ParserOrchestrator(gemini_parser=GeminiStructuredParser(requester=requester))
    options = ParserOptions.from_inputs(parser_strategy="gemini_first", gemini_api_key="demo-key", gemini_model="gemini-2.5-flash")
    raw_text = """
    NGUYEN TUNG
    AI ENGINEER
    Email: tung@example.com
    Phone: 0901234567
    Address: Ha Noi

    SKILLS
    Python, FastAPI, RAG
    """

    extraction, audit, normalized = orchestrator.parse_and_normalize(
        raw_text,
        filename="cv_nguyen_tung.pdf",
        parser_meta={"parser": "plain-text"},
        options=options,
    )

    assert extraction.full_name.value == "NGUYEN TUNG"
    assert normalized["primary_email"] == "tung@example.com"
    assert "gemini_fallback_to_local" in audit.parse_flags
    assert "gemini_quota_exhausted" in audit.parse_flags
    assert audit.extractor_backend.endswith("+local_fallback")


def test_parser_orchestrator_merges_gemini_output_with_local_parser():
    gemini_payload = {
        "full_name": {"value": "Nguyen Tung", "confidence": 0.97, "evidence_text": "Nguyen Tung"},
        "primary_email": {"value": None, "confidence": 0.0, "evidence_text": None},
        "primary_phone": {"value": None, "confidence": 0.0, "evidence_text": None},
        "date_of_birth": {"value": None, "confidence": 0.0, "evidence_text": None},
        "address": {"value": "Quan 1, Ho Chi Minh", "confidence": 0.84, "evidence_text": "Quan 1, Ho Chi Minh"},
        "city": {"value": "ho chi minh", "confidence": 0.95, "evidence_text": "Ho Chi Minh"},
        "summary": {"value": "AI engineer focused on agentic workflows", "confidence": 0.88, "evidence_text": "AI engineer focused on agentic workflows"},
        "current_title": {"value": "AI Engineer", "confidence": 0.91, "evidence_text": "AI Engineer"},
        "current_company": {"value": "G Link", "confidence": 0.86, "evidence_text": "G Link"},
        "skills": [
            {"raw_skill": "LangGraph", "normalized_skill": "langgraph"},
            {"raw_skill": "Qdrant", "normalized_skill": "qdrant"},
        ],
        "experiences": [],
        "educations": [],
        "projects": [],
        "social_links": [],
    }

    def requester(url, headers, json, timeout):
        return _FakeResponse(
            200,
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": json_module.dumps(gemini_payload, ensure_ascii=False)}
                            ]
                        }
                    }
                ]
            },
        )

    # avoid shadowing parameter name inside requester closure
    json_module = json
    orchestrator = ParserOrchestrator(gemini_parser=GeminiStructuredParser(requester=requester))
    options = ParserOptions.from_inputs(parser_strategy="gemini_first", gemini_api_key="demo-key", gemini_model="gemini-2.5-flash")
    raw_text = """
    Email: tung@example.com
    Phone: 0901234567

    SKILLS
    Python, FastAPI, RAG
    """

    extraction, audit, normalized = orchestrator.parse_and_normalize(
        raw_text,
        filename="cv.pdf",
        parser_meta={"parser": "plain-text"},
        options=options,
    )

    assert extraction.full_name.value == "Nguyen Tung"
    assert normalized["primary_email"] == "tung@example.com"
    assert normalized["city"] == "ho chi minh"
    assert {"python", "fastapi", "rag", "langgraph", "qdrant"}.issubset(set(normalized["normalized_skills"]))
    assert audit.extractor_backend == "gemini_structured_with_local_backfill"
    assert "gemini_success" in audit.parse_flags
    assert "hybrid_field_backfill" in audit.parse_flags
