# INDA CV Intelligence Platform — Refactor 9/10

Bản này là một refactor production-minded của repo `ttung191/HR-Agent`, tập trung vào đúng 3 yêu cầu của đề:

1. Bóc tách CV và lưu database theo schema rõ ràng.
2. Tìm kiếm ứng viên theo năng lực và kinh nghiệm.
3. Có giao diện cho recruiter tương tác.

## Điểm nâng cấp chính

- **Schema quan hệ hóa** thay vì nhét gần hết dữ liệu vào JSON blob.
- **Document / ExtractionRun / Candidate** tách riêng để audit được toàn bộ vòng đời parse.
- **Skills / Experience / Education / Projects / Links** được lưu thành bảng riêng.
- **Search 2 tầng**: SQL pre-filter rồi mới explainable scoring.
- **Skill normalization** có alias map cho các công nghệ phổ biến.
- **Review queue** rõ ràng hơn, confidence có căn cứ hơn.
- **UI recruiter workflow**: upload, search, review, export.
- **Test** cho normalize và search.

## Cấu trúc

```text
app/
  api/main.py
  core/
  db/
  models/
  schemas/
  services/
  ui/dashboard.py
tests/
```

## Chạy backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.api.main:app --reload
```

## Chạy frontend

```bash
streamlit run app/ui/dashboard.py
```

## API chính

- `POST /api/v1/candidates/upload`
- `POST /api/v1/candidates/upload-batch`
- `GET /api/v1/candidates`
- `GET /api/v1/candidates/{id}`
- `POST /api/v1/search`
- `POST /api/v1/query-plan`
- `GET /api/v1/review-queue`
- `POST /api/v1/review/{id}`
- `GET /api/v1/duplicates`
- `GET /api/v1/analytics`
- `GET /api/v1/export.csv`

## Gợi ý nâng tiếp để vượt 9/10 hẳn

- Thêm PostgreSQL + FTS hoặc OpenSearch.
- Bổ sung OCR thật và span-level evidence.
- JD parser dùng LLM nhưng giữ fallback heuristic.
- Background jobs cho batch ingest.
- Human feedback loop để sửa alias/rules.
- Benchmark với bộ CV thật của công ty.
