from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.parser_orchestrator import ParserOptions, ParserOrchestrator
from app.services.parsers import extract_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test CV parser")
    parser.add_argument("target", help="File or folder to parse")
    parser.add_argument("--parser-strategy", default="local", choices=["local", "gemini_first"])
    parser.add_argument("--gemini-api-key", default=None)
    parser.add_argument("--gemini-model", default=None)
    args = parser.parse_args()

    target = Path(args.target)
    files = []
    if target.is_dir():
        for ext in ("*.pdf", "*.docx", "*.txt", "*.png", "*.jpg", "*.jpeg", "*.tif", "*.tiff", "*.webp", "*.bmp"):
            files.extend(sorted(target.glob(ext)))
    else:
        files = [target]

    orchestrator = ParserOrchestrator()
    parser_options = ParserOptions.from_inputs(
        parser_strategy=args.parser_strategy,
        gemini_api_key=args.gemini_api_key,
        gemini_model=args.gemini_model,
    )
    results = []
    for file_path in files:
        file_bytes = file_path.read_bytes()
        parse_result = extract_text(file_bytes, file_path.name)
        extraction, audit, normalized = orchestrator.parse_and_normalize(
            parse_result.text,
            filename=file_path.name,
            parser_meta=parse_result.parser_meta,
            options=parser_options,
        )
        results.append(
            {
                "filename": file_path.name,
                "full_name": normalized.get("full_name"),
                "email": normalized.get("primary_email"),
                "phone": normalized.get("primary_phone"),
                "address": normalized.get("address"),
                "city": normalized.get("city"),
                "current_title": normalized.get("current_title"),
                "current_company": normalized.get("current_company"),
                "total_years_experience": normalized.get("total_years_experience"),
                "skills": normalized.get("normalized_skills", []),
                "education_count": len(normalized.get("education", [])),
                "experience_count": len(normalized.get("experience", [])),
                "project_count": len(normalized.get("projects", [])),
                "review_reasons": normalized.get("review_reasons", []),
                "parse_flags": audit.parse_flags,
                "extractor_backend": audit.extractor_backend,
                "critical_fields": {
                    "name": extraction.full_name.model_dump(),
                    "email": extraction.primary_email.model_dump(),
                    "phone": extraction.primary_phone.model_dump(),
                    "address": extraction.address.model_dump(),
                    "city": extraction.city.model_dump(),
                },
            }
        )

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
