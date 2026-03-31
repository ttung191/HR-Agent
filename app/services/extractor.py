from __future__ import annotations

import re
from collections import defaultdict

from app.schemas.candidate import (
    CandidateExtraction,
    EducationItem,
    ExperienceItem,
    ExtractionAudit,
    LinkItem,
    ProjectItem,
    SkillItem,
)
from app.services.taxonomy import SECTION_ALIASES, SKILL_ALIASES, SKILL_FAMILIES

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?84|0)\d{8,10}")
URL_RE = re.compile(r"https?://\S+|(?:linkedin|github)\.com/\S+", re.I)
DATE_RE = re.compile(r"(?:\d{1,2}[/-]){2}\d{2,4}|\b\d{4}\b")


class HybridExtractor:
    def _split_sections(self, text: str) -> dict[str, str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        sections: dict[str, list[str]] = defaultdict(list)
        current = "header"

        for line in lines:
            normalized = line.lower().strip(" :")
            matched = False
            for canonical, aliases in SECTION_ALIASES.items():
                if any(normalized == alias for alias in aliases):
                    current = canonical
                    matched = True
                    break
            if not matched:
                sections[current].append(line)

        return {key: "\n".join(value).strip() for key, value in sections.items() if value}

    def _extract_name(self, header: str) -> str | None:
        for line in header.splitlines()[:4]:
            if EMAIL_RE.search(line) or PHONE_RE.search(line):
                continue
            if len(line.split()) >= 2 and len(line) < 80:
                return line.strip("-• ")
        return None

    def _extract_skills(self, text: str, source_section: str) -> list[SkillItem]:
        found: list[SkillItem] = []
        lowered = text.lower()
        seen: set[str] = set()

        for alias, normalized in SKILL_ALIASES.items():
            if alias in lowered and normalized not in seen:
                seen.add(normalized)
                found.append(
                    SkillItem(
                        raw_skill=alias,
                        normalized_skill=normalized,
                        skill_family=SKILL_FAMILIES.get(normalized),
                        source_section=source_section,
                        evidence_text=text[:250],
                    )
                )
        return found

    def _extract_experiences(self, text: str) -> list[ExperienceItem]:
        chunks = [chunk.strip() for chunk in re.split(r"\n\s*[-•]\s*|\n{2,}", text) if chunk.strip()]
        results: list[ExperienceItem] = []

        for chunk in chunks[:12]:
            lines = [line.strip() for line in chunk.splitlines() if line.strip()]
            if not lines:
                continue

            title = lines[0][:255]
            company = lines[1][:255] if len(lines) > 1 else None
            dates = DATE_RE.findall(chunk)
            description = " ".join(lines[2:]) if len(lines) > 2 else chunk

            results.append(
                ExperienceItem(
                    title=title,
                    company=company,
                    start_date=dates[0] if len(dates) >= 1 else None,
                    end_date=dates[1] if len(dates) >= 2 else None,
                    description=description[:2000],
                )
            )
        return results

    def _extract_educations(self, text: str) -> list[EducationItem]:
        chunks = [chunk.strip() for chunk in re.split(r"\n{2,}", text) if chunk.strip()]
        results: list[EducationItem] = []

        for chunk in chunks[:8]:
            lines = [line.strip() for line in chunk.splitlines() if line.strip()]
            school = lines[0][:255] if lines else None
            degree = lines[1][:255] if len(lines) > 1 else None
            dates = DATE_RE.findall(chunk)

            results.append(
                EducationItem(
                    school=school,
                    degree=degree,
                    start_date=dates[0] if len(dates) >= 1 else None,
                    end_date=dates[1] if len(dates) >= 2 else None,
                    description=" ".join(lines[2:])[:1500] if len(lines) > 2 else None,
                )
            )
        return results

    def _extract_projects(self, text: str) -> list[ProjectItem]:
        chunks = [chunk.strip() for chunk in re.split(r"\n{2,}", text) if chunk.strip()]
        results: list[ProjectItem] = []

        for chunk in chunks[:10]:
            lines = [line.strip() for line in chunk.splitlines() if line.strip()]
            technologies = [skill.normalized_skill for skill in self._extract_skills(chunk, "projects")]

            results.append(
                ProjectItem(
                    name=lines[0][:255] if lines else None,
                    role=lines[1][:255] if len(lines) > 1 else None,
                    description=" ".join(lines[2:])[:2000] if len(lines) > 2 else chunk[:2000],
                    technologies=technologies,
                )
            )
        return results

    def extract(self, raw_text: str, parser_meta: dict | None = None) -> tuple[CandidateExtraction, ExtractionAudit]:
        parser_meta = parser_meta or {}
        sections = self._split_sections(raw_text)
        header = sections.get("header", raw_text[:500])

        full_name = self._extract_name(header)
        email = EMAIL_RE.search(raw_text)
        phone = PHONE_RE.search(raw_text)
        links = [LinkItem(label="profile", url=match.group(0)) for match in URL_RE.finditer(raw_text)]

        skills = []
        for section_name in ("skills", "experience", "projects", "header"):
            if section_name in sections:
                skills.extend(self._extract_skills(sections[section_name], section_name))

        extraction = CandidateExtraction(
            full_name={
                "value": full_name,
                "confidence": 0.85 if full_name else 0.2,
                "evidence_text": header[:120],
                "source_section": "header",
            },
            primary_email={
                "value": email.group(0) if email else None,
                "confidence": 0.99 if email else 0.0,
                "evidence_text": email.group(0) if email else None,
                "source_section": "header",
            },
            primary_phone={
                "value": phone.group(0) if phone else None,
                "confidence": 0.95 if phone else 0.0,
                "evidence_text": phone.group(0) if phone else None,
                "source_section": "header",
            },
            date_of_birth={"value": None, "confidence": 0.0},
            address={"value": None, "confidence": 0.0},
            summary={
                "value": sections.get("summary"),
                "confidence": 0.8 if sections.get("summary") else 0.0,
                "evidence_text": sections.get("summary"),
                "source_section": "summary",
            },
            current_title={
                "value": (sections.get("experience", "").splitlines() or [None])[0],
                "confidence": 0.7 if sections.get("experience") else 0.0,
                "source_section": "experience",
            },
            current_company={
                "value": (sections.get("experience", "").splitlines() or [None, None])[1]
                if sections.get("experience")
                else None,
                "confidence": 0.55 if sections.get("experience") else 0.0,
                "source_section": "experience",
            },
            skills=skills,
            experiences=self._extract_experiences(sections.get("experience", "")),
            educations=self._extract_educations(sections.get("education", "")),
            projects=self._extract_projects(sections.get("projects", "")),
            social_links=links,
            sections_detected=list(sections.keys()),
        )

        field_confidence = {
            "full_name": extraction.full_name.confidence,
            "primary_email": extraction.primary_email.confidence,
            "primary_phone": extraction.primary_phone.confidence,
            "summary": extraction.summary.confidence,
            "current_title": extraction.current_title.confidence,
        }

        review_reasons: list[str] = []
        if not extraction.full_name.value:
            review_reasons.append("missing_full_name")
        if not extraction.primary_email.value and not extraction.primary_phone.value:
            review_reasons.append("missing_contact_info")
        if not extraction.skills:
            review_reasons.append("missing_skills")
        if len(raw_text.strip()) < 200:
            review_reasons.append("low_text_volume")

        audit = ExtractionAudit(
            schema_valid=True,
            extractor_backend="heuristic",
            review_reasons=review_reasons,
            parser_meta=parser_meta,
            field_confidence=field_confidence,
        )
        return extraction, audit