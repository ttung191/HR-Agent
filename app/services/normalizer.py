from __future__ import annotations

from collections import defaultdict
import re

from app.schemas.candidate import CandidateExtraction, ExtractionAudit, VectorMetadata
from app.services.date_utils import months_between, parse_date_point, safe_total_experience_months
from app.services.taxonomy import ACADEMIC_KEYWORDS, DEGREE_ALIASES, LOCATION_ALIASES, ROLE_ALIASES, SKILL_ALIASES, SKILL_FAMILIES

DEGREE_SENTENCE_RE = re.compile(r"\b(thesis|grade|gpa|course|certification|certificate|machine learning|data analysis|cloud platforms|neural networks)\b", re.I)
MAJOR_SPLIT_RE = re.compile(r"\b(?:major|programme|program|chuyên ngành|ngành|field of study)\s*[:：-]?\s*", re.I)
SCHOOL_SPLIT_RE = re.compile(r"^(Bachelor|Master|Doctor|PhD|Cử nhân|Thạc sĩ|Tiến sĩ)\b", re.I)


def normalize_text(value: str | None) -> str | None:
    if not value:
        return None
    text = " ".join(value.strip().split())
    text = text.strip(" ,;:-")
    return text or None


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


def infer_city(*values: str | None) -> str | None:
    for value in values:
        canonical = canonical_location(value)
        if canonical:
            return canonical
    return None


