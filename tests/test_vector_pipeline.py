from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_hr_agent.db")
os.environ.setdefault("EMBEDDING_BACKEND", "hashing")

from app.schemas.candidate import CandidateExtraction, ExtractedField, SkillItem
from app.services.extractor import HybridExtractor
from app.services.jd_parser import JDParser
from app.services.normalizer import normalize_candidate
from app.services.vector_store import cosine_similarity


def test_normalize_candidate_builds_vector_fields():
    extraction = CandidateExtraction(
        full_name=ExtractedField(value="Nguyen Van A", confidence=0.9, extraction_method="header_name_line"),
        primary_email=ExtractedField(value="a@example.com", confidence=0.99),
        primary_phone=ExtractedField(value="0900000000", confidence=0.95),
        date_of_birth=ExtractedField(),
        address=ExtractedField(value="Ha Noi", confidence=0.7),
        summary=ExtractedField(value="AI engineer with FastAPI and RAG experience", confidence=0.8),
        current_title=ExtractedField(value="AI Engineer", confidence=0.8),
        current_company=ExtractedField(value="OpenAI VN", confidence=0.7),
        skills=[
            SkillItem(raw_skill="Python", normalized_skill="python"),
            SkillItem(raw_skill="FastAPI", normalized_skill="fastapi"),
            SkillItem(raw_skill="RAG", normalized_skill="rag"),
        ],
        experiences=[],
        educations=[],
        projects=[],
        social_links=[],
        sections_detected=["header", "summary", "skills"],
    )
    normalized = normalize_candidate(extraction)
    assert normalized["vector_document"]
    assert normalized["vector_metadata"]["skills"] == ["fastapi", "python", "rag"]
    assert normalized["confidence_score"] >= 0.6


def test_jd_parser_extracts_requirements_without_role_confusion():
    parser = JDParser()
    parsed = parser.parse(
        "Cần AI Engineer có Python, FastAPI, RAG, vector database, tối thiểu 3 năm kinh nghiệm, ưu tiên Computer Science"
    )
    assert parsed.minimum_years_experience == 3.0
    assert parsed.role_keywords == ["ai engineer"]
    assert set(parsed.must_have_skills) >= {"python", "fastapi", "rag", "vector database"}
    assert "computer science" in parsed.degree_keywords


def test_extractor_does_not_trust_generic_filename_as_name():
    raw_text = """
    DATA SCIENTIST
    dsai@example.com
    0901234567

    SKILLS
    Python, FastAPI, SQL

    EXPERIENCE
    AI Engineer | ABC Tech
    01/2022 - Present
    Build RAG services for internal platform.
    """
    extractor = HybridExtractor()
    extraction, audit = extractor.extract(raw_text, filename="DS AI.pdf", parser_meta={"parser": "pypdf"})
    assert extraction.full_name.value is None
    assert "filename_used_as_weak_name_fallback" not in audit.parse_flags
    assert "missing_full_name" in audit.review_reasons


def test_extractor_resolves_header_role_company_split():
    raw_text = """
    NGUYEN VAN A
    AI Engineer | ABC Corp
    nguyen@example.com
    0901234567

    SUMMARY
    AI engineer with experience in LLM, RAG and FastAPI.
    """
    extractor = HybridExtractor()
    extraction, audit = extractor.extract(raw_text, filename="cv_ai_engineer.pdf", parser_meta={"parser": "plain-text"})
    assert extraction.current_title.value == "AI Engineer"
    assert extraction.current_company.value == "ABC Corp"
    assert audit.resolver_stats["field_conflicts"]["current_title"] >= 1


def test_skill_extractor_prefers_longest_overlapping_alias():
    raw_text = """
    JOHN DOE
    john@example.com
    0901234567

    SKILLS
    Spring Boot, Java, Docker
    """
    extractor = HybridExtractor()
    extraction, audit = extractor.extract(raw_text, filename="john_doe.pdf", parser_meta={"parser": "plain-text"})
    skills = {item.normalized_skill for item in extraction.skills}
    assert "spring boot" in skills
    assert "spring" not in skills
    assert "skill_overlap_resolved" in audit.parse_flags


