# HR-Agent

## Overview

HR-Agent là một dự án sàng lọc CV dành cho quy trình tuyển dụng nội bộ. Hệ thống tập trung vào 4 phần chính:

- ingest CV từ file `.pdf`, `.docx`, `.txt`
- trích xuất thông tin ứng viên từ nội dung CV
- chuẩn hóa dữ liệu để lưu trữ và tìm kiếm
- cung cấp giao diện web để upload, tra cứu, review và export dữ liệu ứng viên

Hiện tại repo bao gồm:

- **FastAPI backend** để xử lý upload, parsing, search, review, analytics và export
- **Streamlit dashboard** để thao tác thủ công qua giao diện web
- **SQLAlchemy models** để lưu dữ liệu ứng viên vào database
- **pipeline xử lý CV** gồm parse text, deduplicate, extract, normalize và search
- **test cơ bản** cho normalizer và luồng smoke test

---

## What the project does

Luồng xử lý hiện tại của dự án:

1. Người dùng upload một hoặc nhiều CV
2. Backend kiểm tra dung lượng file và tránh ingest lại file trùng bằng `SHA-256`
3. File được parse text theo định dạng:
   - PDF
   - DOCX
   - TXT
4. Nếu PDF có chất lượng text thấp, hệ thống có thể thử OCR fallback
5. Dữ liệu thô được đưa qua extractor để lấy ra các trường ứng viên
6. Kết quả được normalize để suy ra:
   - tên chuẩn hóa
   - email / phone chính
   - current title / current company
   - số năm kinh nghiệm
   - normalized skills
   - review status
   - confidence score
7. Dữ liệu được lưu vào database
8. Người dùng có thể:
   - search ứng viên
   - xem review queue
   - cập nhật review status
   - xem analytics
   - export CSV

---

## Main features

### 1. CV upload
- upload 1 CV hoặc nhiều CV cùng lúc
- hỗ trợ `.pdf`, `.docx`, `.txt`
- chặn file quá dung lượng cấu hình
- bỏ qua file trùng nội dung bằng hash

### 2. Text parsing
- parse text từ PDF
- parse text từ DOCX
- parse text từ TXT
- có cơ chế OCR fallback cho PDF khi native extraction yếu

### 3. Candidate extraction
Extractor hiện tại tập trung vào:
- full name
- email
- phone
- summary
- current title
- current company
- skills
- experience
- education
- projects
- social/profile links
- detected sections

### 4. Candidate normalization
Normalizer xử lý:
- chuẩn hóa email / phone
- suy ra current title
- suy ra current company
- suy ra tổng số năm kinh nghiệm
- chuẩn hóa skill list
- tính confidence score
- gán review status và review reasons

### 5. Search and recruiter workflow
- preview query plan từ câu query tuyển dụng
- search ứng viên theo query
- lọc review queue
- cập nhật review status
- xem duplicate groups
- xem analytics
- export dữ liệu ứng viên ra CSV

### 6. Dashboard
Dashboard Streamlit hiện có 4 tab:
- Upload CV
- Search Candidates
- Review Queue
- Analytics

---

## Tech stack

### Backend
- FastAPI
- Uvicorn
- SQLAlchemy
- Pydantic
- Pydantic Settings

### Frontend
- Streamlit

### Data / Utility
- SQLite mặc định
- pandas
- requests

### File parsing
- pdfplumber
- python-docx

### Testing
- pytest

---

## Project structure

```text
HR-Agent/
├── app/
│   ├── api/
│   │   └── main.py
│   ├── core/
│   │   ├── config.py
│   │   └── logging.py
│   ├── db/
│   │   └── session.py
│   ├── models/
│   │   └── candidate.py
│   ├── schemas/
│   │   └── candidate.py
│   ├── services/
│   │   ├── dedup.py
│   │   ├── extractor.py
│   │   ├── normalizer.py
│   │   ├── parsers.py
│   │   ├── query_parser.py
│   │   ├── repository.py
│   │   └── search.py
│   └── ui/
│       └── dashboard.py
├── tests/
│   ├── test_normalizer.py
│   └── test_smoke.py
├── .gitignore
├── Dockerfile
├── README.md
└── requirements.txt
