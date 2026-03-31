from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

PRESENT_TOKENS = {"present", "current", "now", "hiện tại", "nay"}

MONTH_YEAR_RE = re.compile(
    r"(?:(\d{1,2})[/-])?(\d{4})|"
    r"([A-Za-z]+)\s+(\d{4})|"
    r"(\d{4})"
)


@dataclass
class DatePoint:
    year: int
    month: int = 1


def parse_date_point(value: str | None) -> DatePoint | None:
    if not value:
        return None

    raw = value.strip().lower()
    if raw in PRESENT_TOKENS:
        now = datetime.now(timezone.utc)
        return DatePoint(year=now.year, month=now.month)

    match = MONTH_YEAR_RE.search(raw)
    if not match:
        return None

    if match.group(1) and match.group(2):
        month = int(match.group(1))
        year = int(match.group(2))
        if 1 <= month <= 12:
            return DatePoint(year=year, month=month)

    if match.group(3) and match.group(4):
        month_name = match.group(3).lower()
        year = int(match.group(4))
        month = MONTH_MAP.get(month_name)
        if month:
            return DatePoint(year=year, month=month)

    if match.group(5):
        return DatePoint(year=int(match.group(5)), month=1)

    return None


def months_between(start: DatePoint | None, end: DatePoint | None) -> int | None:
    if not start or not end:
        return None
    total = (end.year - start.year) * 12 + (end.month - start.month)
    return max(total, 0)


def merge_overlapping_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []

    ranges = sorted(ranges)
    merged = [ranges[0]]

    for start, end in ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def months_index(point: DatePoint) -> int:
    return point.year * 12 + point.month


def safe_total_experience_months(items: list[tuple[str | None, str | None]]) -> int:
    ranges: list[tuple[int, int]] = []
    for start_raw, end_raw in items:
        start = parse_date_point(start_raw)
        end = parse_date_point(end_raw)
        if not start:
            continue
        if not end:
            now = datetime.now(timezone.utc)
            end = DatePoint(year=now.year, month=now.month)

        start_idx = months_index(start)
        end_idx = months_index(end)
        if end_idx >= start_idx:
            ranges.append((start_idx, end_idx))

    merged = merge_overlapping_ranges(ranges)
    return sum(end - start for start, end in merged)