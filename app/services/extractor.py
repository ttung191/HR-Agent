from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any

from app.schemas.candidate import (
    CandidateExtraction,
    EducationItem,
    ExperienceItem,
    ExtractedField,
    ExtractionAudit,
    LinkItem,
    ProjectItem,
    SkillItem,
)
from app.services.cv_classifier import (
    CVClassifier,
    filename_to_person_name,
    is_generic_filename,
    is_section_heading,
    looks_like_human_name,
)
from app.services.resolution import FieldCandidate, SkillCandidate, resolve_field_candidates, resolve_skill_candidates
from app.services.taxonomy import (
    JOB_TITLE_TOKENS,
    LOCATION_ALIASES,
    ROLE_ALIASES,
    SECTION_ALIASES,
    SKILL_ALIASES,
    SKILL_FAMILIES,
)

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?84\s*)?(?:0?\d[\s\d]{7,12}\d)")
URL_RE = re.compile(r"https?://\S+|(?:linkedin|github|facebook)\.com/\S+", re.I)
DOB_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b")
DATE_TOKEN_RE = r"(?:T?\d{1,2}[/-]\d{1,2}[/-]\d{4}|T?\d{1,2}[/-]\d{4}|[A-Za-z]+\s+\d{4}|\d{4}|present|current|now|hiện tại|hiện nay|nay|Present|NOW|HIỆN TẠI|HIỆN NAY)"
DATE_RANGE_RE = re.compile(rf"(?P<start>{DATE_TOKEN_RE})\s*(?:-|–|—|to|TO)\s*(?P<end>{DATE_TOKEN_RE})", re.I)
LOCATION_RE = re.compile(r"\b(ha noi|hanoi|ho chi minh|hcm|da nang|remote|finland|belgium|hai duong)\b", re.I)
BULLET_PREFIX_RE = re.compile(r"^[\-•●▪◦‣]+\s*")
TEMPORAL_BAD_NAME_RE = re.compile(r"\b(hiện tại|present|current|nay)\b", re.I)
SUMMARY_BAD_LINE_RE = re.compile(r"\b(gpa|cpa|toeic|ielts|sat|gre|topik)\b|^\s*(\d{2}/\d{4}|\d{4})\s*$", re.I)
PROJECT_TITLE_RE = re.compile(r"^\s*(\d+[\.)])\s*(.+)$")
ROLE_LINE_RE = re.compile(r"^\s*role\s*:\s*(.+)$", re.I)
WORD_RE = re.compile(r"[A-Za-zÀ-ỹ0-9+#./-]+", re.UNICODE)
COMPANY_HINT_RE = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|company|co\.?|group|solutions|technology|tech|software|systems|labs|studio|university|bank|global|công ty|ngân hàng|shop|freelance|logistics|quasoft|mindx|isofh|tnex|fss|cmc)\b",
    re.I,
)
LEADING_GLYPH_RE = re.compile(r"^[^0-9A-Za-zÀ-ỹ]+", re.UNICODE)
TOPCV_BOILERPLATE_RE = re.compile(
    r"topcv|tuyendung\.topcv|nền tảng tuyển dụng nhân sự hàng đầu việt nam|ứng viên .*\| nguồn",
    re.I,
)
TOKEN_BOUNDARY_CLASS = r"A-Za-zÀ-ỹ0-9#+./-"
ADDRESS_HINT_RE = re.compile(
    r"\b(ngõ|ngo|đường|duong|street|st\.|road|district|ward|phường|phuong|quận|quan|thành phố|thanh pho|city|huyện|huyen|xã|xa|tỉnh|tinh|khương|xuân|lê văn lương|lê duẩn|dong da|đống đa)\b",
    re.I,
)
ROLE_PHRASE_HINT_RE = re.compile(
    r"\b(ai engineer|llm engineer|genai engineer|rag engineer|machine learning engineer|ml engineer|data scientist|data engineer|backend engineer|frontend engineer|fullstack engineer|software engineer|software developer|developer|engineer|scientist|analyst|intern|fresher|thực tập sinh|kỹ sư|chuyên viên|quản lý shop|sale executive|shop manager|product specialist)\b",
    re.I,
)
GENDER_LINE_RE = re.compile(r"^(nam|nu|nữ|male|female)$", re.I)
TRUNCATED_EMAIL_RE = re.compile(r"([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z])(?:…|\.\.\.)?", re.I)
CONTACT_LABEL_RE = re.compile(r"^(date of birth|dob|ngày sinh|giới tính|gender|điện thoại|phone|email|địa chỉ|address|website|contact)\s*[:：-]?\s*(.+)$", re.I)
NON_COMPANY_LABEL_RE = re.compile(r"^(điện thoại|phone|email|website|địa chỉ|address|date of birth|ngày sinh|giới tính|gender)\b", re.I)
ROLE_DATE_AT_END_RE = re.compile(rf"^(.+?)\s*\|\s*(?P<start>{DATE_TOKEN_RE})\s*(?:-|–|—|to)\s*(?P<end>{DATE_TOKEN_RE})$", re.I)
CONTACT_NOISE_RE = re.compile(r"^(nam|nữ|nu|male|female|điện thoại|phone|email|website|contact)$", re.I)
SCHOOL_HINT_RE = re.compile(r"\b(university|college|institute|academy|school|đại học|cao đẳng|hoc vien|học viện)\b", re.I)
PROGRAM_HINT_RE = re.compile(r"\b(programme|program|major|chuyên ngành|ngành|field of study)\b", re.I)
COURSE_HINT_RE = re.compile(r"\b(course|coursera|w3school|certificate|certification|khóa học|khoa hoc)\b", re.I)
PROJECT_HINT_RE = re.compile(r"\b(dự án|du an|project|kaggle|dataset|chatbot|agent|fraud detection)\b", re.I)
PROJECT_META_LABEL_RE = re.compile(r"^(khách hàng|mo ta du an|mô tả dự án|mô tả|so luong thanh vien|số lượng thành viên|vi tri cong viec|vị trí công việc|vai tro trong du an|vai trò trong dự án|cong nghe su dung|công nghệ sử dụng|impact|link|role)\b", re.I)
URLISH_RE = re.compile(r"(?:https?://|www\.|[A-Za-z0-9-]+\.[A-Za-z]{2,}/|[?=&%])", re.I)
FOOTER_NOISE_RE = re.compile(r"^(aid:|©\s*topcv|topcv\s*-|ứng tuyển|ung tuyen)", re.I)
EXPERIENCE_STOP_RE = re.compile(r"^(programme|program|frameworks|databases|devops|data analysis libraries|languages|technical skills|contact|about me|hobbies|honours|activities)\b", re.I)
PROJECT_STOP_RE = re.compile(r"^(hobbies|honours|activities|so thich|sở thích|mục tiêu|muc tieu|technical skills|contact|education|work experience)\b", re.I)
LOCATION_ONLY_PARTS_RE = re.compile(r"^[A-ZÀ-Ỹ][^@]*?(hà nội|ha noi|thanh xuân|thanh xuan|long biên|long bien|định công|dinh cong|hải dương|hai duong|finland|belgium|remote)", re.I)
NON_WORK_TITLE_RE = re.compile(r"^(sinh viên|hoc vien|học viên|student|internship project|team member)$", re.I)
ORG_FRAGMENT_RE = re.compile(r"^(công ty|company|shop|school|học viện|hoc vien|đại học|university|ngân hàng|bank)\b", re.I)
PROJECT_EXPERIENCE_HINT_RE = re.compile(r"\b(dự án cá nhân|du an ca nhan|kaggle|dataset|fraud detection|innovation project|team member|người hỗ trợ|mentor|research project)\b", re.I)
DEGREE_TOKEN_RE = re.compile(r"\b(bachelor|master|phd|doctor|cử nhân|thạc sĩ|tiến sĩ)\b", re.I)
MAJOR_TOKEN_RE = re.compile(r"\b(computer science|information technology|software engineering|data science|artificial intelligence|energy technology|environmental engineering|toán ứng dụng|tin học|international economy)\b", re.I)
COURSE_NOISE_RE = re.compile(r"\b(course|certificate|certification|thesis|machine learning|cloud platforms|data analysis with python|neural networks)\b", re.I)


def _ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


SECTION_ALIAS_TO_CANONICAL = {
    alias.lower(): canonical
    for canonical, aliases in SECTION_ALIASES.items()
    for alias in ([canonical] + aliases)
}


