from __future__ import annotations

import csv
import io
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Candidate,
    CandidateEducation,
    CandidateExperience,
    CandidateLink,
    CandidateProject,
    CandidateSkill,
    Document,
    ExtractionRun,
)
from app.schemas.candidate import CandidateSummary, EducationItem, ExperienceItem, LinkItem, ProjectItem, VectorMetadata


class CandidateRepository:
    def __init__(self, db: Session):
        self.db = db

    def _base_query(self):
        return select(Candidate).options(
            selectinload(Candidate.skills),
            selectinload(Candidate.experiences),
            selectinload(Candidate.educations),
            selectinload(Candidate.projects),
            selectinload(Candidate.links),
            selectinload(Candidate.documents),
            selectinload(Candidate.extraction_runs),
            selectinload(Candidate.vectors),
        )

    def get(self, candidate_id: int) -> Candidate | None:
        return self.db.scalar(self._base_query().where(Candidate.id == candidate_id))

    def list_all(self) -> list[Candidate]:
        return list(self.db.scalars(self._base_query().order_by(Candidate.created_at.desc())).unique())

    def list_by_review_status(self, review_status: str) -> list[Candidate]:
        return list(
            self.db.scalars(
                self._base_query().where(Candidate.review_status == review_status).order_by(Candidate.created_at.desc())
            ).unique()
        )

    def get_by_file_hash(self, file_hash: str) -> Document | None:
        return self.db.scalar(select(Document).where(Document.file_hash == file_hash))

    def create_candidate_bundle(
        self,
        normalized: dict[str, Any],
        extraction_json: dict,
        audit_json: dict,
        file_info: dict[str, Any],
    ) -> Candidate:
        candidate = Candidate(
            full_name=normalized.get("full_name"),
            primary_email=normalized.get("primary_email"),
            primary_phone=normalized.get("primary_phone"),
            date_of_birth=normalized.get("date_of_birth"),
            address=normalized.get("address"),
            summary=normalized.get("summary"),
            current_title=normalized.get("current_title"),
            current_company=normalized.get("current_company"),
            total_years_experience=normalized.get("total_years_experience"),
            searchable_text=normalized.get("searchable_text"),
            confidence_score=normalized.get("confidence_score") or 0.0,
            review_status="needs_review" if normalized.get("review_reasons") else "ready",
            review_reason=", ".join(normalized.get("review_reasons") or []) or None,
            duplicate_group=file_info.get("duplicate_group"),
            vector_document=normalized.get("vector_document"),
            vector_metadata_json=json.dumps(normalized.get("vector_metadata") or {}, ensure_ascii=False),
        )
        self.db.add(candidate)
        self.db.flush()

        document = Document(
            candidate_id=candidate.id,
            source_filename=file_info["filename"],
            mime_type=file_info.get("mime_type"),
            file_hash=file_info["file_hash"],
            raw_text=file_info["raw_text"],
            used_ocr=file_info.get("used_ocr", False),
            parser_engine=file_info.get("parser_engine"),
            parser_meta_json=json.dumps(file_info.get("parser_meta") or {}, ensure_ascii=False),
        )
        self.db.add(document)

        self._append_extraction_run(candidate.id, normalized, extraction_json, audit_json)
        self._replace_candidate_children(candidate, normalized)

        self.db.commit()
        self.db.refresh(candidate)
        return self.get(candidate.id) or candidate

    def reparse_candidate_bundle(self, candidate_id: int, normalized: dict[str, Any], extraction_json: dict, audit_json: dict) -> Candidate | None:
        candidate = self.get(candidate_id)
        if not candidate:
            return None

        candidate.full_name = normalized.get("full_name")
        candidate.primary_email = normalized.get("primary_email")
        candidate.primary_phone = normalized.get("primary_phone")
        candidate.date_of_birth = normalized.get("date_of_birth")
        candidate.address = normalized.get("address")
        candidate.summary = normalized.get("summary")
        candidate.current_title = normalized.get("current_title")
        candidate.current_company = normalized.get("current_company")
        candidate.total_years_experience = normalized.get("total_years_experience")
        candidate.searchable_text = normalized.get("searchable_text")
        candidate.confidence_score = normalized.get("confidence_score") or 0.0
        candidate.review_status = "needs_review" if normalized.get("review_reasons") else "ready"
        candidate.review_reason = ", ".join(normalized.get("review_reasons") or []) or None
        candidate.vector_document = normalized.get("vector_document")
        candidate.vector_metadata_json = json.dumps(normalized.get("vector_metadata") or {}, ensure_ascii=False)

        self._replace_candidate_children(candidate, normalized)
        self._append_extraction_run(candidate.id, normalized, extraction_json, audit_json)

        self.db.commit()
        self.db.refresh(candidate)
        return self.get(candidate.id)

    def _append_extraction_run(self, candidate_id: int, normalized: dict[str, Any], extraction_json: dict, audit_json: dict) -> None:
        extraction_run = ExtractionRun(
            candidate_id=candidate_id,
            extractor_backend=audit_json.get("extractor_backend", "hybrid"),
            schema_version="v5",
            raw_extraction_json=json.dumps(extraction_json, ensure_ascii=False),
            normalized_profile_json=json.dumps(normalized, ensure_ascii=False),
            audit_json=json.dumps(audit_json, ensure_ascii=False),
        )
        self.db.add(extraction_run)

    def _replace_candidate_children(self, candidate: Candidate, normalized: dict[str, Any]) -> None:
        candidate.skills.clear()
        candidate.experiences.clear()
        candidate.educations.clear()
        candidate.projects.clear()
        candidate.links.clear()
        self.db.flush()

        for skill in normalized.get("normalized_skills", []):
            candidate.skills.append(
                CandidateSkill(
                    raw_skill=skill,
                    normalized_skill=skill,
                    skill_family=(normalized.get("skills_by_family") and _reverse_skill_family(normalized["skills_by_family"], skill)),
                    source_section="normalized",
                    evidence_text=None,
                )
            )

        for exp in normalized.get("experience", []):
            candidate.experiences.append(
                CandidateExperience(
                    company=exp.get("company"),
                    title=exp.get("title"),
                    location=exp.get("location"),
                    start_date=exp.get("start_date"),
                    end_date=exp.get("end_date"),
                    inferred_months=exp.get("inferred_months"),
                    description=exp.get("description"),
                )
            )

        for edu in normalized.get("education", []):
            candidate.educations.append(
                CandidateEducation(
                    school=edu.get("school"),
                    degree=edu.get("degree"),
                    major=edu.get("major"),
                    start_date=edu.get("start_date"),
                    end_date=edu.get("end_date"),
                    description=edu.get("description"),
                )
            )

        for proj in normalized.get("projects", []):
            candidate.projects.append(
                CandidateProject(
                    name=proj.get("name"),
                    role=proj.get("role"),
                    start_date=proj.get("start_date"),
                    end_date=proj.get("end_date"),
                    description=proj.get("description"),
                    technologies=json.dumps(proj.get("technologies") or [], ensure_ascii=False),
                )
            )

        for link in normalized.get("social_links", []):
            candidate.links.append(CandidateLink(label=link.get("label"), url=link.get("url")))

    def update_review(self, candidate_id: int, review_status: str, review_reason: str | None) -> Candidate | None:
        row = self.get(candidate_id)
        if not row:
            return None
        row.review_status = review_status
        row.review_reason = review_reason
        self.db.commit()
        self.db.refresh(row)
        return row

    def duplicate_groups(self) -> list[dict]:
        stmt = (
            select(Candidate.duplicate_group, func.count(Candidate.id))
            .where(Candidate.duplicate_group.is_not(None))
            .group_by(Candidate.duplicate_group)
            .having(func.count(Candidate.id) > 1)
        )
        rows = self.db.execute(stmt).all()
        return [{"duplicate_group": group, "count": count} for group, count in rows]

    def analytics(self) -> dict:
        total_candidates = self.db.scalar(select(func.count(Candidate.id))) or 0
        ready_candidates = self.db.scalar(select(func.count(Candidate.id)).where(Candidate.review_status == "ready")) or 0
        needs_review = self.db.scalar(select(func.count(Candidate.id)).where(Candidate.review_status == "needs_review")) or 0
        avg_confidence = self.db.scalar(select(func.avg(Candidate.confidence_score))) or 0.0
        return {
            "total_candidates": total_candidates,
            "ready_candidates": ready_candidates,
            "needs_review": needs_review,
            "avg_confidence_score": round(float(avg_confidence), 3),
        }

    def export_csv(self) -> str:
        rows = self.list_all()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id",
                "full_name",
                "primary_email",
                "primary_phone",
                "current_title",
                "current_company",
                "total_years_experience",
                "normalized_skills",
                "review_status",
                "confidence_score",
            ]
        )
        for row in rows:
            summary = to_candidate_summary(row)
            writer.writerow(
                [
                    summary.id,
                    summary.full_name,
                    summary.primary_email,
                    summary.primary_phone,
                    summary.current_title,
                    summary.current_company,
                    summary.total_years_experience,
                    ", ".join(summary.normalized_skills),
                    summary.review_status,
                    summary.confidence_score,
                ]
            )
        return buffer.getvalue()


