from __future__ import annotations

from app.schemas.candidate import JDRequirement, VectorMetadata
from app.services.normalizer import canonical_degree, canonical_location, canonical_role, canonical_skill
from app.services.query_parser import QueryPlanner
from app.services.taxonomy import SKILL_FAMILIES


class JDParser:
    def __init__(self) -> None:
        self.planner = QueryPlanner()

    def parse(self, jd_text: str) -> JDRequirement:
        plan = self.planner.plan(jd_text)
        role_keywords = [canonical_role(role) or role for role in plan.role_keywords]
        must_have_skills = sorted({canonical_skill(skill) or skill for skill in plan.must_have_skills})
        nice_to_have_skills = sorted(
            {
                canonical_skill(skill) or skill
                for skill in plan.nice_to_have_skills
                if (canonical_skill(skill) or skill) not in must_have_skills
            }
        )
        degree_keywords = sorted({canonical_degree(item) or item for item in plan.degree_keywords})
        location_keywords = sorted({canonical_location(item) or item for item in plan.location_keywords})
        skill_families = sorted(
            {
                SKILL_FAMILIES.get(skill)
                for skill in must_have_skills + nice_to_have_skills
                if SKILL_FAMILIES.get(skill)
            }
        )

        vector_document_parts = [
            f"jd_text: {jd_text.strip()}",
            f"roles: {', '.join(role_keywords)}",
            f"must_have_skills: {', '.join(must_have_skills)}",
            f"nice_to_have_skills: {', '.join(nice_to_have_skills)}",
            f"minimum_years_experience: {plan.minimum_years_experience if plan.minimum_years_experience is not None else ''}",
            f"degrees: {', '.join(degree_keywords)}",
            f"locations: {', '.join(location_keywords)}",
            f"domains: {', '.join(plan.domain_keywords)}",
            f"keywords: {', '.join(plan.query_text_terms)}",
        ]
        vector_document = "\n".join(part for part in vector_document_parts if part.strip())

        metadata = VectorMetadata(
            role=role_keywords[0] if role_keywords else None,
            title=role_keywords[0] if role_keywords else None,
            company=None,
            skills=must_have_skills + [skill for skill in nice_to_have_skills if skill not in must_have_skills],
            skill_families=skill_families,
            degrees=degree_keywords,
            majors=[],
            locations=location_keywords,
            domains=plan.domain_keywords,
            years_experience=plan.minimum_years_experience,
        )

        return JDRequirement(
            raw_text=jd_text,
            canonical_text=jd_text.strip(),
            role_keywords=role_keywords,
            must_have_skills=must_have_skills,
            nice_to_have_skills=nice_to_have_skills,
            degree_keywords=degree_keywords,
            location_keywords=location_keywords,
            domain_keywords=plan.domain_keywords,
            minimum_years_experience=plan.minimum_years_experience,
            vector_document=vector_document,
            vector_metadata=metadata,
        )