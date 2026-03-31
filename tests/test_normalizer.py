from __future__ import annotations

from app.schemas.candidate import (
    CandidateExtraction,
    EducationItem,
    ExperienceItem,
    ExtractedField,
    ProjectItem,
    SkillItem,
)
from app.services.normalizer import normalize_candidate


def test_normalize_candidate_basic():
    extraction = CandidateExtraction(
        full_name=ExtractedField(value="Nguyen Van A", confidence=0.9),
        primary_email=ExtractedField(value="a@example.com", confidence=0.99),
        primary_phone=ExtractedField(value="0912345678", confidence=0.95),
        date_of_birth=ExtractedField(value=None, confidence=0.0),
        address=ExtractedField(value="Ha Noi", confidence=0.8),
        summary=ExtractedField(value="Data engineer with AWS experience", confidence=0.85),
        current_title=ExtractedField(value="Senior Data Engineer", confidence=0.8),
        current_company=ExtractedField(value="ABC Corp", confidence=0.7),
        skills=[
            SkillItem(raw_skill="AWS", normalized_skill="aws"),
            SkillItem(raw_skill="PySpark", normalized_skill="spark"),
            SkillItem(raw_skill="SQL", normalized_skill="sql"),
        ],
        experiences=[
            ExperienceItem(
                title="Senior Data Engineer",
                company="ABC Corp",
                start_date="2020",
                end_date="2024",
                description="Built data pipelines",
            )
        ],
        educations=[
            EducationItem(
                school="HUST",
                degree="Bachelor",
                major="Computer Science",
                start_date="2015",
                end_date="2019",
            )
        ],
        projects=[
            ProjectItem(
                name="Data Platform",
                description="Built AWS ETL system",
                technologies=["aws", "spark"],
            )
        ],
        social_links=[],
        sections_detected=["header", "skills", "experience", "education", "projects"],
    )

    normalized = normalize_candidate(extraction)

    assert normalized["full_name"] == "Nguyen Van A"
    assert normalized["primary_email"] == "a@example.com"
    assert normalized["current_title"] == "data engineer"
    assert "aws" in normalized["normalized_skills"]
    assert "spark" in normalized["normalized_skills"]
    assert normalized["total_years_experience"] is not None
    assert normalized["confidence_score"] > 0.7