def test_layout_sections_handle_topcv_style_icons_and_contacts():
    raw_text = """
    NỀN TẢNG TUYỂN DỤNG NHÂN SỰ HÀNG ĐẦU VIỆT NAM
    Ứng viên Trần Quốc Thái | Nguồn tuyendung.topcv.vn

    TRẦN QUỐC THÁI
    THỰC TẬP SINH AI

     Nam
     tranthai.tqt@gmail.c…
     0342540765
     23/04/2001
     62 ngõ 29 Khương Hạ,Thanh Xuân

     Mục tiêu nghề nghiệp
    Mong muốn tìm được một nơi làm việc dài
    hạn, có cơ hội thăng tiến rõ ràng, môi trường
    làm việc chuyên nghiệp để có thể cống hiến,
    phát triển bản thân.

     Học vấn
    Đại học Xây Dựng Hà Nội, chuyên ngành Khoa học máy tính
    9/2019 - nay
    CPA: 2.7

     Kinh nghiệm làm việc
    Phân tích dữ liệu và dự đoán khách hàng rời bỏ Viettel, Tập dữ liệu thật của Viettel
    với gần 1 triệu data. Dự án cá nhân.
    11/2021 - 12/2021
    Người hỗ trợ: Thạc sĩ Nguyễn Đình Quý
    - Xử lý dữ liệu mất cân bằng, ngoại lai, chuẩn hóa.

     Các kỹ năng
    Sử dụng ngôn ngữ Python, Java, C++, SQL:
    Có kiến thức về xử lý dữ liệu phân tán, xử lý dữ liệu lớn (Hadoop, Spark, ...):
    """
    parser_meta = {
        "parser": "pymupdf_layout",
        "first_page_width": 594.95,
        "first_page_height": 841.92,
        "first_page_layout_lines": [
            {"text": "NỀN TẢNG TUYỂN DỤNG NHÂN SỰ HÀNG ĐẦU VIỆT NAM", "x0": 145.36, "y0": 44.89, "x1": 478.79, "font_size": 12.01, "is_bold": True},
            {"text": "Ứng viên Trần Quốc Thái | Nguồn tuyendung.topcv.vn", "x0": 168.59, "y0": 58.40, "x1": 455.57, "font_size": 12.01, "is_bold": False},
            {"text": "TRẦN QUỐC THÁI", "x0": 256.00, "y0": 142.07, "x1": 461.43, "font_size": 24.01, "is_bold": False},
            {"text": "THỰC TẬP SINH AI", "x0": 256.00, "y0": 173.68, "x1": 343.91, "font_size": 12.01, "is_bold": False},
            {"text": "\uf007 Nam", "x0": 27.97, "y0": 254.60, "x1": 63.80, "font_size": 10.5, "is_bold": False},
            {"text": "\uf0e0 tranthai.tqt@gmail.c…", "x0": 95.52, "y0": 254.60, "x1": 201.80, "font_size": 10.5, "is_bold": False},
            {"text": "\uf095 0342540765", "x0": 222.09, "y0": 254.60, "x1": 289.55, "font_size": 10.5, "is_bold": False},
            {"text": "\uf073 23/04/2001", "x0": 324.22, "y0": 254.60, "x1": 389.56, "font_size": 10.5, "is_bold": False},
            {"text": "\uf015 62 ngõ 29 Khương Hạ,Thanh Xuân", "x0": 426.99, "y0": 254.60, "x1": 582.72, "font_size": 10.5, "is_bold": False},
            {"text": "\uf19d Học vấn", "x0": 245.49, "y0": 290.19, "x1": 314.18, "font_size": 15.01, "is_bold": False},
            {"text": "\uf05a Mục tiêu nghề nghiệp", "x0": 24.01, "y0": 291.69, "x1": 170.01, "font_size": 15.01, "is_bold": False},
            {"text": "Đại học Xây Dựng Hà Nội, chuyên ngành Khoa học máy tính", "x0": 245.49, "y0": 332.64, "x1": 488.65, "font_size": 10.5, "is_bold": True},
            {"text": "9/2019 - nay", "x0": 245.49, "y0": 349.79, "x1": 294.31, "font_size": 9.0, "is_bold": True},
            {"text": "CPA: 2.7", "x0": 245.49, "y0": 368.65, "x1": 279.34, "font_size": 10.5, "is_bold": False},
            {"text": "Mong muốn tìm được một nơi làm việc dài", "x0": 24.01, "y0": 331.14, "x1": 195.55, "font_size": 10.5, "is_bold": False},
            {"text": "hạn, có cơ hội thăng tiến rõ ràng, môi trường", "x0": 24.01, "y0": 344.64, "x1": 203.55, "font_size": 10.5, "is_bold": False},
            {"text": "làm việc chuyên nghiệp để có thể cống hiến,", "x0": 24.01, "y0": 358.15, "x1": 202.84, "font_size": 10.5, "is_bold": False},
            {"text": "phát triển bản thân.", "x0": 24.01, "y0": 371.65, "x1": 103.26, "font_size": 10.5, "is_bold": False},
            {"text": "\uf0b1 Kinh nghiệm làm việc", "x0": 245.49, "y0": 399.74, "x1": 390.86, "font_size": 15.01, "is_bold": False},
            {"text": "\uf040 Các kỹ năng", "x0": 24.01, "y0": 419.25, "x1": 116.08, "font_size": 15.01, "is_bold": False},
            {"text": "Phân tích dữ liệu và dự đoán khách hàng rời bỏ Viettel, Tập dữ liệu thật của Viettel", "x0": 245.49, "y0": 442.18, "x1": 584.96, "font_size": 10.5, "is_bold": True},
            {"text": "với gần 1 triệu data. Dự án cá nhân.", "x0": 245.49, "y0": 455.69, "x1": 388.98, "font_size": 10.5, "is_bold": False},
            {"text": "11/2021 - 12/2021", "x0": 245.49, "y0": 472.84, "x1": 315.87, "font_size": 9.0, "is_bold": True},
            {"text": "Người hỗ trợ: Thạc sĩ Nguyễn Đình Quý", "x0": 245.49, "y0": 491.70, "x1": 404.43, "font_size": 10.5, "is_bold": False},
            {"text": "- Xử lý dữ liệu mất cân bằng, ngoại lai, chuẩn hóa.", "x0": 245.49, "y0": 505.21, "x1": 450.65, "font_size": 10.5, "is_bold": False},
            {"text": "Sử dụng ngôn ngữ Python, Java, C++, SQL:", "x0": 24.01, "y0": 461.69, "x1": 202.11, "font_size": 10.5, "is_bold": True},
            {"text": "Có kiến thức về xử lý dữ liệu phân tán, xử lý dữ liệu lớn (Hadoop, Spark, ...):", "x0": 24.01, "y0": 691.29, "x1": 206.62, "font_size": 10.5, "is_bold": True},
        ],
    }

    extractor = HybridExtractor()
    extraction, audit = extractor.extract(raw_text, filename="Tran-Quoc-Thai-TopCV.vn-250822.85348.pdf", parser_meta=parser_meta)

    assert extraction.full_name.value == "TRẦN QUỐC THÁI"
    assert extraction.current_title.value == "THỰC TẬP SINH AI"
    assert extraction.current_company.value is None
    assert extraction.primary_email.value == "tranthai.tqt@gmail.com"
    assert extraction.date_of_birth.value == "23/04/2001"
    assert extraction.address.value == "62 ngõ 29 Khương Hạ,Thanh Xuân"
    assert extraction.summary.value.startswith("Mong muốn tìm được")
    assert set(extraction.sections_detected) >= {"summary", "skills", "education", "experience", "header"}
    assert extraction.educations
    assert extraction.experiences or extraction.projects
    assert "email_truncated_domain_recovered" in audit.parse_flags


