from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
    city: ExtractedField = Field(default_factory=ExtractedField)
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
    document_type: str = "general_cv"
    parser_mode: str = "fallback"
    cv_quality_score: float = 0.0
    parse_flags: list[str] = Field(default_factory=list)
    source_trace: dict = Field(default_factory=dict)
    resolver_stats: dict = Field(default_factory=dict)
    resolver_trace: dict = Field(default_factory=dict)


class VectorMetadata(BaseModel):
    role: str | None = None
    title: str | None = None
    company: str | None = None
    skills: list[str] = Field(default_factory=list)
    skill_families: list[str] = Field(default_factory=list)
    degrees: list[str] = Field(default_factory=list)
    majors: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    years_experience: float | None = None


class CandidateSummary(BaseModel):
    id: int
    schema_version: str = "v5"
    full_name: str | None = None
    primary_email: str | None = None
    primary_phone: str | None = None
    address: str | None = None
    city: str | None = None
    summary: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    total_years_experience: float | None = None
    normalized_skills: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    field_confidence: dict[str, float] = Field(default_factory=dict)
    review_status: str = "needs_review"
    review_reasons: list[str] = Field(default_factory=list)
    parser_backend: str | None = None
    parse_flags: list[str] = Field(default_factory=list)
    vector_document: str | None = None
    vector_metadata: VectorMetadata | None = None
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
    use_vectors: bool = True
    semantic_weight: float = 0.45


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
    semantic_similarity: float = 0.0
    missing_required_skills: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    candidate: CandidateSummary
    explanation: SearchExplanation


class UploadResult(BaseModel):
    schema_version: str = "v5"
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


class JDRequirement(BaseModel):
    raw_text: str
    canonical_text: str
    role_keywords: list[str] = Field(default_factory=list)
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    degree_keywords: list[str] = Field(default_factory=list)
    location_keywords: list[str] = Field(default_factory=list)
    domain_keywords: list[str] = Field(default_factory=list)
    minimum_years_experience: float | None = None
    vector_document: str
    vector_metadata: VectorMetadata


class JDMatchRequest(BaseModel):
    jd_text: str
    limit: int = 10
    candidate_ids: list[int] | None = None
    semantic_weight: float = 0.45
    skill_weight: float = 0.30
    role_weight: float = 0.10
    years_weight: float = 0.10
    degree_weight: float = 0.05


class MatchBreakdown(BaseModel):
    semantic_similarity: float
    skill_alignment: float
    role_alignment: float
    years_alignment: float
    degree_alignment: float
    final_score: float
    matched_must_have_skills: list[str] = Field(default_factory=list)
    matched_nice_to_have_skills: list[str] = Field(default_factory=list)
    missing_must_have_skills: list[str] = Field(default_factory=list)
    matched_roles: list[str] = Field(default_factory=list)
    matched_degrees: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CandidateMatchResult(BaseModel):
    candidate: CandidateSummary
    breakdown: MatchBreakdown


class JDMatchResponse(BaseModel):
    parsed_jd: JDRequirement
    results: list[CandidateMatchResult] = Field(default_factory=list)


class RebuildVectorsResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    total_candidates: int
    rebuilt_vectors: int
    skipped_vectors: int
    model_name: str
