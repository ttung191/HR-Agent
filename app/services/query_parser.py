from __future__ import annotations

import re

from app.schemas.candidate import QueryPlan
from app.services.taxonomy import DEGREE_ALIASES, LOCATION_ALIASES, ROLE_ALIASES, SKILL_ALIASES

YEARS_RE = re.compile(r"(\d+(?:[\.,]\d+)?)\s*(?:\+)?\s*(?:years?|yrs?|năm)", re.I)

NICE_HINTS = [
    "nice to have", "plus", "ưu tiên", "bonus", "preferred",
]

DOMAIN_HINTS = [
    "banking", "fintech", "ecommerce", "healthcare", "logistics",
]


def _contains_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


class QueryPlanner:
    def plan(self, query: str) -> QueryPlan:
        lowered = query.lower().strip()

        years_match = YEARS_RE.search(lowered)
        minimum_years = float(years_match.group(1).replace(",", ".")) if years_match else None

        must_have_skills: list[str] = []
        nice_to_have_skills: list[str] = []

        for alias, normalized in SKILL_ALIASES.items():
            if alias not in lowered:
                continue
            if _contains_any(lowered, NICE_HINTS):
                if normalized not in nice_to_have_skills:
                    nice_to_have_skills.append(normalized)
            else:
                if normalized not in must_have_skills:
                    must_have_skills.append(normalized)

        role_keywords: list[str] = []
        for canonical, aliases in ROLE_ALIASES.items():
            if canonical in lowered or any(alias in lowered for alias in aliases):
                role_keywords.append(canonical)

        location_keywords: list[str] = []
        for canonical, aliases in LOCATION_ALIASES.items():
            if any(alias in lowered for alias in aliases):
                location_keywords.append(canonical)

        degree_keywords: list[str] = []
        for canonical, aliases in DEGREE_ALIASES.items():
            if any(alias in lowered for alias in aliases):
                degree_keywords.append(canonical)

        domain_keywords = [token for token in DOMAIN_HINTS if token in lowered]

        stopwords = {
            "co", "có", "va", "và", "biết", "with", "and", "or", "hoặc", "là",
            "kinh", "nghiệm", "experience", "year", "years", "yrs", "năm",
            "ứng", "viên", "candidate", "can", "cần", "tim", "tìm",
        }
        query_text_terms = [
            token for token in re.findall(r"[a-zA-ZÀ-ỹ0-9+#.-]+", lowered)
            if token not in stopwords and len(token) > 1
        ]

        return QueryPlan(
            original_query=query,
            role_keywords=sorted(set(role_keywords)),
            must_have_skills=sorted(set(must_have_skills)),
            nice_to_have_skills=sorted(set(nice_to_have_skills)),
            minimum_years_experience=minimum_years,
            location_keywords=sorted(set(location_keywords)),
            degree_keywords=sorted(set(degree_keywords)),
            domain_keywords=sorted(set(domain_keywords)),
            query_text_terms=query_text_terms,
        )