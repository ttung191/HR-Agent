from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from app.services.taxonomy import GENERIC_FILENAME_TOKENS, JOB_TITLE_TOKENS, SECTION_ALIASES, SKILL_ALIASES

_WORD_RE = re.compile(r"[A-Za-zÀ-ỹ]+", re.UNICODE)
_FILENAME_SPLIT_RE = re.compile(r"[^A-Za-zÀ-ỹ]+", re.UNICODE)
_LEADING_ICON_RE = re.compile(r"^[^0-9A-Za-zÀ-ỹ]+", re.UNICODE)

HUMAN_NAME_BLOCKLIST = {
    "hiện",
    "tại",
    "current",
    "present",
    "today",
    "resume",
    "cv",
    "profile",
    "data",
    "engineer",
    "developer",
    "scientist",
    "analyst",
    "backend",
    "frontend",
    "fullstack",
    "intern",
    "fresher",
    "senior",
    "junior",
    "python",
    "sql",
    "spark",
    "etl",
    "skills",
    "experience",
    "education",
    "projects",
    "kinh",
    "nghiệm",
    "học",
    "vấn",
    "kỹ",
    "năng",
    "điện",
    "thoại",
    "email",
    "giới",
    "tính",
}


@dataclass(slots=True)
class CVClassification:
    document_type: str
    parser_mode: str
    quality_score: float
    tech_signal_score: float
    parse_flags: list[str] = field(default_factory=list)
    detected_sections: list[str] = field(default_factory=list)


class CVClassifier:
    def classify(self, raw_text: str, sections: dict[str, str]) -> CVClassification:
        lowered = raw_text.lower()
        detected_sections = sorted(set(sections.keys()))
        parse_flags: list[str] = []

        has_contact = any(token in lowered for token in ["@", "linkedin", "github", "tel", "+84", "gmail", "điện thoại", "email:"])
        tech_hits = self._count_hits(lowered, SKILL_ALIASES.keys())
        section_hits = sum(1 for key in ["summary", "skills", "experience", "education", "projects"] if sections.get(key))
        looks_like_cv = has_contact and section_hits >= 2

        if not looks_like_cv and len(raw_text.strip()) < 160:
            return CVClassification(
                document_type="non_cv",
                parser_mode="fallback",
                quality_score=0.18,
                tech_signal_score=0.0,
                parse_flags=["not_enough_cv_signals", "too_little_text"],
                detected_sections=detected_sections,
            )

        tech_signal_score = min(tech_hits / 8.0, 1.0)
        heading_coverage = min(section_hits / 4.0, 1.0)
        text_quality = min(len(raw_text.strip()) / 2200.0, 1.0)
        quality_score = round(0.45 * heading_coverage + 0.30 * tech_signal_score + 0.25 * text_quality, 3)

        if section_hits >= 3 and tech_hits >= 4:
            document_type = "tech_cv"
            parser_mode = "strict"
        elif looks_like_cv:
            document_type = "general_cv"
            parser_mode = "fallback"
        else:
            document_type = "uncertain"
            parser_mode = "fallback"

        if document_type != "tech_cv":
            parse_flags.append("weak_tech_cv_signals")
        if section_hits < 3:
            parse_flags.append("limited_section_coverage")
        if len(raw_text.strip()) < 500:
            parse_flags.append("short_document")

        return CVClassification(
            document_type=document_type,
            parser_mode=parser_mode,
            quality_score=quality_score,
            tech_signal_score=round(tech_signal_score, 3),
            parse_flags=parse_flags,
            detected_sections=detected_sections,
        )

    @staticmethod
    def _count_hits(text: str, patterns: Iterable[str]) -> int:
        hits = 0
        seen: set[str] = set()
        for pattern in patterns:
            if pattern in seen:
                continue
            if re.search(rf"(?<!\w){re.escape(pattern)}(?!\w)", text):
                seen.add(pattern)
                hits += 1
        return hits


def normalize_filename_stem(filename: str) -> str:
    stem = Path(filename or "").stem
    stem = stem.replace("_", " ").replace("-", " ")
    return " ".join(stem.split())


def filename_tokens(filename: str) -> list[str]:
    stem = normalize_filename_stem(filename).lower()
    return [token for token in _FILENAME_SPLIT_RE.split(stem) if token]


def is_generic_filename(filename: str) -> bool:
    tokens = filename_tokens(filename)
    if not tokens:
        return True
    generic_hits = sum(1 for token in tokens if token in GENERIC_FILENAME_TOKENS)
    return generic_hits >= max(1, len(tokens) // 2)


def filename_to_person_name(filename: str) -> str | None:
    tokens = filename_tokens(filename)
    if len(tokens) < 2:
        return None
    if any(token in GENERIC_FILENAME_TOKENS for token in tokens):
        return None
    if any(token in JOB_TITLE_TOKENS for token in tokens):
        return None
    if any(token in HUMAN_NAME_BLOCKLIST for token in tokens):
        return None
    if any(len(token) == 1 for token in tokens):
        return None
    return " ".join(token.title() for token in tokens[:5])


def looks_like_human_name(value: str | None) -> bool:
    if not value:
        return False

    cleaned = " ".join(value.strip().split())
    cleaned = _LEADING_ICON_RE.sub("", cleaned).strip()
    if len(cleaned) < 4 or len(cleaned) > 60:
        return False
    if any(char.isdigit() for char in cleaned):
        return False
    if "@" in cleaned or "http" in cleaned.lower():
        return False

    words = _WORD_RE.findall(cleaned)
    if not (2 <= len(words) <= 6):
        return False

    lowered_words = [word.lower() for word in words]
    if any(word in JOB_TITLE_TOKENS for word in lowered_words):
        return False
    if any(word in GENERIC_FILENAME_TOKENS for word in lowered_words):
        return False
    if any(word in HUMAN_NAME_BLOCKLIST for word in lowered_words):
        return False

    uppercase_like_ratio = sum(1 for word in words if word[:1].isupper() or word.isupper()) / max(len(words), 1)
    if uppercase_like_ratio < 0.75:
        return False

    return True


def _ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalized_heading_token(value: str) -> str:
    clean = " ".join(value.split())
    clean = _LEADING_ICON_RE.sub("", clean)
    clean = _ascii_fold(clean)
    return clean.lower().strip(" :-•|\t")


def is_section_heading(value: str) -> bool:
    token = normalized_heading_token(value)
    return token in SECTION_ALIASES or token in {alias for aliases in SECTION_ALIASES.values() for alias in aliases}