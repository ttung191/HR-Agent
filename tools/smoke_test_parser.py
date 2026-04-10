from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.extractor import HybridExtractor
from app.services.normalizer import normalize_candidate
from app.services.parsers import extract_text


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python tools/smoke_test_parser.py <file-or-folder>")
        raise SystemExit(1)

    target = Path(sys.argv[1])
    files = []
    if target.is_dir():
        for ext in ("*.pdf", "*.docx", "*.txt", "*.png", "*.jpg", "*.jpeg", "*.tif", "*.tiff", "*.webp", "*.bmp"):
            files.extend(sorted(target.glob(ext)))
    else:
        files = [target]

    extractor = HybridExtractor()
    results = []
    for file_path in files:
        file_bytes = file_path.read_bytes()
        parse_result = extract_text(file_bytes, file_path.name)
        extraction, audit = extractor.extract(
            parse_result.text,
            filename=file_path.name,
            parser_meta=parse_result.parser_meta,
        )
        normalized = normalize_candidate(extraction, audit)
        results.append(
            {
                "filename": file_path.name,
                "full_name": normalized.get("full_name"),
                "email": normalized.get("primary_email"),
                "phone": normalized.get("primary_phone"),
                "address": normalized.get("address"),
                "current_title": normalized.get("current_title"),
                "current_company": normalized.get("current_company"),
                "total_years_experience": normalized.get("total_years_experience"),
                "skills": normalized.get("normalized_skills", []),
                "education_count": len(normalized.get("education", [])),
                "experience_count": len(normalized.get("experience", [])),
                "project_count": len(normalized.get("projects", [])),
                "review_reasons": normalized.get("review_reasons", []),
                "parse_flags": audit.parse_flags,
            }
        )

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()