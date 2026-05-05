from __future__ import annotations

import json
from typing import Any

import requests

from app.core.config import get_settings
from app.schemas.candidate import (
    CandidateExtraction,
    EducationItem,
    ExperienceItem,
    ExtractedField,
    LinkItem,
    ProjectItem,
    SkillItem,
)
from app.services.normalizer import canonical_skill
from app.services.taxonomy import SKILL_FAMILIES


class GeminiParserError(Exception):
    pass


class GeminiQuotaExceededError(GeminiParserError):
    pass


class GeminiStructuredParser:
    def __init__(self, requester: Any | None = None) -> None:
        self.settings = get_settings()
        self.requester = requester or requests.post

    def parse(
        self,
        raw_text: str,
        *,
        filename: str,
        parser_meta: dict[str, Any] | None,
        api_key: str,
        model: str | None = None,
    ) -> CandidateExtraction:
        if not api_key:
            raise GeminiParserError("Missing Gemini API key")

        response = self.requester(
            self._build_url(model or self.settings.gemini_model),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json=self._build_payload(raw_text=raw_text, filename=filename, parser_meta=parser_meta or {}),
            timeout=self.settings.gemini_timeout_seconds,
        )
        data = self._safe_json(response)
        self._raise_for_errors(response, data)
        output_text = self._extract_text_payload(data)
        if not output_text:
            raise GeminiParserError("Gemini returned an empty body")
        try:
            payload = json.loads(output_text)
        except json.JSONDecodeError as exc:  # pragma: no cover - exercised through generic fallback path
            raise GeminiParserError(f"Gemini returned invalid JSON: {exc}") from exc
        return self._to_candidate_extraction(payload)

    def _build_url(self, model: str) -> str:
        base_url = self.settings.gemini_api_base_url.rstrip("/")
        return f"{base_url}/models/{model}:generateContent"

    def _build_payload(self, *, raw_text: str, filename: str, parser_meta: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(raw_text=raw_text, filename=filename, parser_meta=parser_meta)
        return {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
                "responseJsonSchema": self._schema(),
            },
        }

    def _build_prompt(self, *, raw_text: str, filename: str, parser_meta: dict[str, Any]) -> str:
        layout_lines = parser_meta.get("first_page_layout_lines") or []
        layout_preview = "\n".join(str(item.get("text", "")).strip() for item in layout_lines[:25] if str(item.get("text", "")).strip())
        clipped_text = self._truncate_text(raw_text)
        return (
            "You are a strict CV parser. Extract only information that is explicitly supported by the CV text. "
            "Do not invent missing values. Return JSON only, with no markdown fences. "
            "For city, prefer the city or province from the address or latest work location. "
            "For skills, keep only professional or technical skills. Deduplicate aggressively.\n\n"
            f"Filename: {filename}\n\n"
            f"Header layout preview:\n{layout_preview or '(none)'}\n\n"
            f"CV text:\n{clipped_text}"
        )

    def _truncate_text(self, raw_text: str) -> str:
        limit = max(self.settings.gemini_max_raw_text_chars, 4000)
        text = raw_text.strip()
        if len(text) <= limit:
            return text
        head = text[: int(limit * 0.72)].strip()
        tail = text[-int(limit * 0.22) :].strip()
        return f"{head}\n\n[TRUNCATED FOR TOKEN BUDGET]\n\n{tail}"

    def _schema(self) -> dict[str, Any]:
        field_schema = {
            "type": "object",
            "properties": {
                "value": {"type": ["string", "null"]},
                "confidence": {"type": ["number", "null"]},
                "evidence_text": {"type": ["string", "null"]},
            },
            "required": ["value", "confidence", "evidence_text"],
        }
        return {
            "type": "object",
            "properties": {
                "full_name": field_schema,
                "primary_email": field_schema,
                "primary_phone": field_schema,
                "date_of_birth": field_schema,
                "address": field_schema,
                "city": field_schema,
                "summary": field_schema,
                "current_title": field_schema,
                "current_company": field_schema,
                "skills": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "raw_skill": {"type": "string"},
                            "normalized_skill": {"type": "string"},
                        },
                        "required": ["raw_skill", "normalized_skill"],
                    },
                },
                "experiences": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": ["string", "null"]},
                            "company": {"type": ["string", "null"]},
                            "location": {"type": ["string", "null"]},
                            "start_date": {"type": ["string", "null"]},
                            "end_date": {"type": ["string", "null"]},
                            "employment_type": {"type": ["string", "null"]},
                            "description": {"type": ["string", "null"]},
                        },
                        "required": ["title", "company", "location", "start_date", "end_date", "employment_type", "description"],
                    },
                },
                "educations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "school": {"type": ["string", "null"]},
                            "degree": {"type": ["string", "null"]},
                            "major": {"type": ["string", "null"]},
                            "start_date": {"type": ["string", "null"]},
                            "end_date": {"type": ["string", "null"]},
                            "description": {"type": ["string", "null"]},
                        },
                        "required": ["school", "degree", "major", "start_date", "end_date", "description"],
                    },
                },
                "projects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": ["string", "null"]},
                            "role": {"type": ["string", "null"]},
                            "start_date": {"type": ["string", "null"]},
                            "end_date": {"type": ["string", "null"]},
                            "description": {"type": ["string", "null"]},
                            "technologies": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["name", "role", "start_date", "end_date", "description", "technologies"],
                    },
                },
                "social_links": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": ["string", "null"]},
                            "url": {"type": "string"},
                        },
                        "required": ["label", "url"],
                    },
                },
            },
            "required": [
                "full_name",
                "primary_email",
                "primary_phone",
                "date_of_birth",
                "address",
                "city",
                "summary",
                "current_title",
                "current_company",
                "skills",
                "experiences",
                "educations",
                "projects",
                "social_links",
            ],
        }

    def _safe_json(self, response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
            return data if isinstance(data, dict) else {"raw": data}
        except Exception:
            return {"error_text": response.text}

    def _raise_for_errors(self, response: requests.Response, data: dict[str, Any]) -> None:
        if response.ok:
            return
        error = data.get("error") if isinstance(data, dict) else {}
        status = str((error or {}).get("status") or response.status_code).upper()
        message = str((error or {}).get("message") or data.get("error_text") or response.text)
        quota_hit = response.status_code == 429 or "RESOURCE_EXHAUSTED" in status or any(
            token in message.lower() for token in ["quota", "resource exhausted", "rate limit", "token"]
        )
        if quota_hit:
            raise GeminiQuotaExceededError(message)
        raise GeminiParserError(message)

    def _extract_text_payload(self, data: dict[str, Any]) -> str:
        candidates = data.get("candidates") or []
        for candidate in candidates:
            parts = (((candidate or {}).get("content") or {}).get("parts") or [])
            for part in parts:
                text = part.get("text")
                if text:
                    return str(text)
        return ""

    def _coerce_field(self, payload: Any, *, method: str) -> ExtractedField:
        if isinstance(payload, dict):
            value = payload.get("value")
            confidence = float(payload.get("confidence") or 0.0)
            evidence_text = payload.get("evidence_text")
        else:
            value = payload if isinstance(payload, str) else None
            confidence = 0.0
            evidence_text = None
        if value is not None:
            value = str(value).strip() or None
        return ExtractedField(
            value=value,
            confidence=max(min(confidence or 0.0, 0.98), 0.0),
            evidence_text=evidence_text,
            source_section="llm",
            extraction_method=method if value else "not_found",
        )

    def _to_candidate_extraction(self, payload: dict[str, Any]) -> CandidateExtraction:
        skills: list[SkillItem] = []
        for item in payload.get("skills") or []:
            raw_skill = str((item or {}).get("raw_skill") or "").strip()
            normalized = canonical_skill((item or {}).get("normalized_skill") or raw_skill)
            if not raw_skill and not normalized:
                continue
            normalized = normalized or raw_skill.lower()
            skills.append(
                SkillItem(
                    raw_skill=raw_skill or normalized,
                    normalized_skill=normalized,
                    skill_family=SKILL_FAMILIES.get(normalized),
                    source_section="llm",
                    evidence_text=None,
                )
            )

        return CandidateExtraction(
            full_name=self._coerce_field(payload.get("full_name"), method="gemini_structured"),
            primary_email=self._coerce_field(payload.get("primary_email"), method="gemini_structured"),
            primary_phone=self._coerce_field(payload.get("primary_phone"), method="gemini_structured"),
            date_of_birth=self._coerce_field(payload.get("date_of_birth"), method="gemini_structured"),
            address=self._coerce_field(payload.get("address"), method="gemini_structured"),
            city=self._coerce_field(payload.get("city"), method="gemini_structured"),
            summary=self._coerce_field(payload.get("summary"), method="gemini_structured"),
            current_title=self._coerce_field(payload.get("current_title"), method="gemini_structured"),
            current_company=self._coerce_field(payload.get("current_company"), method="gemini_structured"),
            skills=skills,
            experiences=[ExperienceItem.model_validate(item or {}) for item in payload.get("experiences") or []],
            educations=[EducationItem.model_validate(item or {}) for item in payload.get("educations") or []],
            projects=[ProjectItem.model_validate(item or {}) for item in payload.get("projects") or []],
            social_links=[LinkItem.model_validate(item or {}) for item in payload.get("social_links") or [] if (item or {}).get("url")],
            sections_detected=["llm_structured"],
        )