def _reverse_skill_family(mapping: dict[str, list[str]], skill: str) -> str | None:
    for family, skills in mapping.items():
        if skill in skills:
            return family
    return None


def _parse_project_technologies(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
        return [str(item) for item in data] if isinstance(data, list) else []
    except Exception:
        return []


def to_candidate_summary(row: Candidate) -> CandidateSummary:
    metadata = {}
    normalized_profile: dict[str, Any] = {}
    schema_version = "v5"

    if row.vector_metadata_json:
        try:
            metadata = json.loads(row.vector_metadata_json)
        except Exception:
            metadata = {}

    latest_run = None
    if row.extraction_runs:
        latest_run = sorted(row.extraction_runs, key=lambda item: item.created_at or row.created_at)[-1]
        schema_version = latest_run.schema_version or schema_version
        if latest_run.normalized_profile_json:
            try:
                normalized_profile = json.loads(latest_run.normalized_profile_json)
            except Exception:
                normalized_profile = {}

    return CandidateSummary(
        id=row.id,
        schema_version=schema_version,
        full_name=row.full_name,
        primary_email=row.primary_email,
        primary_phone=row.primary_phone,
        address=row.address,
        summary=row.summary,
        current_title=row.current_title,
        current_company=row.current_company,
        total_years_experience=row.total_years_experience,
        normalized_skills=sorted({skill.normalized_skill for skill in row.skills}),
        confidence_score=row.confidence_score,
        field_confidence=normalized_profile.get("field_confidence") or {},
        review_status=row.review_status,
        review_reasons=normalized_profile.get("review_reasons") or ([row.review_reason] if row.review_reason else []),
        vector_document=row.vector_document,
        vector_metadata=VectorMetadata.model_validate(metadata) if metadata else None,
        experiences=[
            ExperienceItem(
                title=exp.title,
                company=exp.company,
                location=exp.location,
                start_date=exp.start_date,
                end_date=exp.end_date,
                inferred_months=exp.inferred_months,
                description=exp.description,
            )
            for exp in row.experiences
        ],
        educations=[
            EducationItem(
                school=edu.school,
                degree=edu.degree,
                major=edu.major,
                start_date=edu.start_date,
                end_date=edu.end_date,
                description=edu.description,
            )
            for edu in row.educations
        ],
        projects=[
            ProjectItem(
                name=proj.name,
                role=proj.role,
                start_date=proj.start_date,
                end_date=proj.end_date,
                description=proj.description,
                technologies=_parse_project_technologies(proj.technologies),
            )
            for proj in row.projects
        ],
        links=[LinkItem(label=link.label, url=link.url) for link in row.links],
    )
