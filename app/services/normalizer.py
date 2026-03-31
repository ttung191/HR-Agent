from __future__ import annotations

from collections import defaultdict

from app.schemas.candidate import CandidateExtraction
from app.services.date_utils import months_between, parse_date_point, safe_total_experience_months
from app.services.taxonomy import DEGREE_ALIASES, LOCATION_ALIASES, ROLE_ALIASES, SKILL_ALIASES, SKILL_FAMILIES


def normalize_text(value: str | None) -> str | None:
    return value.strip() if value else None


def canonical_skill(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    return SKILL_ALIASES.get(lowered, lowered)


def canonical_role(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.lower()
    for canonical, aliases in ROLE_ALIASES.items():
        if canonical in lowered or any(alias in lowered for alias in aliases):
            return canonical
    return value.strip()


def canonical_location(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.lower()
    for canonical, aliases in LOCATION_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            return canonical
    return value.strip()


def canonical_degree(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.lower()
    for canonical, aliases in DEGREE_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            return canonical
    return value.strip()


def compute_confidence(extraction: CandidateExtraction, normalized_skills: list[str], total_years: float | None) -> float:
    base = 0.0
    fields = [
        extraction.full_name.confidence,
        max(extraction.primary_email.confidence, extraction.primary_phone.confidence),
        extraction.summary.confidence,
        extraction.current_title.confidence,
    ]
    if fields:
        base += sum(fields) / len(fields)

    if normalized_skills:
        base += min(len(normalized_skills), 12) * 0.015

    if extraction.experiences:
        base += min(len(extraction.experiences), 5) * 0.03

    if total_years is not None:
        base += 0.08

    if extraction.sections_detected:
        base += min(len(extraction.sections_detected), 6) * 0.01

    return round(min(base, 0.99), 3)


def build_searchable_text(
    full_name: str | None,
    summary: str | None,
    current_title: str | None,
    current_company: str | None,
    address: str | None,
    skills: list[str],
    experiences: list[dict],
    projects: list[dict],
    educations: list[dict],
) -> str:
    parts = [
        full_name,
        summary,
        current_title,
        current_company,
        address,
        " ".join(skills),
        " ".join(filter(None, [(exp.get("title") or "") + " " + (exp.get("company") or "") + " " + (exp.get("description") or "") for exp in experiences])),
        " ".join(filter(None, [(proj.get("name") or "") + " " + (proj.get("description") or "") + " " + " ".join(proj.get("technologies") or []) for proj in projects])),
        " ".join(filter(None, [(edu.get("school") or "") + " " + (edu.get("degree") or "") + " " + (edu.get("major") or "") for edu in educations])),
    ]
    return " ".join(filter(None, parts)).lower()


def normalize_candidate(extraction: CandidateExtraction) -> dict:
    raw_skills = extraction.skills or []
    normalized_skills = sorted(
        {
            canonical_skill(item.normalized_skill or item.raw_skill)
            for item in raw_skills
            if canonical_skill(item.normalized_skill or item.raw_skill)
        }
    )

    skills_by_family: dict[str, list[str]] = defaultdict(list)
    for skill in normalized_skills:
        family = SKILL_FAMILIES.get(skill, "other")
        skills_by_family[family].append(skill)

    normalized_experiences = []
    total_months = safe_total_experience_months(
        [(exp.start_date, exp.end_date) for exp in extraction.experiences]
    )

    current_title = canonical_role(extraction.current_title.value)
    current_company = normalize_text(extraction.current_company.value)

    for exp in extraction.experiences:
        start = parse_date_point(exp.start_date)
        end = parse_date_point(exp.end_date)
        inferred_months = months_between(start, end) if start and end else None

        title = canonical_role(exp.title)
        company = normalize_text(exp.company)
        location = canonical_location(exp.location)

        if not current_title and title:
            current_title = title
        if not current_company and company:
            current_company = company

        normalized_experiences.append(
            {
                **exp.model_dump(),
                "title": title,
                "company": company,
                "location": location,
                "inferred_months": inferred_months,
            }
        )

    normalized_educations = []
    for edu in extraction.educations:
        normalized_educations.append(
            {
                **edu.model_dump(),
                "degree": canonical_degree(edu.degree),
            }
        )

    normalized_projects = [proj.model_dump() for proj in extraction.projects]
    links = [link.model_dump() for link in extraction.social_links]

    total_years = round(total_months / 12.0, 2) if total_months > 0 else None
    confidence = compute_confidence(extraction, normalized_skills, total_years)

    review_reasons = []
    if not extraction.full_name.value:
        review_reasons.append("missing_full_name")
    if not extraction.primary_email.value and not extraction.primary_phone.value:
        review_reasons.append("missing_contact_info")
    if not normalized_skills:
        review_reasons.append("missing_skills")
    if total_years is None:
        review_reasons.append("missing_experience_duration")
    if confidence < 0.65:
        review_reasons.append("low_confidence")

    searchable_text = build_searchable_text(
        full_name=extraction.full_name.value,
        summary=extraction.summary.value,
        current_title=current_title,
        current_company=current_company,
        address=canonical_location(extraction.address.value) or extraction.address.value,
        skills=normalized_skills,
        experiences=normalized_experiences,
        projects=normalized_projects,
        educations=normalized_educations,
    )

    return {
        "full_name": normalize_text(extraction.full_name.value),
        "primary_email": normalize_text(extraction.primary_email.value),
        "primary_phone": normalize_text(extraction.primary_phone.value),
        "date_of_birth": normalize_text(extraction.date_of_birth.value),
        "address": canonical_location(extraction.address.value) or normalize_text(extraction.address.value),
        "summary": normalize_text(extraction.summary.value),
        "current_title": current_title,
        "current_company": current_company,
        "normalized_skills": normalized_skills,
        "skills_by_family": dict(skills_by_family),
        "experience": normalized_experiences,
        "education": normalized_educations,
        "projects": normalized_projects,
        "social_links": links,
        "total_years_experience": total_years,
        "searchable_text": searchable_text,
        "confidence_score": confidence,
        "review_reasons": review_reasons,
    }