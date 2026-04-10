from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Candidate
from app.schemas.candidate import CandidateMatchResult, JDMatchRequest, JDMatchResponse, MatchBreakdown
from app.services.jd_parser import JDParser
from app.services.normalizer import canonical_role
from app.services.repository import to_candidate_summary
from app.services.vector_store import CandidateVectorStore


class JDMatcher:
    def __init__(self, db: Session):
        self.db = db
        self.vector_store = CandidateVectorStore(db)
        self.jd_parser = JDParser()

    def match(self, request: JDMatchRequest) -> JDMatchResponse:
        parsed_jd = self.jd_parser.parse(request.jd_text)
        candidate_ids = request.candidate_ids
        semantic_hits = {
            hit.candidate_id: hit.similarity
            for hit in self.vector_store.candidate_hits(
                parsed_jd.vector_document,
                candidate_ids=candidate_ids,
                limit=max(request.limit * 5, 50),
            )
        }

        stmt = select(Candidate).options(
            selectinload(Candidate.skills),
            selectinload(Candidate.experiences),
            selectinload(Candidate.educations),
            selectinload(Candidate.projects),
            selectinload(Candidate.links),
        )
        if candidate_ids:
            stmt = stmt.where(Candidate.id.in_(candidate_ids))
        candidates = list(self.db.scalars(stmt).unique())

        results: list[CandidateMatchResult] = []
        for row in candidates:
            summary = to_candidate_summary(row)
            matched_must = [skill for skill in parsed_jd.must_have_skills if skill in summary.normalized_skills]
            missing_must = [skill for skill in parsed_jd.must_have_skills if skill not in summary.normalized_skills]
            matched_nice = [skill for skill in parsed_jd.nice_to_have_skills if skill in summary.normalized_skills]

            must_ratio = len(matched_must) / len(parsed_jd.must_have_skills) if parsed_jd.must_have_skills else 1.0
            nice_ratio = len(matched_nice) / len(parsed_jd.nice_to_have_skills) if parsed_jd.nice_to_have_skills else 0.0
            skill_alignment = min(1.0, must_ratio * 0.85 + nice_ratio * 0.15)

            role_terms = []
            for value in [summary.current_title] + [exp.title for exp in summary.experiences]:
                if not value:
                    continue
                role_terms.append(value)
                canonical = canonical_role(value)
                if canonical:
                    role_terms.append(canonical)
            role_blob = " ".join(role_terms).lower()
            matched_roles = [role for role in parsed_jd.role_keywords if role.lower() in role_blob]
            role_alignment = 1.0 if parsed_jd.role_keywords and matched_roles else (1.0 if not parsed_jd.role_keywords else 0.0)

            if parsed_jd.minimum_years_experience is None:
                years_alignment = 1.0
            elif summary.total_years_experience is None:
                years_alignment = 0.0
            else:
                ratio = summary.total_years_experience / max(parsed_jd.minimum_years_experience, 0.5)
                years_alignment = max(0.0, min(ratio, 1.0))

            matched_degrees = []
            degree_blob = " ".join(
                filter(None, [f"{edu.degree or ''} {edu.major or ''} {edu.school or ''}" for edu in summary.educations])
            ).lower()
            for degree in parsed_jd.degree_keywords:
                if degree.lower() in degree_blob:
                    matched_degrees.append(degree)
            degree_alignment = (
                len(matched_degrees) / len(parsed_jd.degree_keywords)
                if parsed_jd.degree_keywords
                else 1.0
            )

            semantic_similarity = semantic_hits.get(summary.id, 0.0)
            final_score = (
                semantic_similarity * request.semantic_weight
                + skill_alignment * request.skill_weight
                + role_alignment * request.role_weight
                + years_alignment * request.years_weight
                + degree_alignment * request.degree_weight
            )

            notes: list[str] = []
            if missing_must:
                notes.append("Thiếu một phần must-have skills từ JD")
            if parsed_jd.minimum_years_experience is not None and summary.total_years_experience is None:
                notes.append("Hồ sơ chưa suy luận được số năm kinh nghiệm")
            if semantic_similarity < 0.2:
                notes.append("Độ tương đồng ngữ nghĩa thấp")

            results.append(
                CandidateMatchResult(
                    candidate=summary,
                    breakdown=MatchBreakdown(
                        semantic_similarity=round(semantic_similarity, 4),
                        skill_alignment=round(skill_alignment, 4),
                        role_alignment=round(role_alignment, 4),
                        years_alignment=round(years_alignment, 4),
                        degree_alignment=round(degree_alignment, 4),
                        final_score=round(final_score * 100, 2),
                        matched_must_have_skills=matched_must,
                        matched_nice_to_have_skills=matched_nice,
                        missing_must_have_skills=missing_must,
                        matched_roles=matched_roles,
                        matched_degrees=matched_degrees,
                        notes=notes,
                    ),
                )
            )

        results.sort(key=lambda item: item.breakdown.final_score, reverse=True)
        return JDMatchResponse(parsed_jd=parsed_jd, results=results[: request.limit])