class HybridExtractor:
    def __init__(self) -> None:
        self.classifier = CVClassifier()
        self._skill_patterns = {
            alias: self._build_skill_pattern(alias)
            for alias in sorted(SKILL_ALIASES.keys(), key=len, reverse=True)
        }

    def _build_skill_pattern(self, alias: str) -> re.Pattern[str]:
        escaped = re.escape(alias).replace(r"\ ", r"\s+")
        return re.compile(rf"(?<![{TOKEN_BOUNDARY_CLASS}]){escaped}(?![{TOKEN_BOUNDARY_CLASS}])", re.I)

    def _strip_leading_glyphs(self, text: str) -> str:
        return LEADING_GLYPH_RE.sub("", text or "").strip()

    def _clean_line(self, value: str | None) -> str:
        value = unicodedata.normalize("NFC", value or "")
        value = self._strip_leading_glyphs(value)
        value = BULLET_PREFIX_RE.sub("", value)
        value = value.replace("￾", "")
        return " ".join(value.split()).strip("|:- ")

    def _clean_entity_fragment(self, value: str | None) -> str | None:
        text = self._clean_line(value)
        if not text:
            return None
        text = re.sub(r"[\(\[]+$", "", text).strip()
        text = re.sub(r"\s{2,}", " ", text).strip(" ,;:-")
        return text or None

    def _normalize_date_token(self, value: str | None) -> str | None:
        if not value:
            return None
        token = self._clean_line(value)
        token = re.sub(r"^t(?=\d)", "", token, flags=re.I)
        lowered = token.lower()
        if lowered in {"present", "current", "now", "hiện tại", "hiện nay", "nay"}:
            return "Present" if lowered in {"present", "current", "now"} else "Hiện tại"
        return token

    def _normalize_phone(self, value: str) -> str:
        digits = re.sub(r"\D", "", value or "")
        if not digits:
            return digits
        if digits.startswith("84") and len(digits) >= 11:
            digits = f"0{digits[2:]}"
        elif len(digits) == 9 and not digits.startswith("0"):
            digits = f"0{digits}"
        if len(digits) > 10 and digits.startswith("0"):
            digits = digits[:10]
        return digits

    def _clean_address(self, value: str | None) -> str:
        text = self._clean_line(value or "")
        text = re.sub(r"^(địa chỉ|dia chi|address|contact)\s*[:：-]?\s*", "", text, flags=re.I)
        text = re.sub(r"\bwebsite\b\s*[:：-]?\s*", "", text, flags=re.I)
        text = re.sub(r"\s{2,}", " ", text).strip(",;:- ")
        return text

    def _canonical_section_name(self, text: str) -> str | None:
        normalized = _ascii_fold(self._clean_line(text)).lower().strip(" :-•|\t")
        return SECTION_ALIAS_TO_CANONICAL.get(normalized)

    def _inline_heading_prefix(self, line: str) -> tuple[str | None, str]:
        clean = self._clean_line(line)
        upper_prefix_match = re.match(r"^([A-ZÀ-Ỹ][A-ZÀ-Ỹ /&-]{2,30})\s+(.+)$", clean)
        if not upper_prefix_match:
            return None, clean
        heading_token = self._clean_line(upper_prefix_match.group(1))
        canonical = self._canonical_section_name(heading_token)
        if canonical and canonical != "header":
            return canonical, self._clean_line(upper_prefix_match.group(2))
        return None, clean

    def _is_boilerplate_line(self, text: str | None) -> bool:
        cleaned = self._clean_line(text)
        return bool(cleaned and TOPCV_BOILERPLATE_RE.search(cleaned))

    def _combine_section_values(self, layout_value: str, text_value: str) -> str:
        seen: set[str] = set()
        output: list[str] = []
        for line in [*layout_value.splitlines(), *(text_value or "").splitlines()]:
            clean = " ".join(line.split()).strip()
            if not clean:
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            output.append(clean)
        return "\n".join(output)

    def _split_sections_from_text(self, text: str) -> dict[str, str]:
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        sections: dict[str, list[str]] = defaultdict(list)
        current = "header"

        for raw_line in lines:
            line = self._clean_line(raw_line)
            if not line or self._is_boilerplate_line(line):
                continue

            canonical = self._canonical_section_name(line)
            if canonical:
                current = canonical
                continue

            inline_canonical, remainder = self._inline_heading_prefix(line)
            if inline_canonical:
                current = inline_canonical
                if remainder:
                    sections[current].append(remainder)
                continue

            normalized = line.lower().strip(" :-•|\t")
            matched = False
            if len(normalized) <= 50:
                for canonical_name, aliases in SECTION_ALIASES.items():
                    if normalized == canonical_name or normalized in aliases or any(normalized.startswith(f"{alias}:") for alias in aliases):
                        current = canonical_name
                        matched = True
                        break
            if matched:
                continue

            sections[current].append(line)

        return {key: "\n".join(value).strip() for key, value in sections.items() if value}

    def _infer_column_split(self, lines: list[dict[str, Any]], page_width: float) -> float:
        heading_xs = sorted(
            {
                round(float(item.get("x0") or 0.0), 2)
                for item in lines
                if self._canonical_section_name(str(item.get("text", "")))
            }
        )
        if len(heading_xs) >= 2:
            gaps = [
                (heading_xs[i + 1] - heading_xs[i], heading_xs[i], heading_xs[i + 1])
                for i in range(len(heading_xs) - 1)
            ]
            best_gap, left_x, right_x = max(gaps, key=lambda item: item[0])
            if best_gap >= 60:
                return (left_x + right_x) / 2.0
        return page_width * 0.5 if page_width > 0 else 220.0

    def _split_sections_from_layout(self, parser_meta: dict) -> dict[str, str]:
        lines = parser_meta.get("all_page_layout_lines") or parser_meta.get("first_page_layout_lines") or []
        if not lines:
            return {}

        page_dimensions = parser_meta.get("page_dimensions") or {}
        grouped_by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for item in lines:
            grouped_by_page[int(item.get("page") or 1)].append(item)

        assigned: dict[str, list[tuple[int, float, float, str]]] = defaultdict(list)
        last_heading_by_column: dict[str, str | None] = {"left": None, "right": None}

        for page in sorted(grouped_by_page.keys()):
            page_lines = grouped_by_page[page]
            page_width = float((page_dimensions.get(str(page)) or {}).get("width") or 0.0)
            if page_width <= 0:
                page_width = max(float(item.get("x1") or 0.0) for item in page_lines) + 1.0

            split_x = self._infer_column_split(page_lines, page_width)
            ordered = sorted(page_lines, key=lambda item: (float(item.get("y0") or 0.0), float(item.get("x0") or 0.0)))
            current_heading_by_column = dict(last_heading_by_column)
            page_heading_seen = False

            for item in ordered:
                raw_text = " ".join(str(item.get("text", "")).split()).strip()
                if not raw_text:
                    continue

                x0 = float(item.get("x0") or 0.0)
                y0 = float(item.get("y0") or 0.0)
                column = "left" if x0 < split_x else "right"

                canonical = self._canonical_section_name(raw_text)
                if canonical and (float(item.get("font_size") or 0.0) >= 13.0 or item.get("is_bold")):
                    current_heading_by_column[column] = canonical
                    page_heading_seen = True
                    continue

                text = self._clean_line(raw_text)
                if not text or self._is_boilerplate_line(text):
                    continue

                target_section = current_heading_by_column.get(column)
                if not target_section:
                    if page == min(grouped_by_page.keys()) and not page_heading_seen:
                        target_section = "header"
                    else:
                        target_section = current_heading_by_column.get("left") or current_heading_by_column.get("right")
                if not target_section:
                    continue

                assigned[target_section].append((page, y0, x0, text))

            last_heading_by_column = current_heading_by_column

        sections: dict[str, str] = {}
        for section_name, items in assigned.items():
            items = sorted(items, key=lambda pair: (pair[0], pair[1], pair[2]))
            text = "\n".join(item[3] for item in items).strip()
            if text:
                sections[section_name] = text
        return sections

    def _sanitize_merged_section(self, section_name: str, text: str) -> str:
        if not text:
            return text
        output: list[str] = []
        for raw_line in text.splitlines():
            line = self._clean_line(raw_line)
            if not line or self._is_boilerplate_line(line) or FOOTER_NOISE_RE.search(line):
                continue

            canonical = self._canonical_section_name(line)
            inline_canonical, remainder = self._inline_heading_prefix(line)
            foreign_section = canonical or inline_canonical
            if foreign_section and foreign_section != section_name and section_name != "header":
                break

            folded = _ascii_fold(line).lower()
            if section_name in {"experience", "education", "projects"}:
                if EMAIL_RE.search(line) or PHONE_RE.search(line) or CONTACT_LABEL_RE.match(line):
                    break
                if section_name != "projects" and URL_RE.search(line):
                    break
                if looks_like_human_name(line) and line.isupper() and output:
                    break
                if re.search(r"\b(short-term goals|long-term goals|muc tieu)\b", folded):
                    break
                if section_name == "projects" and PROJECT_STOP_RE.match(line):
                    break
                if section_name == "experience" and EXPERIENCE_STOP_RE.match(line):
                    break

            output.append(remainder if inline_canonical and remainder else line)
        return "\n".join(output).strip()

    def _merge_sections(self, layout_sections: dict[str, str], text_sections: dict[str, str]) -> dict[str, str]:
        merged: dict[str, str] = {}
        for key in sorted(set(layout_sections) | set(text_sections)):
            layout_value = self._sanitize_merged_section(key, layout_sections.get(key, ""))
            text_value = self._sanitize_merged_section(key, text_sections.get(key, ""))

            if layout_value and text_value:
                if key in {"experience", "education", "projects"} and (EMAIL_RE.search(text_value) or PHONE_RE.search(text_value)):
                    merged[key] = layout_value
                elif key in {"experience", "education"} and len(text_value.splitlines()) > len(layout_value.splitlines()) * 2 and any(marker in _ascii_fold(text_value).lower() for marker in ["skills", "honours", "hobbies", "thông tin", "thong tin"]):
                    merged[key] = layout_value
                else:
                    merged[key] = self._combine_section_values(layout_value, text_value)
            else:
                merged[key] = layout_value or text_value
        return {key: value for key, value in merged.items() if value}

    def _score_name_line(self, line: str) -> float:
        cleaned = self._clean_line(line)
        if not cleaned or is_section_heading(cleaned):
            return -1.0
        if self._is_boilerplate_line(cleaned):
            return -1.0
        if EMAIL_RE.search(cleaned) or PHONE_RE.search(cleaned) or URL_RE.search(cleaned):
            return -1.0
        if TEMPORAL_BAD_NAME_RE.search(cleaned):
            return -1.0
        if any(char.isdigit() for char in cleaned):
            return -0.8
        if len(cleaned) > 48:
            return -0.4
        if not looks_like_human_name(cleaned):
            return -0.3

        score = 0.6
        if cleaned.isupper():
            score += 0.2
        if 2 <= len(cleaned.split()) <= 4:
            score += 0.1
        if len(cleaned.split()) >= 2:
            score += 0.05
        return min(score, 0.98)

    def _extract_name_from_layout(self, parser_meta: dict) -> FieldCandidate | None:
        layout_lines = parser_meta.get("first_page_layout_lines") or []
        page_height = float(parser_meta.get("first_page_height") or 0.0)
        if not layout_lines:
            return None

        max_font = max(float(item.get("font_size") or 0.0) for item in layout_lines) or 1.0
        top_zone_limit = page_height * 0.38 if page_height > 0 else 260.0

        candidates: list[tuple[float, dict[str, Any]]] = []
        for item in layout_lines:
            text = self._clean_line(str(item.get("text", "")))
            if not text:
                continue
            if float(item.get("y0") or 0.0) > top_zone_limit:
                continue
            if is_section_heading(text) or self._is_boilerplate_line(text):
                continue
            if EMAIL_RE.search(text) or PHONE_RE.search(text) or URL_RE.search(text):
                continue
            if TEMPORAL_BAD_NAME_RE.search(text):
                continue
            if not looks_like_human_name(text):
                continue

            font_score = float(item.get("font_size") or 0.0) / max_font
            top_score = 1.0 - min(float(item.get("y0") or 0.0) / max(top_zone_limit, 1.0), 1.0)
            bold_bonus = 0.07 if item.get("is_bold") else 0.0
            upper_bonus = 0.08 if text.isupper() else 0.0
            score = 0.58 * font_score + 0.24 * top_score + bold_bonus + upper_bonus
            candidates.append((score, item))

        if not candidates:
            return None

        score, best = sorted(candidates, key=lambda pair: pair[0], reverse=True)[0]
        text = self._clean_line(str(best["text"]))
        return FieldCandidate(
            value=text,
            confidence=round(min(max(score, 0.0), 0.99), 3),
            evidence_text=text,
            source_section="header",
            extraction_method="layout_top_font_name",
            priority=0,
        )

    def _collect_name_candidates(self, header: str, filename: str, parser_meta: dict) -> tuple[ExtractedField, list[dict[str, Any]]]:
        candidates: list[FieldCandidate] = []
        layout_name = self._extract_name_from_layout(parser_meta)
        if layout_name and layout_name.value:
            candidates.append(layout_name)

        header_lines = [self._clean_line(line) for line in header.splitlines()[:12] if line.strip()]
        for line in header_lines:
            score = self._score_name_line(line)
            if score > 0:
                candidates.append(FieldCandidate(value=line, confidence=round(score, 3), evidence_text=line, source_section="header", extraction_method="header_name_line", priority=1))

        fallback_name = filename_to_person_name(filename)
        if fallback_name:
            candidates.append(FieldCandidate(value=fallback_name, confidence=0.20, evidence_text=filename, source_section="filename", extraction_method="filename_fallback", priority=9))

        winner, trace = resolve_field_candidates("full_name", candidates)
        if winner:
            return ExtractedField(value=winner.value, confidence=winner.confidence, evidence_text=winner.evidence_text, source_section=winner.source_section, extraction_method=winner.extraction_method), trace
        return ExtractedField(value=None, confidence=0.0, extraction_method="not_found"), trace

    def _looks_like_heading_noise(self, value: str | None) -> bool:
        text = _ascii_fold(self._clean_line(value)).lower()
        if not text:
            return False
        heading_terms = {
            "so thich", "hoc van", "kinh nghiem lam viec", "ky nang", "cacs ky nang", "cac ky nang",
            "work experience", "education", "skills", "activities", "honours", "project", "projects",
            "contact", "cac cong viec da trai qua", "muc tieu nghe nghiep", "muc tieu", "about me"
        }
        return text in heading_terms

    def _looks_like_role_text(self, value: str | None) -> bool:
        text = self._clean_line(value)
        if not text:
            return False
        lowered = text.lower()
        if self._is_boilerplate_line(text):
            return False
        if EMAIL_RE.search(text) or PHONE_RE.search(text) or URL_RE.search(text):
            return False
        if NON_COMPANY_LABEL_RE.search(lowered) or self._looks_like_heading_noise(text):
            return False
        if len(text.split()) > 9:
            return False
        if ROLE_PHRASE_HINT_RE.search(lowered):
            return True
        for canonical, aliases in ROLE_ALIASES.items():
            if canonical in lowered or any(alias in lowered for alias in aliases):
                return True
        tokens = set(WORD_RE.findall(lowered))
        return len(tokens & JOB_TITLE_TOKENS) >= 1

    def _looks_like_location_only(self, value: str | None) -> bool:
        text = self._clean_line(value)
        if not text:
            return False
        lowered = _ascii_fold(text).lower()
        if ADDRESS_HINT_RE.search(text):
            return True
        alias_hits = 0
        for aliases in LOCATION_ALIASES.values():
            for alias in aliases:
                if alias in lowered:
                    alias_hits += 1
                    break
        if alias_hits >= 1 and not COMPANY_HINT_RE.search(text):
            return True
        if "," in text and LOCATION_ONLY_PARTS_RE.search(text) and not COMPANY_HINT_RE.search(text):
            return True
        return False

    def _sanitize_company_value(self, value: str | None) -> str | None:
        text = self._clean_entity_fragment(value)
        if not text:
            return None
        lowered = text.lower()
        if self._looks_like_location_only(text):
            return None
        if lowered in SKILL_ALIASES or COURSE_NOISE_RE.search(lowered):
            return None
        if len(text.split()) > 10 and not COMPANY_HINT_RE.search(text):
            return None
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) >= 2:
            trailing = parts[-1]
            trailing_folded = _ascii_fold(trailing).lower()
            if self._looks_like_location_only(trailing) or any(alias == trailing_folded or alias in trailing_folded for aliases in LOCATION_ALIASES.values() for alias in aliases):
                stripped = ", ".join(parts[:-1]).strip()
                if stripped and not self._looks_like_location_only(stripped):
                    text = stripped
        return text

    def _looks_like_company_text(self, value: str | None) -> bool:
        text = self._clean_line(value)
        if not text:
            return False
        lowered = text.lower()
        if self._is_boilerplate_line(text):
            return False
        if EMAIL_RE.search(text) or PHONE_RE.search(text) or URL_RE.search(text):
            return False
        if DATE_RANGE_RE.search(text) or DOB_RE.search(text):
            return False
        if GENDER_LINE_RE.fullmatch(lowered):
            return False
        if self._looks_like_heading_noise(text):
            return False
        if NON_COMPANY_LABEL_RE.search(lowered):
            return False
        if self._looks_like_location_only(text):
            return False
        if self._looks_like_role_text(text):
            return False
        if is_section_heading(text):
            return False
        if ADDRESS_HINT_RE.search(text) or any(char.isdigit() for char in text):
            return False
        if text.endswith("."):
            return False
        if COMPANY_HINT_RE.search(text):
            return True
        if text.isupper() and 2 <= len(text) <= 28:
            return True
        words = text.split()
        if 1 <= len(words) <= 9 and sum(1 for word in words if word[:1].isupper() or word.isupper()) >= max(1, len(words) - 1):
            return True
        return False

    def _is_company_continuation(self, previous: str, current: str) -> bool:
        prev = self._clean_line(previous)
        cur = self._clean_line(current)
        if not prev or not cur:
            return False
        if DATE_RANGE_RE.search(cur) or self._looks_like_role_text(cur) or EMAIL_RE.search(cur) or PHONE_RE.search(cur):
            return False
        if self._looks_like_company_text(prev) and len(cur.split()) <= 5:
            return True
        if ORG_FRAGMENT_RE.search(prev):
            return True
        if prev.lower().endswith(("phần", "cổ", "soft", "tech", "bank", "tnhh", "co", "company")):
            return True
        return False

    def _merge_broken_header_lines(self, lines: list[str]) -> list[str]:
        merged: list[str] = []
        for line in [self._clean_line(item) for item in lines if self._clean_line(item)]:
            if merged and self._is_company_continuation(merged[-1], line):
                merged[-1] = self._clean_entity_fragment(f"{merged[-1]} {line}") or merged[-1]
            else:
                merged.append(line)
        return merged

    def _split_role_company_line(self, line: str) -> tuple[str | None, str | None]:
        text = self._clean_line(line)
        if not text:
            return None, None

        def validate(left: str, right: str) -> tuple[str | None, str | None]:
            left = self._clean_line(left)
            right = self._clean_line(right)
            if self._looks_like_role_text(left) and self._looks_like_company_text(right):
                return left, self._sanitize_company_value(right)
            if self._looks_like_company_text(left) and self._looks_like_role_text(right):
                return right, self._sanitize_company_value(left)
            return None, None

        if "|" in text:
            parts = [part.strip() for part in text.split("|") if part.strip()]
            if len(parts) >= 2:
                role, company = validate(parts[0], parts[1])
                if role or company:
                    return role, company

        if " at " in text.lower():
            parts = re.split(r"\bat\b", text, maxsplit=1, flags=re.I)
            if len(parts) == 2:
                role, company = validate(parts[0], parts[1])
                if role or company:
                    return role, company

        for separator in [" - ", " — ", " – "]:
            if separator in text:
                left, right = [part.strip() for part in text.split(separator, 1)]
                role, company = validate(left, right)
                if role or company:
                    return role, company

        comma_parts = [part.strip() for part in re.split(r",\s*", text) if part.strip()]
        if len(comma_parts) >= 2:
            for pivot in range(1, len(comma_parts)):
                left = ", ".join(comma_parts[:pivot])
                right = ", ".join(comma_parts[pivot:])
                role, company = validate(left, right)
                if role or company:
                    return role, company

        return None, None

    def _extract_title_from_layout(self, parser_meta: dict, full_name: str | None) -> FieldCandidate | None:
        layout_lines = parser_meta.get("first_page_layout_lines") or []
        if not layout_lines or not full_name:
            return None

        name_item: dict[str, Any] | None = None
        heading_ys = [float(item.get("y0") or 0.0) for item in layout_lines if self._canonical_section_name(str(item.get("text", "")))]
        first_heading_y = min(heading_ys) if heading_ys else 9999.0

        for item in layout_lines:
            if self._clean_line(str(item.get("text", ""))) == full_name:
                name_item = item
                break
        if not name_item:
            return None

        name_y = float(name_item.get("y0") or 0.0)
        name_x = float(name_item.get("x0") or 0.0)

        candidates: list[FieldCandidate] = []
        for item in layout_lines:
            text = self._clean_line(str(item.get("text", "")))
            if not text or text == full_name:
                continue
            y0 = float(item.get("y0") or 0.0)
            x0 = float(item.get("x0") or 0.0)
            if not (name_y < y0 <= min(name_y + 70.0, first_heading_y)):
                continue
            if abs(x0 - name_x) > 70:
                continue
            if EMAIL_RE.search(text) or PHONE_RE.search(text) or URL_RE.search(text):
                continue
            if self._is_boilerplate_line(text) or is_section_heading(text):
                continue
            if not self._looks_like_role_text(text):
                continue
            candidates.append(FieldCandidate(value=text, confidence=0.92, evidence_text=text, source_section="header", extraction_method="layout_line_below_name", priority=0))

        winner, _ = resolve_field_candidates("current_title", candidates)
        return winner

    def _collect_header_role_company_candidates(self, header: str, full_name: str | None, parser_meta: dict) -> tuple[list[FieldCandidate], list[FieldCandidate]]:
        title_candidates: list[FieldCandidate] = []
        company_candidates: list[FieldCandidate] = []

        layout_title = self._extract_title_from_layout(parser_meta, full_name)
        if layout_title and layout_title.value:
            title_candidates.append(layout_title)

        lines = [self._clean_line(line) for line in header.splitlines()[:14] if line.strip()]
        lines = self._merge_broken_header_lines(lines)
        for line in lines:
            clean = self._clean_line(line)
            if not clean or (full_name and clean == full_name):
                continue
            if self._is_boilerplate_line(clean):
                continue
            if EMAIL_RE.search(clean) or PHONE_RE.search(clean) or URL_RE.search(clean):
                continue
            if is_section_heading(clean) or SUMMARY_BAD_LINE_RE.search(clean):
                continue
            if DOB_RE.fullmatch(clean) or GENDER_LINE_RE.fullmatch(clean.lower()):
                continue

            split_title, split_company = self._split_role_company_line(clean)
            if split_title:
                title_candidates.append(FieldCandidate(value=split_title, confidence=0.93, evidence_text=clean, source_section="header", extraction_method="header_role_company_split", priority=0))
            if split_company:
                sanitized_company = self._sanitize_company_value(split_company)
                if sanitized_company:
                    company_candidates.append(FieldCandidate(value=sanitized_company, confidence=0.90, evidence_text=clean, source_section="header", extraction_method="header_role_company_split", priority=0))

            if self._looks_like_role_text(clean):
                title_candidates.append(FieldCandidate(value=clean, confidence=0.80, evidence_text=clean, source_section="header", extraction_method="header_title_line", priority=2))
            elif self._looks_like_company_text(clean):
                sanitized_company = self._sanitize_company_value(clean)
                if sanitized_company:
                    company_candidates.append(FieldCandidate(value=sanitized_company, confidence=0.66, evidence_text=clean, source_section="header", extraction_method="header_company_line", priority=4))

        return title_candidates, company_candidates

    def _recover_truncated_email(self, text: str) -> tuple[str | None, float, str]:
        cleaned = self._clean_line(text)
        if not cleaned or "@" not in cleaned:
            return None, 0.0, "not_found"
        exact = EMAIL_RE.search(cleaned)
        if exact:
            return exact.group(0), 0.99, "regex_email"

        lowered = cleaned.lower().replace("...", "").replace("…", "")
        lowered = lowered.replace(" ", "")
        match = TRUNCATED_EMAIL_RE.search(cleaned)
        local_part = None
        domain_hint = None
        if match:
            raw = match.group(1).replace(" ", "")
            local_part, _, domain_hint = raw.partition("@")
        else:
            local_part, _, domain_hint = lowered.partition("@")

        if not local_part or not domain_hint:
            return None, 0.0, "not_found"

        fixups = {
            "gmail.c": "gmail.com",
            "gmail.co": "gmail.com",
            "gmail.con": "gmail.com",
            "outlook.c": "outlook.com",
            "outlook.co": "outlook.com",
            "hotmail.c": "hotmail.com",
            "hotmail.co": "hotmail.com",
            "yahoo.c": "yahoo.com",
            "yahoo.co": "yahoo.com",
        }
        for prefix, target in fixups.items():
            if domain_hint.startswith(prefix):
                return f"{local_part}@{target}", 0.72, "email_truncated_domain_fixup"

        if domain_hint.endswith("."):
            return f"{local_part}@{domain_hint}com", 0.55, "email_missing_tld_suffix"
        return None, 0.0, "not_found"

    def _layout_header_lines(self, parser_meta: dict) -> list[str]:
        lines = parser_meta.get("first_page_layout_lines") or []
        heading_ys = [float(item.get("y0") or 0.0) for item in lines if self._canonical_section_name(str(item.get("text", "")))]
        first_heading_y = min(heading_ys) if heading_ys else 320.0
        output: list[str] = []
        for item in lines:
            y0 = float(item.get("y0") or 0.0)
            if y0 > max(first_heading_y, 285.0):
                continue
            text = self._clean_line(str(item.get("text", "")))
            if text and not self._is_boilerplate_line(text):
                output.append(text)
        return self._merge_broken_header_lines(output)

    def _extract_email_field(self, raw_text: str, parser_meta: dict) -> tuple[ExtractedField, list[dict[str, Any]]]:
        candidates: list[FieldCandidate] = []
        exact = EMAIL_RE.search(raw_text)
        if exact:
            candidates.append(FieldCandidate(value=exact.group(0), confidence=0.99, evidence_text=exact.group(0), source_section="header", extraction_method="regex_email", priority=0))

        recovered, confidence, method = self._recover_truncated_email(raw_text)
        if recovered:
            candidates.append(FieldCandidate(value=recovered, confidence=confidence, evidence_text=recovered, source_section="header", extraction_method=method, priority=3))

        for text in self._layout_header_lines(parser_meta):
            match = CONTACT_LABEL_RE.match(text)
            if match and match.group(1).lower().startswith(("email",)):
                recovered, confidence, method = self._recover_truncated_email(match.group(2))
                if recovered:
                    candidates.append(FieldCandidate(value=recovered, confidence=max(confidence, 0.93), evidence_text=text, source_section="header", extraction_method="layout_label_email", priority=0))
            recovered, confidence, method = self._recover_truncated_email(text)
            if recovered:
                candidates.append(FieldCandidate(value=recovered, confidence=confidence, evidence_text=text, source_section="header", extraction_method=method, priority=1))

        winner, trace = resolve_field_candidates("primary_email", candidates)
        if winner:
            return ExtractedField(value=winner.value, confidence=winner.confidence, evidence_text=winner.evidence_text, source_section=winner.source_section, extraction_method=winner.extraction_method), trace
        return ExtractedField(value=None, confidence=0.0, extraction_method="not_found"), trace

    def _extract_phone_field(self, raw_text: str, parser_meta: dict) -> tuple[ExtractedField, list[dict[str, Any]]]:
        candidates: list[FieldCandidate] = []
        exact = PHONE_RE.search(raw_text)
        if exact:
            normalized = self._normalize_phone(exact.group(0))
            if 9 <= len(normalized) <= 11:
                candidates.append(FieldCandidate(value=normalized, confidence=0.95, evidence_text=exact.group(0), source_section="header", extraction_method="regex_phone", priority=0))

        for text in self._layout_header_lines(parser_meta):
            match = PHONE_RE.search(text)
            if match:
                normalized = self._normalize_phone(match.group(0))
                if 9 <= len(normalized) <= 11:
                    candidates.append(FieldCandidate(value=normalized, confidence=0.93, evidence_text=text, source_section="header", extraction_method="layout_contact_phone", priority=1))

        winner, trace = resolve_field_candidates("primary_phone", candidates)
        if winner:
            return ExtractedField(value=winner.value, confidence=winner.confidence, evidence_text=winner.evidence_text, source_section=winner.source_section, extraction_method=winner.extraction_method), trace
        return ExtractedField(value=None, confidence=0.0, extraction_method="not_found"), trace

    def _extract_dob_field(self, raw_text: str, parser_meta: dict) -> tuple[ExtractedField, list[dict[str, Any]]]:
        candidates: list[FieldCandidate] = []
        for text in self._layout_header_lines(parser_meta):
            match = DOB_RE.search(text)
            if match:
                candidates.append(FieldCandidate(value=match.group(0), confidence=0.90, evidence_text=text, source_section="header", extraction_method="layout_contact_dob", priority=0))
        if not candidates:
            match = DOB_RE.search(raw_text)
            if match:
                candidates.append(FieldCandidate(value=match.group(0), confidence=0.74, evidence_text=match.group(0), source_section="header", extraction_method="regex_dob", priority=2))

        winner, trace = resolve_field_candidates("date_of_birth", candidates)
        if winner:
            return ExtractedField(value=winner.value, confidence=winner.confidence, evidence_text=winner.evidence_text, source_section=winner.source_section, extraction_method=winner.extraction_method), trace
        return ExtractedField(value=None, confidence=0.0, extraction_method="not_found"), trace

    def _collect_address_candidates(self, header: str, raw_text: str, parser_meta: dict) -> tuple[ExtractedField, list[dict[str, Any]]]:
        scan_text = header
        candidates: list[FieldCandidate] = []
        layout_header_lines = self._layout_header_lines(parser_meta)
        for idx, text_line in enumerate(layout_header_lines):
            text_clean = self._clean_line(text_line)
            next_line = self._clean_address(layout_header_lines[idx + 1]) if idx + 1 < len(layout_header_lines) else ""
            label_match = CONTACT_LABEL_RE.match(text_clean)
            if label_match and label_match.group(1).lower().startswith(("địa chỉ", "address")):
                addr = self._clean_address(label_match.group(2))
                if next_line and (ADDRESS_HINT_RE.search(next_line) or LOCATION_RE.search(next_line) or any(alias in next_line.lower() for aliases in LOCATION_ALIASES.values() for alias in aliases)) and next_line.lower() not in addr.lower():
                    addr = f"{addr}, {next_line}".strip(", ")
                if addr:
                    candidates.append(FieldCandidate(value=addr, confidence=0.92, evidence_text=text_clean, source_section="header", extraction_method="layout_label_address", priority=0))
            elif ADDRESS_HINT_RE.search(text_clean) and not EMAIL_RE.search(text_clean) and not PHONE_RE.search(text_clean) and not DOB_RE.search(text_clean):
                addr = self._clean_address(text_clean)
                if next_line and (ADDRESS_HINT_RE.search(next_line) or LOCATION_RE.search(next_line) or any(alias in next_line.lower() for aliases in LOCATION_ALIASES.values() for alias in aliases)) and next_line.lower() not in addr.lower():
                    addr = f"{addr}, {next_line}".strip(", ")
                candidates.append(FieldCandidate(value=addr, confidence=0.88, evidence_text=text_clean, source_section="header", extraction_method="layout_contact_address", priority=1))

        header_lines = self._merge_broken_header_lines([self._clean_line(line) for line in header.splitlines()[:18] if line.strip()])
        for idx, line in enumerate(header_lines):
            next_line = self._clean_address(header_lines[idx + 1]) if idx + 1 < len(header_lines) else ""
            if ADDRESS_HINT_RE.search(line) and not EMAIL_RE.search(line) and not PHONE_RE.search(line) and not DOB_RE.search(line):
                addr = self._clean_address(line)
                if next_line and (ADDRESS_HINT_RE.search(next_line) or LOCATION_RE.search(next_line) or any(alias in next_line.lower() for aliases in LOCATION_ALIASES.values() for alias in aliases)) and next_line.lower() not in addr.lower():
                    addr = f"{addr}, {next_line}".strip(", ")
                candidates.append(FieldCandidate(value=addr, confidence=0.84, evidence_text=line, source_section="header", extraction_method="header_address_line", priority=2))

        for canonical, aliases in LOCATION_ALIASES.items():
            if any(alias in scan_text.lower() for alias in aliases):
                candidates.append(FieldCandidate(value=canonical, confidence=0.60, evidence_text=canonical, source_section="header", extraction_method="location_alias", priority=4))

        match = LOCATION_RE.search(scan_text)
        if match:
            candidates.append(FieldCandidate(value=match.group(1), confidence=0.55, evidence_text=match.group(0), source_section="header", extraction_method="location_regex", priority=5))

        winner, trace = resolve_field_candidates("address", candidates)
        if winner:
            return ExtractedField(value=winner.value, confidence=winner.confidence, evidence_text=winner.evidence_text, source_section=winner.source_section, extraction_method=winner.extraction_method), trace
        return ExtractedField(value=None, confidence=0.0, extraction_method="not_found"), trace

    def _sanitize_summary_lines(self, text: str) -> str:
        kept: list[str] = []
        for raw_line in text.splitlines():
            line = self._clean_line(raw_line)
            if not line:
                continue
            folded = _ascii_fold(line).lower()
            if self._is_boilerplate_line(line):
                continue
            if SUMMARY_BAD_LINE_RE.search(line):
                continue
            if EMAIL_RE.search(line) or PHONE_RE.search(line) or URL_RE.search(line):
                continue
            if self._canonical_section_name(line):
                continue
            if CONTACT_LABEL_RE.match(line):
                continue
            if ADDRESS_HINT_RE.search(line):
                continue
            if folded.startswith(("contact", "thông tin", "thong tin")):
                continue
            kept.append(line)
        merged = " ".join(kept)
        merged = re.sub(r"\s+([,.;:])", r"\1", merged)
        merged = re.sub(r"\s{2,}", " ", merged).strip()
        return merged

    def _summary_looks_polluted(self, value: str) -> bool:
        lowered = _ascii_fold(value).lower()
        if len(value) > 420:
            return True
        if DATE_RANGE_RE.search(value):
            return True
        pollution_terms = ["kinh nghiem lam viec", "work experience", "cac ky nang", "ky nang", "education", "hoc van", "project", "du an", "company", "cong ty", "contact"]
        return sum(1 for term in pollution_terms if term in lowered) >= 2

    def _collect_summary_candidates(self, sections: dict[str, str], header: str, full_name: str | None) -> tuple[ExtractedField, list[dict[str, Any]]]:
        candidates: list[FieldCandidate] = []
        summary_text = sections.get("summary")
        if summary_text:
            clean_summary = self._sanitize_summary_lines(summary_text)
            if clean_summary and not self._summary_looks_polluted(clean_summary):
                candidates.append(FieldCandidate(value=clean_summary, confidence=0.90, evidence_text=clean_summary[:240], source_section="summary", extraction_method="section_summary_layout_aware", priority=0))

        if not candidates:
            header_lines = [self._clean_line(line) for line in header.splitlines()[:12] if line.strip()]
            summary_candidates: list[str] = []
            for line in header_lines:
                if full_name and line == full_name:
                    continue
                if self._is_boilerplate_line(line) or CONTACT_LABEL_RE.match(line) or ADDRESS_HINT_RE.search(line):
                    continue
                if EMAIL_RE.search(line) or PHONE_RE.search(line) or URL_RE.search(line) or is_section_heading(line):
                    continue
                if SUMMARY_BAD_LINE_RE.search(line):
                    continue
                if 10 <= len(line.split()) <= 35:
                    summary_candidates.append(line)
            if summary_candidates:
                merged = " ".join(summary_candidates[:2])
                candidates.append(FieldCandidate(value=merged, confidence=0.35, evidence_text=merged[:240], source_section="header", extraction_method="header_summary_fallback", priority=8))

        winner, trace = resolve_field_candidates("summary", candidates)
        if winner:
            return ExtractedField(value=winner.value, confidence=winner.confidence, evidence_text=winner.evidence_text, source_section=winner.source_section, extraction_method=winner.extraction_method), trace
        return ExtractedField(value=None, confidence=0.0, extraction_method="not_found"), trace

    def _build_skill_candidates(self, text: str, source_section: str) -> list[SkillCandidate]:
        if not text.strip():
            return []
        base = {"skills": 0.97, "projects": 0.90, "experience": 0.88, "summary": 0.83, "header": 0.76}.get(source_section, 0.75)
        candidates: list[SkillCandidate] = []
        for alias, normalized in sorted(SKILL_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
            pattern = self._skill_patterns[alias]
            for match in pattern.finditer(text):
                evidence_start = max(match.start() - 40, 0)
                evidence_end = min(match.end() + 80, len(text))
                length_bonus = min(len(alias) / 24.0, 0.08)
                confidence = min(base + length_bonus, 0.99)
                candidates.append(SkillCandidate(alias=alias, normalized_skill=normalized, source_section=source_section, start=match.start(), end=match.end(), confidence=round(confidence, 3), evidence_text=text[evidence_start:evidence_end], priority=0 if source_section == "skills" else 1, scope=source_section))
        return candidates

    def _build_skill_items(self, sections: dict[str, str]) -> tuple[list[SkillItem], list[dict[str, Any]]]:
        candidates: list[SkillCandidate] = []
        for section_name in ("skills", "projects", "experience", "summary", "header"):
            if section_name in sections:
                candidates.extend(self._build_skill_candidates(sections[section_name], section_name))
        selected, trace = resolve_skill_candidates(candidates)
        items = [SkillItem(raw_skill=c.alias, normalized_skill=c.normalized_skill, skill_family=SKILL_FAMILIES.get(c.normalized_skill), source_section=c.source_section, evidence_text=c.evidence_text) for c in selected]
        return items, trace

    def _section_lines(self, text: str) -> list[str]:
        lines: list[str] = []
        for raw in text.splitlines():
            line = self._clean_line(raw)
            if not line or self._is_boilerplate_line(line):
                continue
            if self._canonical_section_name(line):
                continue
            if FOOTER_NOISE_RE.search(line):
                continue
            lines.append(line)
        return lines

    def _extract_date_range(self, line: str) -> tuple[str | None, str | None, str]:
        line = self._clean_line(line)
        line = re.sub(r"\)\s*$", "", line).strip()
        role_end = ROLE_DATE_AT_END_RE.match(line)
        if role_end:
            return self._normalize_date_token(role_end.group("start")), self._normalize_date_token(role_end.group("end")), self._clean_line(role_end.group(1))
        match = DATE_RANGE_RE.search(line)
        if not match:
            compact_match = DATE_RANGE_RE.search(line.replace(" ", ""))
            if not compact_match:
                return None, None, line
            line = line.replace(" ", "")
            match = compact_match
        start = self._normalize_date_token(match.group("start"))
        end = self._normalize_date_token(match.group("end"))
        rest = self._clean_line((line[: match.start()] + " " + line[match.end() :]).strip())
        return start, end, rest

    def _looks_like_bullet_or_detail(self, line: str) -> bool:
        lowered = line.lower()
        if line.startswith("-") or lowered.startswith(("•", "impact:", "vai trò", "mô tả", "quy mô", "công nghệ sử dụng", "người hỗ trợ", "khách hàng", "số lượng thành viên", "vị trí công việc")):
            return True
        if DATE_RANGE_RE.search(line):
            return False
        if self._looks_like_company_text(line) or self._looks_like_role_text(line):
            return False
        return len(line.split()) >= 16

    def _parse_header_triplet(self, lines: list[str]) -> tuple[str | None, str | None, str | None]:
        lines = [self._clean_line(line) for line in lines if self._clean_line(line)]
        lines = self._merge_broken_header_lines(lines)
        lines = [line for line in lines if not self._looks_like_contact_or_noise(line)]
        if not lines:
            return None, None, None

        title = None
        company = None
        location = None

        if len(lines) >= 2 and "," in lines[0] and self._looks_like_role_text(lines[1]) and not self._looks_like_company_text(lines[1]):
            left, right = [part.strip() for part in lines[0].rsplit(",", 1)]
            if self._looks_like_company_text(left):
                company = left
                title = self._clean_line(f"{right} {lines[1]}")
                lines = [company, title, *lines[2:]]

        for line in lines:
            role, comp = self._split_role_company_line(line)
            if role and not title:
                title = role
            if comp and not company:
                company = comp

        for idx, line in enumerate(lines):
            if title is None and self._looks_like_role_text(line):
                title = line
                continue
            if company is None and self._looks_like_company_text(line):
                company = self._sanitize_company_value(line)
                if idx + 1 < len(lines) and self._is_company_continuation(line, lines[idx + 1]):
                    company = self._sanitize_company_value(f"{company} {lines[idx + 1]}")
                continue
            if location is None and (ADDRESS_HINT_RE.search(line) or LOCATION_RE.search(line)):
                location = line

        if title is None and lines:
            fallback = lines[0]
            if self._looks_like_role_text(fallback):
                title = fallback
        if company is None and lines:
            for fallback in lines:
                if self._looks_like_company_text(fallback):
                    company = self._sanitize_company_value(fallback)
                    break
        if location is None:
            for item in lines:
                if ADDRESS_HINT_RE.search(item) or LOCATION_RE.search(item):
                    location = item
                    break

        if company and title and company.lower() == title.lower():
            company = None
        return self._clean_entity_fragment(title), self._sanitize_company_value(company), self._clean_entity_fragment(location)

    def _looks_like_project_experience(self, title: str | None, company: str | None, description: str | None, header_lines: list[str]) -> bool:
        title_text = self._clean_line(title)
        company_text = self._clean_line(company)
        description_text = self._clean_line(description)
        joined = " | ".join([item for item in [title_text, company_text, description_text, *header_lines] if item])
        lowered = joined.lower()

        if company_text and company_text.lower() in SKILL_ALIASES:
            return True
        if not company_text and PROJECT_EXPERIENCE_HINT_RE.search(lowered):
            return True
        if title_text and len(title_text.split()) > 9 and PROJECT_HINT_RE.search(lowered):
            return True
        if not title_text and not company_text and description_text:
            return True
        return False

    def _experience_stop_line(self, line: str) -> bool:
        folded = _ascii_fold(self._clean_line(line)).lower()
        if not folded:
            return True
        if FOOTER_NOISE_RE.search(line):
            return True
        if EXPERIENCE_STOP_RE.match(line):
            return True
        if re.match(r"^(gpa|cpa|toeic|ielts|sat|gre)\b", folded):
            return True
        if re.match(r"^(frameworks|databases|devops|data analysis libraries|technical skills|contact|about me)\b", folded):
            return True
        if re.match(r"^(programme|program|thesis)\b", folded):
            return True
        return False

    def _extract_experiences(self, text: str) -> list[ExperienceItem]:
        lines = self._section_lines(text)
        if not lines:
            return []

        date_indices = [idx for idx, line in enumerate(lines) if DATE_RANGE_RE.search(line) or ROLE_DATE_AT_END_RE.match(line)]
        if not date_indices:
            return []

        results: list[ExperienceItem] = []
        for pointer, date_idx in enumerate(date_indices):
            block_end = date_indices[pointer + 1] if pointer + 1 < len(date_indices) else len(lines)
            start_date, end_date, rest = self._extract_date_range(lines[date_idx])

            before_window = [
                line
                for line in lines[max(0, date_idx - 5):date_idx]
                if line and not self._looks_like_bullet_or_detail(line) and not DATE_RANGE_RE.search(line)
            ]
            body_lines = lines[date_idx + 1:block_end]
            leading_after: list[str] = []
            while body_lines and len(leading_after) < 3:
                candidate = body_lines[0]
                if DATE_RANGE_RE.search(candidate) or self._canonical_section_name(candidate):
                    break
                if self._looks_like_bullet_or_detail(candidate):
                    break
                candidate_clean = self._clean_line(candidate)
                candidate_words = len(candidate_clean.split())
                if not (
                    self._looks_like_company_text(candidate_clean)
                    or self._looks_like_role_text(candidate_clean)
                    or (leading_after and self._is_company_continuation(leading_after[-1], candidate_clean))
                    or candidate_words <= 4
                ):
                    break
                leading_after.append(body_lines.pop(0))

            header_lines = before_window[-3:]
            if rest:
                header_lines.append(rest)
            header_lines.extend(leading_after)
            title, company, location = self._parse_header_triplet(header_lines)

            description_lines = []
            for line in body_lines:
                if CONTACT_NOISE_RE.match(line.lower()):
                    continue
                if self._experience_stop_line(line):
                    break
                if title and company and (self._looks_like_role_text(line) or self._looks_like_company_text(line)) and len(description_lines) >= 1 and len(line.split()) <= 8:
                    break
                description_lines.append(line)
            description = " ".join(description_lines).strip() if description_lines else None
            if description and len(description) > 2200:
                description = description[:2200]

            company = self._sanitize_company_value(company)

            if title or company or description:
                results.append(ExperienceItem(title=title, company=company, location=location, start_date=start_date, end_date=end_date, description=description))

        deduped: list[ExperienceItem] = []
        seen: set[tuple[str | None, str | None, str | None, str | None]] = set()
        for item in results:
            key = (item.title, item.company, item.start_date, item.end_date)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped[:20]

    def _parse_education_entry(self, header_lines: list[str], start_date: str | None, end_date: str | None, body_lines: list[str]) -> EducationItem | None:
        lines = [self._clean_line(line) for line in [*header_lines, *body_lines] if self._clean_line(line)]
        if not lines:
            return None

        school = None
        degree = None
        major = None
        description_bits: list[str] = []

        def split_school_degree(line: str) -> tuple[str | None, str | None]:
            if "," in line and DEGREE_TOKEN_RE.search(line):
                left, right = [part.strip() for part in line.split(",", 1)]
                if DEGREE_TOKEN_RE.search(left):
                    return right, left
            return line, None

        for line in lines:
            lower = line.lower()
            if school is None and SCHOOL_HINT_RE.search(line):
                school_candidate, degree_candidate = split_school_degree(line)
                school = school_candidate
                if degree is None and degree_candidate:
                    degree = degree_candidate
                if major is None and "," in school_candidate:
                    left, right = [part.strip() for part in school_candidate.rsplit(",", 1)]
                    if MAJOR_TOKEN_RE.search(right):
                        school = left
                        major = right
                continue
            if degree is None and DEGREE_TOKEN_RE.search(lower) and not COURSE_NOISE_RE.search(lower):
                degree = line
                continue
            if major is None and PROGRAM_HINT_RE.search(line):
                major = re.sub(r"^(programme|program|major|chuyên ngành|ngành|field of study)\s*[:：-]?\s*", "", line, flags=re.I)
                continue
            if major is None and MAJOR_TOKEN_RE.search(lower):
                major = line
                continue
            description_bits.append(line)

        if school is None:
            for line in header_lines:
                if SCHOOL_HINT_RE.search(line):
                    school = line
                    break
        if school is None and COURSE_HINT_RE.search(" | ".join(lines)):
            return None
        if school is None:
            school = header_lines[0] if header_lines else lines[0]

        if degree and COURSE_NOISE_RE.search(degree):
            description_bits.append(degree)
            degree = None
        if major and COURSE_NOISE_RE.search(major):
            description_bits.append(major)
            major = None

        description = " | ".join(bit for bit in description_bits if bit not in {school, degree, major})[:1800] or None
        school = self._clean_entity_fragment(school)
        degree = self._clean_entity_fragment(degree)
        major = self._clean_entity_fragment(major)
        if not school:
            return None
        return EducationItem(school=school, degree=degree, major=major, start_date=start_date, end_date=end_date, description=description)

    def _extract_educations(self, text: str) -> list[EducationItem]:
        lines = [line for line in self._section_lines(text) if not FOOTER_NOISE_RE.search(line)]
        if not lines:
            return []
        date_indices = [idx for idx, line in enumerate(lines) if DATE_RANGE_RE.search(line) or ROLE_DATE_AT_END_RE.match(line)]
        if not date_indices:
            compact = " ".join(lines)
            if SCHOOL_HINT_RE.search(compact):
                return [EducationItem(school=self._clean_entity_fragment(lines[0]), description=" | ".join(lines[1:]) or None)]
            return []

        items: list[EducationItem] = []
        for pointer, date_idx in enumerate(date_indices):
            block_end = date_indices[pointer + 1] if pointer + 1 < len(date_indices) else len(lines)
            start_date, end_date, rest = self._extract_date_range(lines[date_idx])
            before_window = [
                line
                for line in lines[max(0, date_idx - 4):date_idx]
                if line and not self._looks_like_bullet_or_detail(line) and not DATE_RANGE_RE.search(line)
            ]
            school_positions = [idx for idx, line in enumerate(before_window) if SCHOOL_HINT_RE.search(line) or DEGREE_TOKEN_RE.search(line)]
            if school_positions:
                before_window = before_window[school_positions[-1]:]
            body_lines = lines[date_idx + 1:block_end]
            if pointer + 1 < len(date_indices):
                while body_lines and (SCHOOL_HINT_RE.search(body_lines[-1]) or DEGREE_TOKEN_RE.search(body_lines[-1])):
                    body_lines.pop()
            header_lines = self._merge_broken_header_lines(before_window[-3:])
            if rest:
                header_lines.append(rest)
            entry = self._parse_education_entry(header_lines, start_date, end_date, body_lines[:5])
            if entry:
                items.append(entry)
        return items[:12]

    def _looks_like_contact_or_noise(self, line: str) -> bool:
        if not line:
            return True
        if FOOTER_NOISE_RE.search(line):
            return True
        if EMAIL_RE.search(line) or PHONE_RE.search(line) or URL_RE.search(line):
            return True
        if self._canonical_section_name(line):
            return True
        return False

    def _project_stop_line(self, line: str, *, seen_project: bool = False) -> bool:
        folded = _ascii_fold(self._clean_line(line)).lower()
        if not folded:
            return True
        if FOOTER_NOISE_RE.search(line):
            return True
        if PROJECT_STOP_RE.match(line):
            return True
        compact_words = len(self._clean_line(line).split())
        if seen_project and compact_words <= 8 and not ROLE_LINE_RE.match(line) and not PROJECT_META_LABEL_RE.match(line) and (self._looks_like_company_text(line) or self._looks_like_role_text(line)) and not PROJECT_HINT_RE.search(line):
            return True
        if seen_project and DATE_RANGE_RE.search(line) and not PROJECT_HINT_RE.search(line):
            return True
        return False

    def _extract_projects(self, text: str) -> list[ProjectItem]:
        if not text.strip():
            return []
        raw_lines = [self._clean_line(line) for line in text.splitlines() if self._clean_line(line)]
        lines = [line for line in raw_lines if not self._looks_like_contact_or_noise(line) and not self._is_boilerplate_line(line)]
        if not lines:
            return []

        projects: list[ProjectItem] = []
        current: dict[str, Any] | None = None

        def flush_current() -> None:
            nonlocal current
            if not current or not current.get("name"):
                current = None
                return
            description = " ".join(current["description"]).strip()
            tech_text = " ".join(filter(None, [current.get("name"), current.get("role"), description]))
            selected_technologies, _ = resolve_skill_candidates(self._build_skill_candidates(tech_text, "projects"))
            projects.append(ProjectItem(name=current.get("name"), role=current.get("role"), start_date=current.get("start_date"), end_date=current.get("end_date"), description=description or None, technologies=[item.normalized_skill for item in selected_technologies]))
            current = None

        def looks_like_urlish(line: str) -> bool:
            return bool(URL_RE.search(line) or URLISH_RE.search(line))

        def should_start_project(idx: int, line: str) -> bool:
            if PROJECT_TITLE_RE.match(line):
                return True
            if PROJECT_META_LABEL_RE.match(line) or looks_like_urlish(line):
                return False
            word_count = len(line.split())
            if word_count > 14:
                return False
            next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
            if next_line and (DATE_RANGE_RE.search(next_line) or looks_like_urlish(next_line)):
                return True
            if PROJECT_HINT_RE.search(line):
                lowered = line.lower()
                if line.endswith(".") or any(token in lowered for token in ["objective", "manage", "conduct", "lives in the nordic"]):
                    return False
                return word_count <= 10
            return idx == 0 and 2 <= word_count <= 10

        seen_named_project = False
        for idx, line in enumerate(lines):
            if self._project_stop_line(line, seen_project=seen_named_project):
                if current is not None and current.get("name"):
                    flush_current()
                break
            title_match = PROJECT_TITLE_RE.match(line)
            role_match = ROLE_LINE_RE.match(line)
            meta_match = PROJECT_META_LABEL_RE.match(line)
            start_date, end_date, rest = self._extract_date_range(line)

            if current is None and start_date and end_date and rest:
                current = {"name": rest, "role": None, "start_date": start_date, "end_date": end_date, "description": []}
                seen_named_project = True
                continue

            if title_match:
                flush_current()
                current = {"name": title_match.group(2).strip(), "role": None, "start_date": None, "end_date": None, "description": []}
                seen_named_project = True
                continue

            if current is None and should_start_project(idx, line):
                current = {"name": line, "role": None, "start_date": None, "end_date": None, "description": []}
                seen_named_project = True
                continue

            if current is not None and should_start_project(idx, line) and current.get("description"):
                flush_current()
                current = {"name": line, "role": None, "start_date": None, "end_date": None, "description": []}
                seen_named_project = True
                continue

            if current is None:
                continue
            if role_match and not current.get("role"):
                current["role"] = role_match.group(1).strip()
                continue
            if meta_match:
                current["description"].append(self._clean_line(line))
                continue
            if looks_like_urlish(line):
                current["description"].append(line)
                continue
            if start_date and end_date:
                current["start_date"] = start_date
                current["end_date"] = end_date
                if rest:
                    current["description"].append(rest)
                continue
            current["description"].append(line)

        flush_current()
        return [proj for proj in projects if proj.name][:12]

    def _links_from_text(self, raw_text: str) -> list[LinkItem]:
        seen: set[str] = set()
        items: list[LinkItem] = []
        for match in URL_RE.finditer(raw_text):
            url = match.group(0).strip().rstrip(",.")
            if url.lower() in seen:
                continue
            seen.add(url.lower())
            items.append(LinkItem(label="profile", url=url))
        return items

    def extract(self, raw_text: str, filename: str | None = None, parser_meta: dict | None = None) -> tuple[CandidateExtraction, ExtractionAudit]:
        parser_meta = parser_meta or {}
        filename = filename or "uploaded_cv"

        text_sections = self._split_sections_from_text(raw_text)
        layout_sections = self._split_sections_from_layout(parser_meta)
        sections = self._merge_sections(layout_sections, text_sections)

        classification = self.classifier.classify(raw_text, sections)
        header = sections.get("header", raw_text[:1400])

        full_name, name_trace = self._collect_name_candidates(header, filename, parser_meta)
        email_field, email_trace = self._extract_email_field(raw_text, parser_meta)
        phone_field, phone_trace = self._extract_phone_field(raw_text, parser_meta)
        dob_field, dob_trace = self._extract_dob_field(raw_text, parser_meta)
        summary, summary_trace = self._collect_summary_candidates(sections, header, full_name.value)
        address, address_trace = self._collect_address_candidates(header, raw_text, parser_meta)
        title_candidates, company_candidates = self._collect_header_role_company_candidates(header, full_name.value, parser_meta)

        skills, skill_trace = self._build_skill_items(sections)
        experiences = self._extract_experiences(sections.get("experience", ""))
        educations = self._extract_educations(sections.get("education", ""))
        projects = self._extract_projects(sections.get("projects", ""))
        links = self._links_from_text(raw_text)

        if experiences:
            first_exp = experiences[0]
            if first_exp.title:
                title_candidates.append(FieldCandidate(value=first_exp.title, confidence=0.72, evidence_text=first_exp.title, source_section="experience", extraction_method="experience_first_block", priority=5))
            if first_exp.company and self._looks_like_company_text(first_exp.company):
                company_candidates.append(FieldCandidate(value=first_exp.company, confidence=0.68, evidence_text=first_exp.company, source_section="experience", extraction_method="experience_first_block", priority=5))

        title_winner, title_trace = resolve_field_candidates("current_title", title_candidates)
        company_winner, company_trace = resolve_field_candidates("current_company", company_candidates)

        current_title = ExtractedField(value=None, confidence=0.0, extraction_method="not_found")
        if title_winner:
            current_title = ExtractedField(value=title_winner.value, confidence=title_winner.confidence, evidence_text=title_winner.evidence_text, source_section=title_winner.source_section, extraction_method=title_winner.extraction_method)

        current_company = ExtractedField(value=None, confidence=0.0, extraction_method="not_found")
        if company_winner:
            current_company = ExtractedField(value=company_winner.value, confidence=company_winner.confidence, evidence_text=company_winner.evidence_text, source_section=company_winner.source_section, extraction_method=company_winner.extraction_method)

        extraction = CandidateExtraction(
            full_name=full_name,
            primary_email=email_field,
            primary_phone=phone_field,
            date_of_birth=dob_field,
            address=address,
            summary=summary,
            current_title=current_title,
            current_company=current_company,
            skills=skills,
            experiences=experiences,
            educations=educations,
            projects=projects,
            social_links=links,
            sections_detected=sorted(sections.keys()),
        )

        field_confidence = {
            "full_name": extraction.full_name.confidence,
            "primary_email": extraction.primary_email.confidence,
            "primary_phone": extraction.primary_phone.confidence,
            "date_of_birth": extraction.date_of_birth.confidence,
            "address": extraction.address.confidence,
            "summary": extraction.summary.confidence,
            "current_title": extraction.current_title.confidence,
            "current_company": extraction.current_company.confidence,
            "skills": 0.88 if extraction.skills else 0.0,
            "experiences": min(0.92, 0.45 + 0.12 * len(extraction.experiences)) if extraction.experiences else 0.0,
            "educations": min(0.85, 0.35 + 0.18 * len(extraction.educations)) if extraction.educations else 0.0,
            "projects": min(0.90, 0.45 + 0.15 * len(extraction.projects)) if extraction.projects else 0.0,
        }

        review_reasons: list[str] = []
        parse_flags = list(classification.parse_flags)
        suppressed_skill_conflicts = sum(1 for item in skill_trace if item["status"] == "suppressed")
        field_conflicts = {
            "full_name": max(len(name_trace) - 1, 0),
            "primary_email": max(len(email_trace) - 1, 0),
            "primary_phone": max(len(phone_trace) - 1, 0),
            "date_of_birth": max(len(dob_trace) - 1, 0),
            "summary": max(len(summary_trace) - 1, 0),
            "address": max(len(address_trace) - 1, 0),
            "current_title": max(len(title_trace) - 1, 0),
            "current_company": max(len(company_trace) - 1, 0),
            "skills": suppressed_skill_conflicts,
        }

        if extraction.full_name.extraction_method == "filename_fallback":
            parse_flags.append("filename_used_as_weak_name_fallback")
            review_reasons.append("untrusted_full_name_from_filename")
        if not extraction.full_name.value:
            review_reasons.append("missing_full_name")
        if not extraction.primary_email.value and not extraction.primary_phone.value:
            review_reasons.append("missing_contact_info")
        if not extraction.skills:
            review_reasons.append("missing_skills")
        if classification.document_type == "non_cv":
            review_reasons.append("document_not_classified_as_cv")
        if classification.quality_score < 0.55:
            review_reasons.append("low_cv_quality_score")
        if is_generic_filename(filename):
            parse_flags.append("generic_filename_detected")
        if sections.get("projects") and not extraction.projects:
            review_reasons.append("project_section_detected_but_no_project_parsed")
        if sections.get("experience") and not extraction.experiences:
            review_reasons.append("experience_section_detected_but_no_experience_parsed")
        if sections.get("education") and not extraction.educations:
            review_reasons.append("education_section_detected_but_no_education_parsed")
        if suppressed_skill_conflicts > 0:
            parse_flags.append("skill_overlap_resolved")
        if field_conflicts["current_title"] > 0 or field_conflicts["current_company"] > 0:
            parse_flags.append("field_conflict_resolved")
        if extraction.primary_email.extraction_method == "email_truncated_domain_fixup":
            parse_flags.append("email_truncated_domain_recovered")
        if extraction.current_company.value and CONTACT_NOISE_RE.match(extraction.current_company.value.lower()):
            review_reasons.append("current_company_contact_contamination")

        audit = ExtractionAudit(
            schema_valid=True,
            extractor_backend="hybrid_v9_layout_row_parser",
            review_reasons=sorted(set(review_reasons)),
            parser_meta=parser_meta,
            field_confidence=field_confidence,
            document_type=classification.document_type,
            parser_mode=classification.parser_mode,
            cv_quality_score=classification.quality_score,
            parse_flags=sorted(set(parse_flags)),
            source_trace={
                "filename": filename,
                "name_source": extraction.full_name.extraction_method,
                "email_source": extraction.primary_email.extraction_method,
                "title_source": extraction.current_title.extraction_method,
                "summary_source": extraction.summary.extraction_method,
                "layout_available": bool(parser_meta.get("first_page_layout_lines")),
                "layout_sections_detected": sorted(layout_sections.keys()),
            },
            resolver_stats={
                "field_conflicts": field_conflicts,
                "suppressed_skill_conflicts": suppressed_skill_conflicts,
                "selected_skill_count": len(extraction.skills),
            },
            resolver_trace={
                "full_name": name_trace,
                "primary_email": email_trace,
                "primary_phone": phone_trace,
                "date_of_birth": dob_trace,
                "summary": summary_trace,
                "address": address_trace,
                "current_title": title_trace,
                "current_company": company_trace,
                "skills": skill_trace,
            },
        )
        return extraction, audit