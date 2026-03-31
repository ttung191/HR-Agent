from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    value: str | None = None
    confidence: float = 0.0
    evidence_text: str | None = None
    source_section: str | None = None
    extraction_method: str | None = None


class SkillItem(BaseModel):
    raw_skill: str
    normalized_skill: str
    skill_family: str | None = None
    source_section: str | None = None
    evidence_text: str | None = None


class ExperienceItem(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    inferred_months: int | None = None
    employment_type: str | None = None
    description: str | None = None


class EducationItem(BaseModel):
    school: str | None = None
    degree: str | None = None
    major: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class ProjectItem(BaseModel):
    name: str | None = None
    role: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)


class LinkItem(BaseModel):
    label: str | None = None
    url: str


class CandidateExtraction(BaseModel):
    full_name: ExtractedField
    primary_email: ExtractedField
    primary_phone: ExtractedField
    date_of_birth: ExtractedField
    address: ExtractedField
    summary: ExtractedField
    current_title: ExtractedField
    current_company: ExtractedField
    skills: list[SkillItem] = Field(default_factory=list)
    experiences: list[ExperienceItem] = Field(default_factory=list)
    educations: list[EducationItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    social_links: list[LinkItem] = Field(default_factory=list)
    sections_detected: list[str] = Field(default_factory=list)


class ExtractionAudit(BaseModel):
    schema_valid: bool = True
    extractor_backend: str = "hybrid"
    review_reasons: list[str] = Field(default_factory=list)
    parser_meta: dict = Field(default_factory=dict)
    field_confidence: dict[str, float] = Field(default_factory=dict)


class CandidateSummary(BaseModel):
    id: int
    full_name: str | None = None
    primary_email: str | None = None
    primary_phone: str | None = None
    address: str | None = None
    summary: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    total_years_experience: float | None = None
    normalized_skills: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    review_status: str = "needs_review"
    experiences: list[ExperienceItem] = Field(default_factory=list)
    educations: list[EducationItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    links: list[LinkItem] = Field(default_factory=list)


class QueryPlan(BaseModel):
    original_query: str
    role_keywords: list[str] = Field(default_factory=list)
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    minimum_years_experience: float | None = None
    location_keywords: list[str] = Field(default_factory=list)
    degree_keywords: list[str] = Field(default_factory=list)
    domain_keywords: list[str] = Field(default_factory=list)
    query_text_terms: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    limit: int = 20
    review_status: str | None = None
    must_have_skills: list[str] | None = None
    nice_to_have_skills: list[str] | None = None
    role_keywords: list[str] | None = None
    location_keywords: list[str] | None = None
    degree_keywords: list[str] | None = None
    minimum_years_experience: float | None = None


class SearchExplanation(BaseModel):
    score: float
    matched_required_skills: list[str] = Field(default_factory=list)
    matched_optional_skills: list[str] = Field(default_factory=list)
    matched_roles: list[str] = Field(default_factory=list)
    matched_locations: list[str] = Field(default_factory=list)
    matched_degrees: list[str] = Field(default_factory=list)
    keyword_hits: list[str] = Field(default_factory=list)
    evidence_richness_bonus: float = 0.0
    recency_bonus: float = 0.0
    confidence_bonus: float = 0.0
    years_experience_bonus: float = 0.0
    missing_required_skills: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    candidate: CandidateSummary
    explanation: SearchExplanation


class UploadResult(BaseModel):
    candidate: CandidateSummary
    extraction: CandidateExtraction | dict
    audit: ExtractionAudit | dict
    warnings: list[str] = Field(default_factory=list)


class BatchUploadResult(BaseModel):
    filename: str
    status: str
    candidate_id: int | None = None
    review_status: str | None = None
    confidence_score: float | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class ReviewUpdateRequest(BaseModel):
    review_status: str
    review_reason: str | None = None