def test_cosine_similarity_bounds():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert round(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 5) == 0.0

def test_date_utils_count_inclusive_months():
    from app.services.date_utils import parse_date_point, months_between, safe_total_experience_months

    assert months_between(parse_date_point("01/2020"), parse_date_point("12/2020")) == 12
    assert safe_total_experience_months([("01/2020", "12/2020")]) == 12


def test_education_parser_keeps_degree_major_correct_and_ignores_course_noise():
    raw_text = """
    EDUCATION
    Master of Science, LUT University, Finland
    08/2021 - Present
    Data Science
    Amazon Web Services | Machine Learning & Neural Networks | Data Analysis with Python | Cloud Platforms

    Master of Science (Distinction), Aalto University School of Engineering, Finland
    08/2016 - 06/2020
    Energy Technology (GPA: 4.3/5)
    Thesis (Grade: 5): Simulation-based multi-objective optimization of an office building's envelope
    """
    extractor = HybridExtractor()
    extraction, _ = extractor.extract(raw_text, filename="education_sample.pdf", parser_meta={"parser": "plain-text"})
    normalized = normalize_candidate(extraction)

    assert normalized["education"][0]["school"] == "LUT University, Finland"
    assert normalized["education"][0]["degree"] == "master"
    assert normalized["education"][0]["major"] == "data science"
    assert normalized["education"][1]["degree"] == "master"
    assert normalized["education"][1]["major"] == "Energy Technology"


def test_project_parser_does_not_fragment_narrative_lines_into_multiple_projects():
    raw_text = """
    PROJECTS
    10/2015 - 05/2016 Innovation Project (NDA) with Mitsubishi Electric R&D Scotland
    The multidisciplinary project objective was to envision the future of HVAC systems and citizens lives in the Nordic in 2035 based on megatrends research and scenario planning.
    Manage overall travel plans, documents, and milestone deadlines of the project.
    Conduct research and literature review on forecasts of climate change and potential of renewable energy.
    """
    extractor = HybridExtractor()
    extraction, _ = extractor.extract(raw_text, filename="project_sample.pdf", parser_meta={"parser": "plain-text"})

    assert len(extraction.projects) == 1
    assert extraction.projects[0].name == "Innovation Project (NDA) with Mitsubishi Electric R&D Scotland"


def test_experience_parser_skips_personal_project_blocks_misfiled_as_work_experience():
    raw_text = """
    EXPERIENCE
    Phân tích dữ liệu và dự đoán khách hàng rời bỏ Viettel, Tập dữ liệu thật của Viettel với gần 1 triệu data. Dự án cá nhân.
    11/2021 - 12/2021
    Người hỗ trợ: Thạc sĩ Nguyễn Đình Quý
    - Xử lý dữ liệu mất cân bằng, ngoại lai, chuẩn hóa.
    """
    extractor = HybridExtractor()
    extraction, _ = extractor.extract(raw_text, filename="project_like_experience.pdf", parser_meta={"parser": "plain-text"})
    normalized = normalize_candidate(extraction)

    assert normalized["experience"] == []
