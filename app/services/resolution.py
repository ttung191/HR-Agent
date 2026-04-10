from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FieldCandidate:
    value: str | None
    confidence: float
    source_section: str | None = None
    extraction_method: str | None = None
    evidence_text: str | None = None
    priority: int = 100
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SkillCandidate:
    alias: str
    normalized_skill: str
    source_section: str
    start: int
    end: int
    confidence: float
    evidence_text: str | None = None
    priority: int = 100
    scope: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


_FIELD_SECTION_PRIORITY = {
    "header": 0,
    "summary": 1,
    "experience": 2,
    "projects": 3,
    "education": 4,
    "filename": 5,
}

_SKILL_SECTION_PRIORITY = {
    "skills": 0,
    "projects": 1,
    "experience": 2,
    "summary": 3,
    "header": 4,
}


def _normalized_value(value: str | None) -> str:
    return " ".join((value or "").split()).strip().lower()


def _field_quality_bonus(label: str, candidate: FieldCandidate) -> float:
    value = " ".join((candidate.value or "").split()).strip()
    if not value:
        return -1.0

    bonus = 0.0
    word_count = len(value.split())
    lowered = value.lower()

    if label == "full_name":
        if 2 <= word_count <= 4:
            bonus += 0.08
        if value.isupper() or value.istitle():
            bonus += 0.03
        if any(token in value for token in ["|", "@", "http"]):
            bonus -= 0.15

    if label in {"current_title", "current_company"}:
        if 1 <= word_count <= 7:
            bonus += 0.04
        if any(token in lowered for token in ["email", "điện thoại", "phone", "date of birth", "giới tính"]):
            bonus -= 0.35
        if any(token in value for token in ["|", "@", "http"]):
            bonus -= 0.18

    if label == "summary":
        if 12 <= word_count <= 60:
            bonus += 0.08
        if len(value) > 380:
            bonus -= 0.10
        if any(token in lowered for token in ["topcv", "tuyendung", "nền tảng tuyển dụng"]):
            bonus -= 0.35

    if label == "address":
        if any(token in lowered for token in ["địa chỉ", "street", "district", "quận", "phường", "ward", "ngõ", "road"]):
            bonus += 0.08

    if label == "primary_email":
        if "@" in value and "." in value:
            bonus += 0.05

    return bonus


def resolve_field_candidates(
    label: str,
    candidates: list[FieldCandidate],
    *,
    min_confidence: float = 0.0,
) -> tuple[FieldCandidate | None, list[dict[str, Any]]]:
    usable = [
        candidate
        for candidate in candidates
        if candidate.value and candidate.confidence >= min_confidence
    ]

    deduped: dict[str, FieldCandidate] = {}
    for candidate in usable:
        key = _normalized_value(candidate.value)
        previous = deduped.get(key)
        if previous is None:
            deduped[key] = candidate
            continue

        previous_score = previous.confidence + _field_quality_bonus(label, previous)
        current_score = candidate.confidence + _field_quality_bonus(label, candidate)
        if (
            candidate.priority,
            -current_score,
            -len(candidate.value or ""),
        ) < (
            previous.priority,
            -previous_score,
            -len(previous.value or ""),
        ):
            deduped[key] = candidate

    ranked = sorted(
        deduped.values(),
        key=lambda candidate: (
            candidate.priority,
            _FIELD_SECTION_PRIORITY.get(candidate.source_section or "", 99),
            -(candidate.confidence + _field_quality_bonus(label, candidate)),
            -len(candidate.value or ""),
            _normalized_value(candidate.value),
        ),
    )

    trace: list[dict[str, Any]] = []
    selected = ranked[0] if ranked else None
    for index, candidate in enumerate(ranked):
        trace.append(
            {
                "value": candidate.value,
                "confidence": round(candidate.confidence, 3),
                "source_section": candidate.source_section,
                "extraction_method": candidate.extraction_method,
                "priority": candidate.priority,
                "status": "selected" if index == 0 else "suppressed",
                "reason": "highest_ranked_candidate" if index == 0 else "lower_ranked_conflict",
            }
        )
    return selected, trace


def _spans_overlap(left: SkillCandidate, right: SkillCandidate) -> bool:
    if left.scope != right.scope:
        return False
    return max(left.start, right.start) < min(left.end, right.end)


def resolve_skill_candidates(candidates: list[SkillCandidate]) -> tuple[list[SkillCandidate], list[dict[str, Any]]]:
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            candidate.priority,
            _SKILL_SECTION_PRIORITY.get(candidate.source_section, 99),
            -candidate.confidence,
            -(candidate.end - candidate.start),
            candidate.start,
            candidate.normalized_skill,
        ),
    )

    selected: list[SkillCandidate] = []
    trace: list[dict[str, Any]] = []

    for candidate in ranked:
        suppressed_reason: str | None = None
        for kept in selected:
            if candidate.normalized_skill == kept.normalized_skill:
                suppressed_reason = f"duplicate_of:{kept.normalized_skill}"
                break
            if _spans_overlap(candidate, kept):
                suppressed_reason = f"overlap_with:{kept.normalized_skill}"
                break

        if suppressed_reason:
            trace.append(
                {
                    "alias": candidate.alias,
                    "normalized_skill": candidate.normalized_skill,
                    "source_section": candidate.source_section,
                    "confidence": round(candidate.confidence, 3),
                    "status": "suppressed",
                    "reason": suppressed_reason,
                }
            )
            continue

        selected.append(candidate)
        trace.append(
            {
                "alias": candidate.alias,
                "normalized_skill": candidate.normalized_skill,
                "source_section": candidate.source_section,
                "confidence": round(candidate.confidence, 3),
                "status": "selected",
                "reason": "highest_ranked_skill_candidate",
            }
        )

    return selected, trace