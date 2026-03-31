from __future__ import annotations

import io
import mimetypes
from dataclasses import dataclass

import docx
import pdfplumber


class UnsupportedFileTypeError(Exception):
    pass


@dataclass
class ParseResult:
    text: str
    mime_type: str
    parser_meta: dict


def _guess_mime_type(filename: str) -> str:
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


def _extract_pdf_text(file_bytes: bytes) -> tuple[str, dict]:
    pages = []
    meta = {
        "parser": "pdfplumber",
        "used_ocr": False,
        "page_count": 0,
        "low_text_warning": False,
    }

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        meta["page_count"] = len(pdf.pages)
        for page in pdf.pages:
            pages.append(page.extract_text() or "")

    text = "\n".join(pages).strip()
    if len(text) < 80:
        meta["low_text_warning"] = True
    return text, meta


def _extract_docx_text(file_bytes: bytes) -> tuple[str, dict]:
    document = docx.Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs).strip()
    meta = {
        "parser": "python-docx",
        "used_ocr": False,
        "paragraph_count": len(paragraphs),
        "low_text_warning": len(text) < 80,
    }
    return text, meta


def _extract_txt_text(file_bytes: bytes) -> tuple[str, dict]:
    text = file_bytes.decode("utf-8", errors="ignore").strip()
    meta = {
        "parser": "plain-text",
        "used_ocr": False,
        "low_text_warning": len(text) < 80,
    }
    return text, meta


def extract_text(file_bytes: bytes, filename: str) -> ParseResult:
    name = filename.lower()
    mime_type = _guess_mime_type(filename)

    if name.endswith(".pdf"):
        text, meta = _extract_pdf_text(file_bytes)
    elif name.endswith(".docx"):
        text, meta = _extract_docx_text(file_bytes)
    elif name.endswith(".txt"):
        text, meta = _extract_txt_text(file_bytes)
    else:
        raise UnsupportedFileTypeError(f"Unsupported file type: {filename}")

    return ParseResult(text=text, mime_type=mime_type, parser_meta=meta)