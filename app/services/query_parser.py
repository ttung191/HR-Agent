from __future__ import annotations

import re

from app.schemas.candidate import QueryPlan
from app.services.taxonomy import ACADEMIC_KEYWORDS, DEGREE_ALIASES, LOCATION_ALIASES, ROLE_ALIASES, SKILL_ALIASES

YEARS_RE = re.compile(r"(\d+(?:[\.,]\d+)?)\s*(?:\+)?\s*(?:years?|yrs?|năm)", re.I)
NICE_HINTS = ["nice to have", "plus", "ưu tiên", "bonus", "preferred", "optional"]
DOMAIN_HINTS = ["banking", "fintech", "ecommerce", "healthcare", "logistics", "hrtech", "saas"]
CLAUSE_SPLIT_RE = re.compile(r"[\n,;]|\bbut\b|\bhowever\b|\bwith\b", re.I)


def _contains_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


class QueryPlanner:
    def plan(self, query: str) -> QueryPlan:
        lowered = query.lower().strip()
        years_match = YEARS_RE.search(lowered)
        minimum_years = float(years_match.group(1).replace(",", ".")) if years_match else None

        must_have_skills: list[str] = []
        nice_to_have_skills: list[str] = []
        for clause in [chunk.strip() for chunk in CLAUSE_SPLIT_RE.split(lowered) if chunk.strip()]:
            clause_is_nice = _contains_any(clause, NICE_HINTS)
            for alias, normalized in SKILL_ALIASES.items():
                if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", clause):
                    bucket = nice_to_have_skills if clause_is_nice else must_have_skills
                    if normalized not in bucket:
                        bucket.append(normalized)

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
        for canonical, aliases in ACADEMIC_KEYWORDS.items():
            if any(alias in lowered for alias in aliases) and canonical not in degree_keywords:
                degree_keywords.append(canonical)

        domain_keywords = [token for token in DOMAIN_HINTS if token in lowered]
        stopwords = {
            "co",
            "có",
            "va",
            "và",
            "biết",
            "with",
            "and",
            "or",
            "hoặc",
            "là",
            "kinh",
            "nghiệm",
            "experience",
            "year",
            "years",
            "yrs",
            "năm",
            "ứng",
            "viên",
            "candidate",
            "can",
            "cần",
            "tim",
            "tìm",
            "minimum",
            "toi",
            "thiểu",
            "ưu",
            "tiên",
            "preferred",
        }
        query_text_terms = [
            token
            for token in re.findall(r"[a-zA-ZÀ-ỹ0-9+#.-]+", lowered)
            if token not in stopwords and len(token) > 1
        ]

        return QueryPlan(
            original_query=query,
            role_keywords=sorted(set(role_keywords)),
            must_have_skills=sorted(set(must_have_skills)),
            nice_to_have_skills=sorted(set(skill for skill in nice_to_have_skills if skill not in must_have_skills)),
            minimum_years_experience=minimum_years,
            location_keywords=sorted(set(location_keywords)),
            degree_keywords=sorted(set(degree_keywords)),
            domain_keywords=sorted(set(domain_keywords)),
            query_text_terms=query_text_terms,
        )