from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Candidate, CandidateEducation, CandidateSkill
from app.schemas.candidate import SearchExplanation, SearchRequest, SearchResult
from app.services.query_parser import QueryPlanner
from app.services.repository import to_candidate_summary
from app.services.vector_store import CandidateVectorStore

planner = QueryPlanner()


def _candidate_recent_strength(summary) -> float:
    if not summary.experiences:
        return 0.0
    latest = summary.experiences[:2]
    score = 0.0
    for exp in latest:
        if exp.title:
            score += 1.2
        if exp.description:
            score += 1.0
    return min(score, 3.0)


def _evidence_richness(summary, required_skills: list[str]) -> float:
    evidence = 0.0
    exp_text = " ".join(filter(None, [exp.description for exp in summary.experiences])).lower()
    proj_text = " ".join(filter(None, [proj.description for proj in summary.projects])).lower()
    skill_text = " ".join(summary.normalized_skills).lower()
    for skill in required_skills:
        if skill in skill_text:
            evidence += 1.5
        if skill in exp_text:
            evidence += 2.0
        if skill in proj_text:
            evidence += 1.5
    return min(evidence, 8.0)


def _match_degree(summary, degree_keywords: list[str]) -> list[str]:
    hits = []
    for edu in summary.educations:
        degree_blob = " ".join(filter(None, [edu.degree, edu.major, edu.school])).lower()
        for kw in degree_keywords:
            if kw.lower() in degree_blob and kw not in hits:
                hits.append(kw)
    return hits


def search_candidates(db: Session, request: SearchRequest) -> list[SearchResult]:
    plan = planner.plan(request.query)
    must_have_skills = sorted(set(request.must_have_skills or plan.must_have_skills))
    nice_to_have_skills = sorted(set(request.nice_to_have_skills or plan.nice_to_have_skills))
    role_keywords = sorted(set(request.role_keywords or plan.role_keywords))
    location_keywords = sorted(set(request.location_keywords or plan.location_keywords))
    degree_keywords = sorted(set(request.degree_keywords or plan.degree_keywords))
    minimum_years = request.minimum_years_experience if request.minimum_years_experience is not None else plan.minimum_years_experience

    stmt = (
        select(Candidate)
        .options(
            selectinload(Candidate.skills),
            selectinload(Candidate.experiences),
            selectinload(Candidate.educations),
            selectinload(Candidate.projects),
            selectinload(Candidate.links),
        )
        .distinct()
    )

    if request.review_status:
        stmt = stmt.where(Candidate.review_status == request.review_status)
    if minimum_years is not None:
        stmt = stmt.where(Candidate.total_years_experience.is_not(None))
        stmt = stmt.where(Candidate.total_years_experience >= max(minimum_years - 0.25, 0.0))
    if role_keywords:
        role_filters = [or_(Candidate.current_title.ilike(f"%{role}%"), Candidate.searchable_text.ilike(f"%{role}%")) for role in role_keywords]
        stmt = stmt.where(or_(*role_filters))
    if location_keywords:
        stmt = stmt.where(or_(*[Candidate.searchable_text.ilike(f"%{loc}%") for loc in location_keywords]))
    for skill in must_have_skills:
        stmt = stmt.join(CandidateSkill, CandidateSkill.candidate_id == Candidate.id)
        stmt = stmt.where(CandidateSkill.normalized_skill == skill)
    if degree_keywords:
        stmt = stmt.join(CandidateEducation, CandidateEducation.candidate_id == Candidate.id, isouter=True)

    candidates = list(db.scalars(stmt).unique())
    semantic_hits = {}
    if request.use_vectors:
        vector_store = CandidateVectorStore(db)
        semantic_hits = {hit.candidate_id: hit.similarity for hit in vector_store.candidate_hits(request.query, limit=max(request.limit * 5, 25))}

    results: list[SearchResult] = []
    for row in candidates:
        summary = to_candidate_summary(row)
        penalties: list[str] = []
        score = 0.0
        matched_required = [skill for skill in must_have_skills if skill in summary.normalized_skills]
        missing_required = [skill for skill in must_have_skills if skill not in summary.normalized_skills]
        if missing_required:
            continue
        matched_optional = [skill for skill in nice_to_have_skills if skill in summary.normalized_skills]
        matched_roles = []
        role_blob = " ".join(filter(None, [summary.current_title] + [exp.title for exp in summary.experiences])).lower()
        for role in role_keywords:
            if role.lower() in role_blob:
                matched_roles.append(role)
        matched_locations = []
        loc_blob = " ".join(filter(None, [summary.address, summary.summary])).lower()
        for loc in location_keywords:
            if loc.lower() in loc_blob:
                matched_locations.append(loc)
        matched_degrees = _match_degree(summary, degree_keywords)

        score += len(matched_required) * 45.0
        score += len(matched_optional) * 12.0
        score += len(matched_roles) * 18.0
        score += len(matched_locations) * 7.0
        score += len(matched_degrees) * 8.0

        years_bonus = 0.0
        if minimum_years is not None:
            if summary.total_years_experience is None:
                penalties.append("missing_years_experience")
                score -= 8.0
            else:
                gap = summary.total_years_experience - minimum_years
                if gap >= 0:
                    years_bonus = min(gap, 6.0) * 3.5 + 18.0
                else:
                    penalties.append("below_required_years")
                    years_bonus = max(-8.0, gap * 4.0)
        score += years_bonus

        searchable = " ".join(
            filter(
                None,
                [
                    summary.summary,
                    summary.current_title,
                    summary.current_company,
                    " ".join(summary.normalized_skills),
                    " ".join(filter(None, [exp.description for exp in summary.experiences])),
                    " ".join(filter(None, [proj.description for proj in summary.projects])),
                ],
            )
        ).lower()
        keyword_hits = []
        for term in plan.query_text_terms:
            if term.lower() in searchable:
                keyword_hits.append(term)
                score += 1.8

        evidence_bonus = _evidence_richness(summary, matched_required + matched_optional)
        score += evidence_bonus
        recency_bonus = _candidate_recent_strength(summary)
        score += recency_bonus
        confidence_bonus = summary.confidence_score * 10.0
        score += confidence_bonus

        semantic_similarity = semantic_hits.get(summary.id, 0.0)
        if request.use_vectors:
            score += semantic_similarity * 100.0 * max(min(request.semantic_weight, 1.0), 0.0)
        if summary.confidence_score < 0.55:
            penalties.append("low_confidence")
            score -= 8.0
        if not summary.experiences:
            penalties.append("missing_experience_records")
            score -= 5.0
        if not summary.summary:
            penalties.append("missing_summary")
            score -= 2.0

        results.append(
            SearchResult(
                candidate=summary,
                explanation=SearchExplanation(
                    score=round(score, 2),
                    matched_required_skills=matched_required,
                    matched_optional_skills=matched_optional,
                    matched_roles=matched_roles,
                    matched_locations=matched_locations,
                    matched_degrees=matched_degrees,
                    keyword_hits=keyword_hits,
                    evidence_richness_bonus=round(evidence_bonus, 2),
                    recency_bonus=round(recency_bonus, 2),
                    confidence_bonus=round(confidence_bonus, 2),
                    years_experience_bonus=round(years_bonus, 2),
                    semantic_similarity=round(semantic_similarity, 4),
                    missing_required_skills=missing_required,
                    penalties=penalties,
                ),
            )
        )

    results.sort(key=lambda item: item.explanation.score, reverse=True)
    return results[: request.limit]
