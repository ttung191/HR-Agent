from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import Base
from app.models import Candidate, CandidateExperience, CandidateSkill
from app.services.search import search_candidates
from app.schemas.candidate import SearchRequest


def build_test_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return TestingSessionLocal()


def seed_candidate(
    db: Session,
    *,
    name: str,
    title: str,
    years: float,
    skills: list[str],
    summary: str,
    review_status: str = "approved",
):
    candidate = Candidate(
        full_name=name,
        current_title=title,
        total_years_experience=years,
        searchable_text=f"{name} {title} {' '.join(skills)} {summary}".lower(),
        confidence_score=0.9,
        review_status=review_status,
        summary=summary,
    )
    db.add(candidate)
    db.flush()

    for skill in skills:
        db.add(
            CandidateSkill(
                candidate_id=candidate.id,
                raw_skill=skill,
                normalized_skill=skill,
                source_section="test",
            )
        )

    db.add(
        CandidateExperience(
            candidate_id=candidate.id,
            company="Test Company",
            title=title,
            start_date="2020",
            end_date="2024",
            inferred_months=int(years * 12),
            description=summary,
        )
    )
    db.commit()
    return candidate


def test_search_data_engineer_aws():
    db = build_test_session()

    seed_candidate(
        db,
        name="Alice Nguyen",
        title="data engineer",
        years=4.0,
        skills=["python", "sql", "aws", "airflow"],
        summary="Built ETL pipelines on AWS and Airflow.",
    )
    seed_candidate(
        db,
        name="Bob Tran",
        title="backend engineer",
        years=5.0,
        skills=["python", "fastapi", "docker"],
        summary="Built backend services.",
    )

    results = search_candidates(
        db,
        SearchRequest(query="data engineer 3 năm aws", limit=10),
    )

    assert len(results) >= 1
    assert results[0].candidate.full_name == "Alice Nguyen"
    assert "aws" in results[0].explanation.matched_required_skills
    assert "data engineer" in results[0].explanation.matched_roles


def test_search_filters_below_required_years():
    db = build_test_session()

    seed_candidate(
        db,
        name="Chris Le",
        title="data engineer",
        years=1.5,
        skills=["python", "sql", "aws"],
        summary="Junior data engineer working on AWS.",
    )

    results = search_candidates(
        db,
        SearchRequest(query="data engineer 3 years aws", limit=10),
    )

    assert results == []


def test_search_optional_skills_boost_ranking():
    db = build_test_session()

    seed_candidate(
        db,
        name="Duy",
        title="data engineer",
        years=4.0,
        skills=["python", "sql", "aws"],
        summary="Built batch pipelines.",
    )
    seed_candidate(
        db,
        name="Hanh",
        title="data engineer",
        years=4.0,
        skills=["python", "sql", "aws", "airflow", "spark"],
        summary="Built AWS ETL pipelines with Spark and Airflow.",
    )

    results = search_candidates(
        db,
        SearchRequest(
            query="data engineer 3 years aws",
            must_have_skills=["aws"],
            nice_to_have_skills=["airflow", "spark"],
            limit=10,
        ),
    )

    assert len(results) == 2
    assert results[0].candidate.full_name == "Hanh"
    assert set(results[0].explanation.matched_optional_skills) == {"airflow", "spark"}