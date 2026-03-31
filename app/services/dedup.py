from __future__ import annotations

import hashlib
import re


NON_DIGIT_RE = re.compile(r"\D+")


def file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    return value or None


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = NON_DIGIT_RE.sub("", value)
    if digits.startswith("84") and len(digits) >= 11:
        digits = "0" + digits[2:]
    return digits or None


def normalize_name(value: str | None) -> str | None:
    if not value:
        return None
    lowered = " ".join(value.strip().lower().split())
    return lowered or None


def build_duplicate_key(
    full_name: str | None,
    email: str | None,
    phone: str | None,
) -> str | None:
    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)
    normalized_name = normalize_name(full_name)

    if normalized_email:
        return f"email:{normalized_email}"

    if normalized_phone:
        return f"phone:{normalized_phone}"

    if normalized_name:
        return f"name:{normalized_name}"

    return None