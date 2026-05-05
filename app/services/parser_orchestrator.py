from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.schemas.candidate import CandidateExtraction, ExtractionAudit, LinkItem, SkillItem
from app.services.extractor import HybridExtractor
from app.services.gemini_parser import GeminiParserError, GeminiQuotaExceededError, GeminiStructuredParser
from app.services.normalizer import normalize_candidate
from app.services.taxonomy import SKILL_FAMILIES


@dataclass(slots=True)
class ParserOptions:
    parser_strategy: str = "local"
    gemini_api_key: str | None = None
    gemini_model: str | None = None

    @classmethod
    def from_inputs(
        cls,
        *,
        parser_strategy: str | None = None,
        gemini_api_key: str | None = None,
        gemini_model: str | None = None,
    ) -> "ParserOptions":
        settings = get_settings()
        strategy = (parser_strategy or settings.default_parser_strategy or "local").strip().lower()
        if strategy not in {"local", "gemini_first"}:
            strategy = "local"
        api_key = (gemini_api_key or settings.gemini_api_key or "").strip() or None
        model = (gemini_model or settings.gemini_model or "").strip() or None
        return cls(parser_strategy=strategy, gemini_api_key=api_key, gemini_model=model)


class ParserOrchestrator:
    def __init__(self, extractor: HybridExtractor | None = None, gemini_parser: GeminiStructuredParser | None = None) -> None:
        self.extractor = extractor or HybridExtractor()
        self.gemini_parser = gemini_parser or GeminiStructuredParser()

    def parse_and_normalize(
        self,
        raw_text: str,
        *,
        filename: str,
        parser_meta: dict[str, Any] | None,
        options: ParserOptions | None = None,
    ) -> tuple[CandidateExtraction, ExtractionAudit, dict[str, Any]]:
        options = options or ParserOptions.from_inputs()
        local_extraction, local_audit = self.extractor.extract(raw_text, filename=filename, parser_meta=parser_meta or {})

        if options.parser_strategy != "gemini_first":
            audit = self._audit_with_flags(local_audit, extractor_backend=local_audit.extractor_backend, flags=["local_parser_active"])
            return local_extraction, audit, normalize_candidate(local_extraction, audit)

        if not options.gemini_api_key:
            audit = self._audit_with_flags(
                local_audit,
                extractor_backend=f"{local_audit.extractor_backend}+local_fallback",
                flags=["gemini_requested", "gemini_requested_without_api_key", "gemini_fallback_to_local"],
                source_updates={"parser_strategy": options.parser_strategy, "gemini_status": "missing_api_key"},
            )
            return local_extraction, audit, normalize_candidate(local_extraction, audit)

        try:
            gemini_extraction = self.gemini_parser.parse(
                raw_text,
                filename=filename,
                parser_meta=parser_meta or {},
                api_key=options.gemini_api_key,
                model=options.gemini_model,
            )
        except GeminiQuotaExceededError as exc:
            audit = self._audit_with_flags(
                local_audit,
                extractor_backend=f"{local_audit.extractor_backend}+local_fallback",
                flags=["gemini_requested", "gemini_quota_exhausted", "gemini_fallback_to_local"],
                source_updates={
                    "parser_strategy": options.parser_strategy,
                    "gemini_model": options.gemini_model,
                    "gemini_status": "quota_exhausted",
                    "gemini_error": str(exc),
                },
            )
            return local_extraction, audit, normalize_candidate(local_extraction, audit)
        except GeminiParserError as exc:
            audit = self._audit_with_flags(
                local_audit,
                extractor_backend=f"{local_audit.extractor_backend}+local_fallback",
                flags=["gemini_requested", "gemini_failed", "gemini_fallback_to_local"],
                source_updates={
                    "parser_strategy": options.parser_strategy,
                    "gemini_model": options.gemini_model,
                    "gemini_status": "failed",
                    "gemini_error": str(exc),
                },
            )
            return local_extraction, audit, normalize_candidate(local_extraction, audit)

        merged_extraction, merge_meta = self._merge_extractions(local_extraction, gemini_extraction)
        flags = ["gemini_requested", "gemini_success"]
        if merge_meta["overridden_fields"] or merge_meta["skills_added"] or merge_meta["links_added"]:
            flags.append("hybrid_field_backfill")
        audit = self._audit_with_flags(
            local_audit,
            extractor_backend="gemini_structured_with_local_backfill",
            flags=flags,
            source_updates={
                "parser_strategy": options.parser_strategy,
                "gemini_model": options.gemini_model,
                "gemini_status": "success",
                "gemini_overridden_fields": merge_meta["overridden_fields"],
                "gemini_skills_added": merge_meta["skills_added"],
                "gemini_links_added": merge_meta["links_added"],
                "experience_source": merge_meta["experience_source"],
                "education_source": merge_meta["education_source"],
                "project_source": merge_meta["project_source"],
            },
        )
        return merged_extraction, audit, normalize_candidate(merged_extraction, audit)

    def _audit_with_flags(
        self,
        audit: ExtractionAudit,
        *,
        extractor_backend: str,
        flags: list[str],
        source_updates: dict[str, Any] | None = None,
    ) -> ExtractionAudit:
        next_audit = audit.model_copy(deep=True)
        next_audit.extractor_backend = extractor_backend
        next_audit.parse_flags = sorted(set((next_audit.parse_flags or []) + flags))
        source_trace = dict(next_audit.source_trace or {})
        if source_updates:
            source_trace.update(source_updates)
        next_audit.source_trace = source_trace
        return next_audit

    def _merge_field(self, local_field, gemini_field, *, allow_override_for_methods: set[str] | None = None):
        allow_override_for_methods = allow_override_for_methods or {"not_found", "filename_fallback", "location_alias", "location_regex", "header_summary_fallback"}
        if not gemini_field or not gemini_field.value:
            return local_field, False
        if not local_field or not local_field.value:
            return gemini_field, True
        local_method = (local_field.extraction_method or "").lower()
        local_conf = float(local_field.confidence or 0.0)
        gemini_conf = float(gemini_field.confidence or 0.0)
        if local_method in allow_override_for_methods:
            return gemini_field, True
        if local_conf < 0.72 and gemini_conf >= max(local_conf - 0.05, 0.0):
            return gemini_field, True
        if len((gemini_field.value or "").split()) > len((local_field.value or "").split()) + 3 and local_conf < 0.85:
            return gemini_field, True
        return local_field, False

    def _merge_extractions(self, local: CandidateExtraction, gemini: CandidateExtraction) -> tuple[CandidateExtraction, dict[str, Any]]:
        merged = local.model_copy(deep=True)
        overridden_fields: list[str] = []
        critical_fields = [
            "full_name",
            "primary_email",
            "primary_phone",
            "date_of_birth",
            "address",
            "city",
            "summary",
            "current_title",
            "current_company",
        ]
        for field_name in critical_fields:
            chosen, replaced = self._merge_field(getattr(merged, field_name), getattr(gemini, field_name))
            setattr(merged, field_name, chosen)
            if replaced:
                overridden_fields.append(field_name)

        existing_skills = {item.normalized_skill.lower(): item for item in merged.skills}
        skills_added = 0
        for item in gemini.skills:
            key = item.normalized_skill.lower()
            if key in existing_skills:
                continue
            merged.skills.append(
                SkillItem(
                    raw_skill=item.raw_skill,
                    normalized_skill=item.normalized_skill,
                    skill_family=item.skill_family or SKILL_FAMILIES.get(item.normalized_skill),
                    source_section=item.source_section or "llm",
                    evidence_text=item.evidence_text,
                )
            )
            existing_skills[key] = merged.skills[-1]
            skills_added += 1

        experience_source = "local"
        if len(gemini.experiences) > len(local.experiences):
            merged.experiences = [item.model_copy(deep=True) for item in gemini.experiences]
            experience_source = "gemini"

        education_source = "local"
        if len(gemini.educations) > len(local.educations):
            merged.educations = [item.model_copy(deep=True) for item in gemini.educations]
            education_source = "gemini"

        project_source = "local"
        if len(gemini.projects) > len(local.projects):
            merged.projects = [item.model_copy(deep=True) for item in gemini.projects]
            project_source = "gemini"

        existing_links = {item.url.lower(): item for item in merged.social_links}
        links_added = 0
        for item in gemini.social_links:
            url_key = item.url.lower()
            if url_key in existing_links:
                continue
            merged.social_links.append(LinkItem(label=item.label, url=item.url))
            existing_links[url_key] = merged.social_links[-1]
            links_added += 1

        merged.sections_detected = sorted(set((local.sections_detected or []) + (gemini.sections_detected or [])))
        return merged, {
            "overridden_fields": overridden_fields,
            "skills_added": skills_added,
            "links_added": links_added,
            "experience_source": experience_source,
            "education_source": education_source,
            "project_source": project_source,
        }
