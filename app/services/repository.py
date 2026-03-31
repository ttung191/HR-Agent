from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict

from sqlalchemy import select
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
from app.schemas.candidate import CandidateSummary, EducationItem, ExperienceItem, LinkItem, ProjectItem


def to_candidate_summary(row: Candidate) -> CandidateSummary:
    return CandidateSummary(
        id=row.id,
        full_name=row.full_name,
        primary_email=row.primary_email,
        primary_phone=row.primary_phone,
        address=row.address,
        summary=row.summary,
        current_title=row.current_title,
        current_company=row.current_company,
        total_years_experience=row.total_years_experience,
        normalized_skills=sorted({item.normalized_skill for item in row.skills}),
        confidence_score=row.confidence_score,
        review_status=row.review_status,
        experiences=[
            ExperienceItem(
                title=item.title,
                company=item.company,
                location=item.location,
                start_date=item.start_date,
                end_date=item.end_date,
                inferred_months=item.inferred_months,
                description=item.description,
            )
            for item in row.experiences
        ],
        educations=[
            EducationItem(
                school=item.school,
                degree=item.degree,
                major=item.major,
                start_date=item.start_date,
                end_date=item.end_date,
                description=item.description,
            )
            for item in row.educations
        ],
        projects=[
            ProjectItem(
                name=item.name,
                role=item.role,
                start_date=item.start_date,
                end_date=item.end_date,
                description=item.description,
                technologies=(item.technologies or "").split(",") if item.technologies else [],
            )
            for item in row.projects
        ],
        links=[LinkItem(label=item.label, url=item.url) for item in row.links],
    )


class CandidateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, candidate_id: int) -> Candidate | None:
        stmt = (
            select(Candidate)
            .where(Candidate.id == candidate_id)
            .options(
                selectinload(Candidate.skills),
                selectinload(Candidate.experiences),
                selectinload(Candidate.educations),
                selectinload(Candidate.projects),
                selectinload(Candidate.links),
                selectinload(Candidate.extraction_runs),
                selectinload(Candidate.documents),
            )
        )
        return self.db.scalar(stmt)

    def list_all(self) -> list[Candidate]:
        stmt = (
            select(Candidate)
            .options(
                selectinload(Candidate.skills),
                selectinload(Candidate.experiences),
                selectinload(Candidate.educations),
                selectinload(Candidate.projects),
                selectinload(Candidate.links),
                selectinload(Candidate.extraction_runs),
            )
            .order_by(Candidate.updated_at.desc())
        )
        return list(self.db.scalars(stmt).unique())

    def list_by_review_status(self, status: str) -> list[Candidate]:
        stmt = (
            select(Candidate)
            .where(Candidate.review_status == status)
            .options(selectinload(Candidate.skills))
            .order_by(Candidate.confidence_score.asc(), Candidate.updated_at.desc())
        )
        return list(self.db.scalars(stmt).unique())

    def get_by_file_hash(self, file_hash: str) -> Document | None:
        stmt = select(Document).where(Document.file_hash == file_hash)
        return self.db.scalar(stmt)

    def create_candidate_bundle(
        self,
        *,
        normalized: dict,
        extraction_json: dict,
        audit_json: dict,
        file_info: dict,
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
            confidence_score=normalized.get("confidence_score", 0.0),
            review_status="needs_review" if normalized.get("review_reasons") else "approved",
            review_reason=", ".join(normalized.get("review_reasons", [])) if normalized.get("review_reasons") else None,
            duplicate_group=file_info.get("duplicate_group"),
        )
        self.db.add(candidate)
        self.db.flush()

        document = Document(
            candidate_id=candidate.id,
            source_filename=file_info["filename"],
            mime_type=file_info.get("mime_type"),
            file_hash=file_info["file_hash"],
            raw_text=file_info["raw_text"],
            used_ocr=bool(file_info.get("used_ocr", False)),
            parser_engine=file_info.get("parser_engine"),
            parser_meta_json=json.dumps(file_info.get("parser_meta", {}), ensure_ascii=False),
        )
        self.db.add(document)

        extraction_run = ExtractionRun(
            candidate_id=candidate.id,
            extractor_backend="hybrid",
            schema_version="v2",
            raw_extraction_json=json.dumps(extraction_json, ensure_ascii=False),
            normalized_profile_json=json.dumps(normalized, ensure_ascii=False),
            audit_json=json.dumps(audit_json, ensure_ascii=False),
        )
        self.db.add(extraction_run)

        for skill in normalized.get("normalized_skills", []):
            self.db.add(
                CandidateSkill(
                    candidate_id=candidate.id,
                    raw_skill=skill,
                    normalized_skill=skill,
                    skill_family=None,
                    source_section="normalized",
                    evidence_text=None,
                )
            )

        for exp in normalized.get("experience", []):
            self.db.add(
                CandidateExperience(
                    candidate_id=candidate.id,
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
            self.db.add(
                CandidateEducation(
                    candidate_id=candidate.id,
                    school=edu.get("school"),
                    degree=edu.get("degree"),
                    major=edu.get("major"),
                    start_date=edu.get("start_date"),
                    end_date=edu.get("end_date"),
                    description=edu.get("description"),
                )
            )

        for proj in normalized.get("projects", []):
            self.db.add(
                CandidateProject(
                    candidate_id=candidate.id,
                    name=proj.get("name"),
                    role=proj.get("role"),
                    start_date=proj.get("start_date"),
                    end_date=proj.get("end_date"),
                    description=proj.get("description"),
                    technologies=",".join(proj.get("technologies", [])),
                )
            )

        for link in normalized.get("social_links", []):
            if link.get("url"):
                self.db.add(
                    CandidateLink(
                        candidate_id=candidate.id,
                        label=link.get("label"),
                        url=link["url"],
                    )
                )

        self.db.commit()
        self.db.refresh(candidate)
        return self.get(candidate.id)  # type: ignore[return-value]

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
        rows = self.list_all()
        groups: dict[str, list[Candidate]] = defaultdict(list)
        for row in rows:
            if row.duplicate_group:
                groups[row.duplicate_group].append(row)

        return [
            {
                "duplicate_group": key,
                "count": len(items),
                "candidate_ids": [item.id for item in items],
                "names": [item.full_name for item in items],
            }
            for key, items in groups.items()
            if len(items) > 1
        ]

    def analytics(self) -> dict:
        rows = self.list_all()
        skill_counter = Counter()
        role_counter = Counter()
        review_counter = Counter()

        for row in rows:
            review_counter[row.review_status] += 1
            if row.current_title:
                role_counter[row.current_title] += 1
            for skill in row.skills:
                skill_counter[skill.normalized_skill] += 1

        return {
            "total_candidates": len(rows),
            "review_status_breakdown": dict(review_counter),
            "top_roles": role_counter.most_common(20),
            "top_skills": skill_counter.most_common(30),
            "avg_confidence_score": round(
                sum(item.confidence_score for item in rows) / len(rows), 3
            ) if rows else 0.0,
        }

    def export_csv(self) -> str:
        rows = self.list_all()
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "id", "full_name", "email", "phone", "current_title",
            "current_company", "years_experience", "skills",
            "confidence_score", "review_status"
        ])

        for row in rows:
            writer.writerow([
                row.id,
                row.full_name,
                row.primary_email,
                row.primary_phone,
                row.current_title,
                row.current_company,
                row.total_years_experience,
                ", ".join(sorted({skill.normalized_skill for skill in row.skills})),
                row.confidence_score,
                row.review_status,
            ])
        return buf.getvalue()