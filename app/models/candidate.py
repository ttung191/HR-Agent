from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Candidate(Base, TimestampMixin):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str | None] = mapped_column(String(255), index=True)
    primary_email: Mapped[str | None] = mapped_column(String(255), index=True)
    primary_phone: Mapped[str | None] = mapped_column(String(64), index=True)
    date_of_birth: Mapped[str | None] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(String(512), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    current_title: Mapped[str | None] = mapped_column(String(255), index=True)
    current_company: Mapped[str | None] = mapped_column(String(255))
    total_years_experience: Mapped[float | None] = mapped_column(Float, index=True)
    searchable_text: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    review_status: Mapped[str] = mapped_column(String(32), default="needs_review", index=True)
    review_reason: Mapped[str | None] = mapped_column(Text)
    duplicate_group: Mapped[str | None] = mapped_column(String(255), index=True)

    documents: Mapped[list["Document"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    skills: Mapped[list["CandidateSkill"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    experiences: Mapped[list["CandidateExperience"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    educations: Mapped[list["CandidateEducation"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    projects: Mapped[list["CandidateProject"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    links: Mapped[list["CandidateLink"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")
    extraction_runs: Mapped[list["ExtractionRun"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("file_hash", name="uq_documents_file_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"),
        index=True,
    )
    source_filename: Mapped[str] = mapped_column(String(255), index=True)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    raw_text: Mapped[str] = mapped_column(Text)

    used_ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    parser_engine: Mapped[str | None] = mapped_column(String(128))
    parser_meta_json: Mapped[str | None] = mapped_column(Text)

    candidate: Mapped["Candidate | None"] = relationship(back_populates="documents")


class ExtractionRun(Base, TimestampMixin):
    __tablename__ = "extraction_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"),
        index=True,
    )
    extractor_backend: Mapped[str] = mapped_column(String(64), default="hybrid")
    schema_version: Mapped[str] = mapped_column(String(32), default="v2")
    raw_extraction_json: Mapped[str] = mapped_column(Text)
    normalized_profile_json: Mapped[str] = mapped_column(Text)
    audit_json: Mapped[str] = mapped_column(Text)

    candidate: Mapped["Candidate"] = relationship(back_populates="extraction_runs")


class CandidateSkill(Base, TimestampMixin):
    __tablename__ = "candidate_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    raw_skill: Mapped[str] = mapped_column(String(255), index=True)
    normalized_skill: Mapped[str] = mapped_column(String(255), index=True)
    skill_family: Mapped[str | None] = mapped_column(String(128), index=True)
    source_section: Mapped[str | None] = mapped_column(String(128))
    evidence_text: Mapped[str | None] = mapped_column(Text)

    candidate: Mapped["Candidate"] = relationship(back_populates="skills")


class CandidateExperience(Base, TimestampMixin):
    __tablename__ = "candidate_experiences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    company: Mapped[str | None] = mapped_column(String(255), index=True)
    title: Mapped[str | None] = mapped_column(String(255), index=True)
    location: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[str | None] = mapped_column(String(64))
    end_date: Mapped[str | None] = mapped_column(String(64))
    inferred_months: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)

    candidate: Mapped["Candidate"] = relationship(back_populates="experiences")


class CandidateEducation(Base, TimestampMixin):
    __tablename__ = "candidate_educations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    school: Mapped[str | None] = mapped_column(String(255), index=True)
    degree: Mapped[str | None] = mapped_column(String(255), index=True)
    major: Mapped[str | None] = mapped_column(String(255), index=True)
    start_date: Mapped[str | None] = mapped_column(String(64))
    end_date: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)

    candidate: Mapped["Candidate"] = relationship(back_populates="educations")


class CandidateProject(Base, TimestampMixin):
    __tablename__ = "candidate_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    name: Mapped[str | None] = mapped_column(String(255), index=True)
    role: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[str | None] = mapped_column(String(64))
    end_date: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    technologies: Mapped[str | None] = mapped_column(Text)

    candidate: Mapped["Candidate"] = relationship(back_populates="projects")


class CandidateLink(Base, TimestampMixin):
    __tablename__ = "candidate_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    label: Mapped[str | None] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(512))

    candidate: Mapped["Candidate"] = relationship(back_populates="links")