def canonical_degree(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.lower()
    for canonical, aliases in DEGREE_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            return canonical
    cleaned = normalize_text(value)
    if cleaned and DEGREE_SENTENCE_RE.search(cleaned):
        return None
    return cleaned


def canonical_major(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = normalize_text(MAJOR_SPLIT_RE.sub("", value))
    if not cleaned:
        return None
    lowered = cleaned.lower()
    for canonical, aliases in ACADEMIC_KEYWORDS.items():
        if any(alias in lowered for alias in aliases):
            return canonical
    cleaned = re.sub(r"\(gpa[^)]*\)", "", cleaned, flags=re.I).strip(" ,-|")
    return cleaned or None


def _looks_like_sentence(value: str | None) -> bool:
    if not value:
        return False
    token_count = len(value.split())
    return token_count >= 9 or value.strip().endswith(".")


def _looks_like_company_noise(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower().strip()
    return lowered in {"điện thoại", "phone", "email", "website", "contact", "nam", "nữ", "male", "female"}


def _looks_like_named_org(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return any(token in lowered for token in ["công ty", "company", "corp", "corporation", "bank", "shop", "university", "fss", "tnex", "edsolabs", "tekai", "quasoft", "mindx", "isofh"])


def _looks_like_course_or_certificate(item: dict) -> bool:
    school = (item.get("school") or "").lower()
    degree = (item.get("degree") or "").lower()
    major = (item.get("major") or "").lower()
    description = (item.get("description") or "").lower()
    text = " | ".join([school, degree, major, description])
    if any(token in school for token in ["university", "college", "institute", "academy", "đại học", "học viện", "cao đẳng"]):
        return False
    if degree in {"bachelor", "master", "phd"}:
        return False
    course_tokens = ["coursera", "w3school", "course", "khóa học", "khoa hoc", "certificate", "certification", "machine learning", "data analysis with python"]
    return any(token in text for token in course_tokens)


def _is_formal_education(item: dict) -> bool:
    school = (item.get("school") or "").lower()
    degree = (item.get("degree") or "").lower()
    major = (item.get("major") or "").lower()
    if _looks_like_course_or_certificate(item):
        return False
    if any(token in school for token in ["university", "college", "institute", "academy", "đại học", "học viện", "cao đẳng"]):
        return True
    if degree in {"bachelor", "master", "phd"}:
        return True
    if any(token in major for token in ["computer science", "information technology", "data science", "artificial intelligence", "applied mathematics"]):
        return True
    return False


def _blend(values: list[float]) -> float:
    usable = [value for value in values if value >= 0]
    return round(sum(usable) / len(usable), 3) if usable else 0.0


def _experience_is_training_or_noise(item: dict) -> bool:
    title = (item.get("title") or "").lower().strip()
    company = (item.get("company") or "").lower().strip()
    description = (item.get("description") or "").lower().strip()

    bad_titles = {
        "sinh viên",
        "student",
        "học viên",
        "hoc vien",
    }
    if title in bad_titles:
        return True
    if title.startswith("sinh viên") or title.startswith("học viên"):
        return True
    if not company and title in {"thực tập sinh", "intern"} and not description:
        return True
    if not title and not company and any(token in description for token in ["dự án cá nhân", "du an ca nhan", "kaggle", "dataset", "người hỗ trợ", "mentor"]):
        return True
    if company and any(token in company for token in ["học viện", "hoc vien", "university", "school"]) and title in {"student", "sinh viên", "học viên", "hoc vien"}:
        return True
    canonical = canonical_role(title) if title else None
    if len(title.split()) >= 7 and canonical == title:
        return True
    if any(token in title for token in ["dùng python", "sử dụng", "built", "performed", "designed system"]):
        return True
    if company in {"cafef", "youtube", "vietnamnet"}:
        return True
    if company and len(company.split()) > 10:
        return True
    location = (item.get("location") or "").strip().lower()
    if location and any(token in location for token in ["nhân viên", "quản lý", "chuyên viên", "kỹ sư", "manager", "engineer", "analyst", "scientist"]):
        return True
    return False


def _experience_key(item: dict) -> tuple[str, str, str, str]:
    return (
        (item.get("title") or "").lower().strip(),
        (item.get("company") or "").lower().strip(),
        (item.get("start_date") or "").strip(),
        (item.get("end_date") or "").strip(),
    )


def _education_key(item: dict) -> tuple[str, str, str, str]:
    return (
        (item.get("school") or "").lower().strip(),
        (item.get("degree") or "").lower().strip(),
        (item.get("major") or "").lower().strip(),
        f"{item.get('start_date') or ''}|{item.get('end_date') or ''}",
    )


def _split_school_and_degree(school: str | None, degree: str | None) -> tuple[str | None, str | None]:
    school = normalize_text(school)
    degree = normalize_text(degree)
    if school and SCHOOL_SPLIT_RE.match(school) and "," in school:
        left, right = [bit.strip() for bit in school.split(",", 1)]
        if canonical_degree(left):
            degree = degree or canonical_degree(left) or left
            school = right
    return school, degree


def _sanitize_education_entry(item: dict) -> dict:
    school = normalize_text(item.get("school"))
    degree = canonical_degree(item.get("degree"))
    major = canonical_major(item.get("major"))
    description = normalize_text(item.get("description"))

    school, degree = _split_school_and_degree(school, degree)

    if school and "," in school and not major:
        parts = [part.strip() for part in school.split(",") if part.strip()]
        if len(parts) >= 2 and canonical_major(parts[-1]):
            major = canonical_major(parts[-1])
            school = ", ".join(parts[:-1])

    if degree and DEGREE_SENTENCE_RE.search(degree):
        description = " | ".join(filter(None, [description, degree]))
        degree = None

    if major and DEGREE_SENTENCE_RE.search(major):
        description = " | ".join(filter(None, [description, major]))
        major = None

    if description and not major:
        for chunk in [bit.strip() for bit in description.split("|") if bit.strip()]:
            inferred_major = canonical_major(chunk)
            if inferred_major and inferred_major != degree and len(inferred_major.split()) <= 5:
                major = inferred_major
                break

    item.update({
        "school": school,
        "degree": degree,
        "major": major,
        "description": description,
    })
    return item


def _project_name_quality(name: str | None) -> float:
    if not name:
        return 0.0
    cleaned = normalize_text(name) or ""
    lowered = cleaned.lower()
    if len(cleaned.split()) <= 1:
        return 0.1
    if len(cleaned.split()) > 12:
        return 0.15
    if cleaned.endswith("."):
        return 0.2
    if any(token in lowered for token in ["objective", "manage", "conduct", "thesis", "lives in the nordic"]):
        return 0.2
    return 0.85


def _experience_quality(item: dict) -> float:
    score = 1.0
    title = (item.get("title") or "").strip()
    company = (item.get("company") or "").strip()
    description = (item.get("description") or "").lower()

    if not title and not company:
        score -= 0.55
    if title and _looks_like_sentence(title):
        score -= 0.35
    if company and (company.lower() in SKILL_ALIASES or not _looks_like_named_org(company)):
        score -= 0.30
    if not company and any(token in description for token in ["dự án cá nhân", "du an ca nhan", "kaggle", "dataset", "team member"]):
        score -= 0.35
    return max(0.0, min(score, 1.0))


def _education_quality(item: dict) -> float:
    score = 1.0
    if not item.get("school"):
        score -= 0.4
    if item.get("degree") is None:
        score -= 0.15
    if item.get("major") is None:
        score -= 0.10
    if _looks_like_course_or_certificate(item):
        score -= 0.35
    return max(0.0, min(score, 1.0))


def _dedupe_experiences(items: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        key = _experience_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    final_items: list[dict] = []
    for item in deduped:
        duplicate = False
        for kept in final_items:
            same_core = (item.get("title") or "").lower().strip() == (kept.get("title") or "").lower().strip() and (item.get("company") or "").lower().strip() == (kept.get("company") or "").lower().strip()
            same_dates = (item.get("start_date") or "") == (kept.get("start_date") or "") and (item.get("end_date") or "") == (kept.get("end_date") or "")
            if same_core and same_dates:
                duplicate = True
                if len(item.get("description") or "") > len(kept.get("description") or ""):
                    kept["description"] = item.get("description")
                break
        if not duplicate:
            final_items.append(item)
    return final_items


def _dedupe_educations(items: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        key = _education_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def compute_confidence(
    extraction: CandidateExtraction,
    audit: ExtractionAudit | None,
    normalized_skills: list[str],
    total_years: float | None,
    current_title: str | None,
    current_company: str | None,
) -> float:
    audit = audit or ExtractionAudit()
    name_conf = extraction.full_name.confidence
    if extraction.full_name.extraction_method == "filename_fallback":
        name_conf = min(name_conf, 0.28)

    contact_conf = max(extraction.primary_email.confidence, extraction.primary_phone.confidence)
    title_conf = extraction.current_title.confidence
    company_conf = 0.0 if _looks_like_company_noise(current_company) else extraction.current_company.confidence
    skills_conf = min(0.96, 0.45 + 0.05 * len(normalized_skills)) if normalized_skills else 0.0
    exp_quality = _blend([_experience_quality(item.model_dump()) for item in extraction.experiences]) if extraction.experiences else 0.0
    exp_conf = min(0.95, 0.38 + 0.12 * len(extraction.experiences)) * (0.45 + 0.55 * exp_quality) if extraction.experiences else 0.0
    edu_quality = _blend([_education_quality(item.model_dump()) for item in extraction.educations]) if extraction.educations else 0.0
    edu_conf = min(0.92, 0.42 + 0.16 * len(extraction.educations)) * (0.40 + 0.60 * edu_quality) if extraction.educations else 0.0
    project_quality = _blend([_project_name_quality(item.name) for item in extraction.projects]) if extraction.projects else 0.0
    project_conf = min(0.90, 0.40 + 0.12 * len(extraction.projects)) * (0.35 + 0.65 * project_quality) if extraction.projects else 0.0
    years_conf = 0.82 if total_years is not None else 0.0
    quality_conf = audit.cv_quality_score

    base = (
        0.24 * name_conf
        + 0.18 * contact_conf
        + 0.13 * title_conf
        + 0.06 * company_conf
        + 0.14 * skills_conf
        + 0.13 * exp_conf
        + 0.05 * edu_conf
        + 0.03 * project_conf
        + 0.02 * years_conf
        + 0.02 * quality_conf
    )

    if extraction.full_name.extraction_method == "filename_fallback":
        base -= 0.14
    if _looks_like_sentence(current_title):
        base -= 0.12
    if _looks_like_sentence(current_company):
        base -= 0.10
    if _looks_like_company_noise(current_company):
        base -= 0.20
    if exp_quality < 0.55 and extraction.experiences:
        base -= 0.18
    if edu_quality < 0.55 and extraction.educations:
        base -= 0.10
    if project_quality < 0.45 and len(extraction.projects) >= 2:
        base -= 0.12
    if audit.document_type == "non_cv":
        base -= 0.25
    return round(max(0.0, min(base, 0.99)), 3)


def build_searchable_text(
    full_name: str | None,
    summary: str | None,
    current_title: str | None,
    canonical_title: str | None,
    current_company: str | None,
    address: str | None,
    city: str | None,
    skills: list[str],
    experiences: list[dict],
    projects: list[dict],
    educations: list[dict],
) -> str:
    parts = [
        full_name,
        summary,
        current_title,
        canonical_title,
        current_company,
        address,
        city,
        " ".join(skills),
        " ".join(
            filter(
                None,
                [
                    (exp.get("title") or "")
                    + " "
                    + (exp.get("canonical_title") or "")
                    + " "
                    + (exp.get("company") or "")
                    + " "
                    + (exp.get("description") or "")
                    for exp in experiences
                ],
            )
        ),
        " ".join(
            filter(
                None,
                [
                    (proj.get("name") or "") + " " + (proj.get("role") or "") + " " + " ".join(proj.get("technologies") or []) + " " + (proj.get("description") or "")
                    for proj in projects
                ],
            )
        ),
        " ".join(filter(None, [(edu.get("school") or "") + " " + (edu.get("degree") or "") + " " + (edu.get("major") or "") for edu in educations])),
    ]
    return " ".join(filter(None, parts)).lower()


def build_vector_document(profile: dict) -> str:
    experience_lines = [
        " - ".join(filter(None, [exp.get("title"), exp.get("company"), exp.get("description")]))
        for exp in profile.get("experience", [])
    ]
    project_lines = [
        " - ".join(filter(None, [proj.get("name"), proj.get("role"), ", ".join(proj.get("technologies") or []), proj.get("description")]))
        for proj in profile.get("projects", [])
    ]
    education_lines = [
        " - ".join(filter(None, [edu.get("degree"), edu.get("major"), edu.get("school")]))
        for edu in profile.get("education", [])
    ]

    sections = [
        f"name: {profile.get('full_name') or ''}",
        f"title: {profile.get('current_title') or ''}",
        f"role: {profile.get('canonical_role') or ''}",
        f"company: {profile.get('current_company') or ''}",
        f"location: {profile.get('canonical_location') or profile.get('city') or profile.get('address') or ''}",
        f"years_experience: {profile.get('total_years_experience') or ''}",
        f"skills: {', '.join(profile.get('normalized_skills') or [])}",
        f"summary: {profile.get('summary') or ''}",
        f"experience: {' | '.join(filter(None, experience_lines))}",
        f"projects: {' | '.join(filter(None, project_lines))}",
        f"education: {' | '.join(filter(None, education_lines))}",
    ]
    return "\n".join(section for section in sections if section.strip())


def build_vector_metadata(profile: dict) -> VectorMetadata:
    skill_families = sorted({SKILL_FAMILIES.get(skill) for skill in profile.get("normalized_skills", []) if SKILL_FAMILIES.get(skill)})
    formal_education = [item for item in profile.get("education", []) if _is_formal_education(item)]
    degrees = sorted({edu.get("degree") for edu in formal_education if edu.get("degree")})
    majors = sorted({edu.get("major") for edu in formal_education if edu.get("major")})
    locations = sorted({loc for loc in [profile.get("canonical_location"), profile.get("city"), profile.get("address")] if loc})
    return VectorMetadata(
        role=profile.get("canonical_role"),
        title=profile.get("current_title"),
        company=profile.get("current_company"),
        skills=profile.get("normalized_skills") or [],
        skill_families=skill_families,
        degrees=degrees,
        majors=majors,
        locations=locations,
        domains=[],
        years_experience=profile.get("total_years_experience"),
    )


def normalize_candidate(extraction: CandidateExtraction, audit: ExtractionAudit | None = None) -> dict:
    audit = audit or ExtractionAudit()

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
    current_title = normalize_text(extraction.current_title.value)
    canonical_current_title = canonical_role(current_title)
    current_company = normalize_text(extraction.current_company.value)
    if _looks_like_company_noise(current_company):
        current_company = None

    for exp in extraction.experiences:
        start = parse_date_point(exp.start_date)
        end = parse_date_point(exp.end_date)
        inferred_months = months_between(start, end) if start and end else None
        title = normalize_text(exp.title)
        canonical_title = canonical_role(title)
        company = normalize_text(exp.company)
        if company:
            company = company.strip("()[]{} ")
        if _looks_like_company_noise(company):
            company = None
        location = normalize_text(exp.location)
        canonical_loc = canonical_location(location) if location else None
        description = normalize_text(exp.description)

        normalized_experiences.append(
            {
                **exp.model_dump(),
                "title": title,
                "canonical_title": canonical_title,
                "company": company,
                "location": location,
                "canonical_location": canonical_loc,
                "description": description,
                "inferred_months": inferred_months,
            }
        )

    normalized_experiences = [item for item in normalized_experiences if not _experience_is_training_or_noise(item)]
    normalized_experiences = _dedupe_experiences(normalized_experiences)

    if normalized_experiences:
        current_exp = None
        for item in normalized_experiences:
            end_text = (item.get("end_date") or "").lower()
            if end_text in {"present", "hiện tại"}:
                current_exp = item
                break
        if current_exp is None:
            current_exp = normalized_experiences[0]
        if not current_title and current_exp.get("title"):
            current_title = current_exp.get("title")
            canonical_current_title = current_exp.get("canonical_title")
        if not current_company and current_exp.get("company"):
            current_company = current_exp.get("company")

    normalized_educations = []
    for edu in extraction.educations:
        item = _sanitize_education_entry({
            **edu.model_dump(),
            "school": edu.school,
            "degree": edu.degree,
            "major": edu.major,
            "description": edu.description,
        })
        normalized_educations.append(item)

    normalized_educations = _dedupe_educations(normalized_educations)
    formal_educations = [item for item in normalized_educations if _is_formal_education(item)]
    normalized_educations = formal_educations or normalized_educations[:1]

    normalized_projects = []
    seen_projects: set[tuple[str, str]] = set()
    for proj in extraction.projects:
        item = proj.model_dump()
        item["name"] = normalize_text(item.get("name"))
        item["role"] = normalize_text(item.get("role"))
        item["description"] = normalize_text(item.get("description"))
        if _project_name_quality(item.get("name")) < 0.45 and item.get("description"):
            item["description"] = normalize_text(" ".join(filter(None, [item.get("name"), item.get("description")])))
            item["name"] = None
        key = ((item.get("name") or item.get("description") or "").lower(), (item.get("role") or "").lower())
        if key in seen_projects:
            continue
        seen_projects.add(key)
        if item.get("name") or item.get("description"):
            normalized_projects.append(item)

    links = [link.model_dump() for link in extraction.social_links]

    total_months = safe_total_experience_months([(exp.get("start_date"), exp.get("end_date")) for exp in normalized_experiences])
    total_years = round(total_months / 12.0, 2) if total_months > 0 else None

    address = normalize_text(extraction.address.value)
    city = normalize_text(extraction.city.value)
    if not city:
        experience_cities = [canonical_location(item.get("location")) for item in normalized_experiences if item.get("location")]
        city = infer_city(address, *experience_cities)
    canonical_loc = infer_city(address, city) if address or city else None

    if _looks_like_sentence(current_title):
        current_title = None
        canonical_current_title = None
    if (_looks_like_sentence(current_company) and not _looks_like_named_org(current_company)) or _looks_like_company_noise(current_company):
        current_company = None

    confidence = compute_confidence(extraction, audit, normalized_skills, total_years, current_title, current_company)

    review_reasons = list(audit.review_reasons)
    if extraction.full_name.extraction_method == "filename_fallback":
        review_reasons.append("filename_name_fallback")
    if not extraction.full_name.value:
        review_reasons.append("missing_full_name")
    if not extraction.primary_email.value and not extraction.primary_phone.value:
        review_reasons.append("missing_contact_info")
    if not normalized_skills:
        review_reasons.append("missing_skills")
    if total_years is None:
        review_reasons.append("missing_experience_duration")
    if current_title is None:
        review_reasons.append("current_title_low_precision")
    if extraction.current_company.value and current_company is None:
        review_reasons.append("current_company_low_precision")
    if normalized_experiences and _blend([_experience_quality(item) for item in normalized_experiences]) < 0.6:
        review_reasons.append("experience_quality_low")
    if normalized_educations and _blend([_education_quality(item) for item in normalized_educations]) < 0.6:
        review_reasons.append("education_quality_low")
    if normalized_projects and _blend([_project_name_quality(item.get("name")) for item in normalized_projects]) < 0.5:
        review_reasons.append("project_fragmentation_detected")
    if audit.cv_quality_score < 0.6:
        review_reasons.append("low_cv_quality_score")
    if confidence < 0.72:
        review_reasons.append("low_confidence")

    profile = {
        "full_name": normalize_text(extraction.full_name.value),
        "primary_email": normalize_text(extraction.primary_email.value),
        "primary_phone": normalize_text(extraction.primary_phone.value),
        "date_of_birth": normalize_text(extraction.date_of_birth.value),
        "address": address,
        "city": city,
        "canonical_location": canonical_loc,
        "summary": normalize_text(extraction.summary.value),
        "current_title": current_title,
        "canonical_role": canonical_current_title,
        "current_company": current_company,
        "normalized_skills": normalized_skills,
        "skills_by_family": dict(skills_by_family),
        "experience": normalized_experiences,
        "education": normalized_educations,
        "projects": normalized_projects,
        "social_links": links,
        "total_years_experience": total_years,
        "searchable_text": build_searchable_text(
            full_name=extraction.full_name.value,
            summary=extraction.summary.value,
            current_title=current_title,
            canonical_title=canonical_current_title,
            current_company=current_company,
            address=address,
            city=city,
            skills=normalized_skills,
            experiences=normalized_experiences,
            projects=normalized_projects,
            educations=normalized_educations,
        ),
        "confidence_score": confidence,
        "field_confidence": {
            **audit.field_confidence,
            "overall": confidence,
            "name": extraction.full_name.confidence,
            "contact": _blend([extraction.primary_email.confidence, extraction.primary_phone.confidence]),
            "city": 0.88 if city else 0.0,
            "skills": min(0.96, 0.45 + 0.05 * len(normalized_skills)) if normalized_skills else 0.0,
            "experience": _blend([_experience_quality(item) for item in normalized_experiences]) if normalized_experiences else 0.0,
            "education": _blend([_education_quality(item) for item in normalized_educations]) if normalized_educations else 0.0,
            "projects": _blend([_project_name_quality(item.get("name")) for item in normalized_projects]) if normalized_projects else 0.0,
        },
        "parser_mode": audit.parser_mode,
        "document_type": audit.document_type,
        "cv_quality_score": audit.cv_quality_score,
        "parse_flags": sorted(set(audit.parse_flags)),
        "review_reasons": sorted(set(review_reasons)),
    }
    profile["vector_document"] = build_vector_document(profile)
    profile["vector_metadata"] = build_vector_metadata(profile).model_dump()
    return profile