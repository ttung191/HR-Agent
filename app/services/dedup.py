from __future__ import annotations

import hashlib


def file_sha256(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def build_duplicate_key(full_name: str | None, primary_email: str | None, primary_phone: str | None) -> str | None:
    candidate_key = "|".join(
        [
            (full_name or "").strip().lower(),
            (primary_email or "").strip().lower(),
            (primary_phone or "").strip().lower(),
        ]
    )
    normalized = candidate_key.strip("|")
    return normalized or None
