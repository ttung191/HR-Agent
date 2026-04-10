from __future__ import annotations

import json
from typing import Any

import requests
import streamlit as st

DEFAULT_API_BASE = "http://127.0.0.1:8000"
TIMEOUT_SECONDS = 60

st.set_page_config(page_title="HR Agent Control Center", page_icon="🧠", layout="wide")


def _inject_style() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2rem;
        }
        .app-card {
            background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,250,252,0.96));
            border: 1px solid rgba(15,23,42,0.08);
            border-radius: 18px;
            padding: 18px 18px 14px 18px;
            box-shadow: 0 10px 30px rgba(15,23,42,0.05);
            margin-bottom: 12px;
        }
        .hero-card {
            background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 55%, #0ea5e9 100%);
            border-radius: 22px;
            padding: 24px 24px 18px 24px;
            color: white;
            box-shadow: 0 20px 40px rgba(37,99,235,0.22);
            margin-bottom: 16px;
        }
        .hero-title {
            font-size: 1.7rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }
        .hero-subtitle {
            font-size: 0.98rem;
            opacity: 0.92;
        }
        .metric-label {
            color: #64748b;
            font-size: 0.86rem;
            margin-bottom: 4px;
        }
        .metric-value {
            font-size: 1.45rem;
            font-weight: 700;
            color: #0f172a;
        }
        .section-note {
            color: #475569;
            font-size: 0.93rem;
            margin-top: 4px;
        }
        div[data-testid="stMetric"] {
            background: white;
            border: 1px solid rgba(15,23,42,0.07);
            border-radius: 18px;
            padding: 12px 14px;
            box-shadow: 0 10px 25px rgba(15,23,42,0.04);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


_inject_style()


def _init_state() -> None:
    defaults = {
        "candidate_cache": [],
        "analytics_cache": None,
        "duplicates_cache": None,
        "review_queue_cache": None,
        "last_upload_result": None,
        "last_health_result": None,
        "last_query_plan": None,
        "last_search_result": None,
        "last_jd_result": None,
        "last_candidate_detail": None,
        "selected_candidate_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_state()


def _build_url(api_base: str, path: str) -> str:
    return f"{api_base.rstrip('/')}{path}"


def _parse_json_response(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text


def _request(
    method: str,
    api_base: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    files: Any = None,
) -> tuple[bool, int | None, Any]:
    url = _build_url(api_base, path)
    try:
        response = requests.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
            files=files,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return False, None, {"error": str(exc), "url": url}

    payload = _parse_json_response(response)
    return response.ok, response.status_code, payload


def _show_response(ok: bool, status_code: int | None, payload: Any) -> None:
    if ok:
        st.success(f"OK ({status_code})")
    else:
        st.error(f"Request failed ({status_code})")
    st.json(payload)


def _show_payload_preview(title: str, payload: Any) -> None:
    with st.expander(title, expanded=False):
        st.code(json.dumps(payload, ensure_ascii=False, indent=2), language="json")


def _candidate_label(candidate: dict[str, Any]) -> str:
    candidate_id = candidate.get("id")
    name = candidate.get("full_name") or "Unknown"
    title = candidate.get("current_title") or "No title"
    company = candidate.get("current_company") or "No company"
    return f"#{candidate_id} · {name} · {title} · {company}"


def _split_csv_input(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _render_chip_list(title: str, items: list[str] | None, empty_text: str = "Không có") -> None:
    st.markdown(f"**{title}**")
    if not items:
        st.caption(empty_text)
        return
    st.write(" · ".join(items))


def _refresh_candidates(api_base: str, *, quiet: bool = False) -> list[dict[str, Any]]:
    ok, status_code, payload = _request("GET", api_base, "/api/v1/candidates")
    if ok and isinstance(payload, list):
        st.session_state["candidate_cache"] = payload
    elif not quiet:
        _show_response(ok, status_code, payload)
    return st.session_state.get("candidate_cache", [])


def _refresh_optional_cache(api_base: str, path: str, state_key: str) -> None:
    ok, _, payload = _request("GET", api_base, path)
    if ok:
        st.session_state[state_key] = payload


def _top_candidate_metrics(candidates: list[dict[str, Any]]) -> tuple[int, int, int, float]:
    with_email = sum(1 for item in candidates if item.get("primary_email"))
    with_phone = sum(1 for item in candidates if item.get("primary_phone"))
    with_vectors = sum(1 for item in candidates if item.get("embedding") or item.get("vector_status") == "ready")
    years = []
    for item in candidates:
        value = item.get("total_years_experience")
        if isinstance(value, (int, float)):
            years.append(float(value))
    avg_years = round(sum(years) / len(years), 2) if years else 0.0
    return with_email, with_phone, with_vectors, avg_years


def _render_overview(api_base: str) -> None:
    st.markdown(
        """
        <div class="hero-card">
            <div class="hero-title">HR Agent Control Center</div>
            <div class="hero-subtitle">
                Một layout tập trung để nhìn trọn flow: upload CV, parse, candidate explorer,
                hybrid search, JD matching, analytics và export — không phải nhảy qua nhiều tab nhỏ rời rạc nữa.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    candidates = st.session_state.get("candidate_cache", [])
    if not candidates:
        candidates = _refresh_candidates(api_base, quiet=True)
    if st.session_state.get("analytics_cache") is None:
        _refresh_optional_cache(api_base, "/api/v1/analytics", "analytics_cache")
    if st.session_state.get("duplicates_cache") is None:
        _refresh_optional_cache(api_base, "/api/v1/duplicates", "duplicates_cache")
    if st.session_state.get("review_queue_cache") is None:
        _refresh_optional_cache(api_base, "/api/v1/review-queue", "review_queue_cache")

    with_email, with_phone, with_vectors, avg_years = _top_candidate_metrics(candidates)
    analytics = st.session_state.get("analytics_cache")
    duplicates = st.session_state.get("duplicates_cache")
    review_queue = st.session_state.get("review_queue_cache")

    cols = st.columns(5)
    cols[0].metric("Candidates", len(candidates))
    cols[1].metric("Có email", with_email)
    cols[2].metric("Có phone", with_phone)
    cols[3].metric("Vector ready", with_vectors)
    cols[4].metric("Avg years", avg_years)

    left, right = st.columns([1.1, 0.9], gap="large")

    with left:
        st.markdown("### Snapshot hệ thống")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Check /health", use_container_width=True):
                ok, status_code, payload = _request("GET", api_base, "/health")
                st.session_state["last_health_result"] = {"ok": ok, "status_code": status_code, "payload": payload}
        with c2:
            if st.button("Sample query plan", use_container_width=True):
                ok, status_code, payload = _request(
                    "GET",
                    api_base,
                    "/api/v1/query-plan",
                    params={"query": "AI Engineer Python FastAPI RAG 3 years"},
                )
                st.session_state["last_query_plan"] = {"ok": ok, "status_code": status_code, "payload": payload}

        last_health = st.session_state.get("last_health_result")
        if last_health:
            st.markdown("#### Health response")
            _show_response(last_health["ok"], last_health["status_code"], last_health["payload"])

        last_query_plan = st.session_state.get("last_query_plan")
        if last_query_plan:
            st.markdown("#### Query plan sample")
            _show_response(last_query_plan["ok"], last_query_plan["status_code"], last_query_plan["payload"])

    with right:
        st.markdown("### Tín hiệu vận hành")
        review_count = len(review_queue) if isinstance(review_queue, list) else 0
        duplicate_count = len(duplicates) if isinstance(duplicates, list) else 0
        analytics_count = len(analytics) if isinstance(analytics, dict) else 0
        st.info(
            f"Review queue: **{review_count}** · Duplicates: **{duplicate_count}** · Analytics keys: **{analytics_count}**"
        )
        if analytics:
            _show_payload_preview("Preview analytics", analytics)
        if duplicates:
            _show_payload_preview("Preview duplicates", duplicates[:10] if isinstance(duplicates, list) else duplicates)
        if review_queue:
            _show_payload_preview("Preview review queue", review_queue[:10] if isinstance(review_queue, list) else review_queue)

    st.markdown("### Flow map")
    flow_cols = st.columns(4)
    flow_cols[0].markdown("**1. Upload & Parse**\n\nĐẩy CV đơn lẻ hoặc batch và xem phản hồi parser ngay sau khi upload.")
    flow_cols[1].markdown("**2. Candidate Explorer**\n\nLọc, xem chi tiết hồ sơ, raw JSON, skill và section trọng yếu.")
    flow_cols[2].markdown("**3. Search Workspace**\n\nTest hybrid search với query, must-have skills, vectors, semantic weight.")
    flow_cols[3].markdown("**4. JD Match & Admin**\n\nSo khớp JD, rebuild vectors, analytics, export CSV, review queue.")


def _render_upload_page(api_base: str) -> None:
    st.markdown("### Upload & Parse Workspace")
    st.caption("Bố cục mới ưu tiên nhìn rõ 3 thứ cùng lúc: queue file, action upload, và kết quả trả về gần nhất.")

    left, right = st.columns([1.1, 0.9], gap="large")

    with left:
        with st.container(border=True):
            st.markdown("#### Upload center")
            upload_mode = st.radio("Chế độ upload", options=["Single", "Batch"], horizontal=True)
            uploaded_files = st.file_uploader(
                "Chọn CV (.pdf, .docx, .txt)",
                type=["pdf", "docx", "txt"],
                accept_multiple_files=True,
            )

            if uploaded_files:
                st.markdown("**Queue hiện tại**")
                queue_rows = []
                for item in uploaded_files:
                    queue_rows.append(
                        {
                            "file_name": item.name,
                            "mime_type": item.type or "application/octet-stream",
                            "size_kb": round(len(item.getvalue()) / 1024, 2),
                        }
                    )
                st.dataframe(queue_rows, use_container_width=True, hide_index=True)

            action_cols = st.columns([1, 1, 1])
            with action_cols[0]:
                run_single = st.button("Upload 1 CV", disabled=not uploaded_files or upload_mode != "Single", use_container_width=True)
            with action_cols[1]:
                run_batch = st.button("Upload batch", disabled=not uploaded_files or upload_mode != "Batch", use_container_width=True)
            with action_cols[2]:
                refresh_after = st.button("Refresh candidates", use_container_width=True)

            if run_single and uploaded_files:
                first_file = uploaded_files[0]
                files = {"file": (first_file.name, first_file.getvalue(), first_file.type or "application/octet-stream")}
                ok, status_code, payload = _request("POST", api_base, "/api/v1/candidates/upload", files=files)
                st.session_state["last_upload_result"] = {"ok": ok, "status_code": status_code, "payload": payload}
                if ok:
                    _refresh_candidates(api_base, quiet=True)

            if run_batch and uploaded_files:
                files = [("files", (item.name, item.getvalue(), item.type or "application/octet-stream")) for item in uploaded_files]
                ok, status_code, payload = _request("POST", api_base, "/api/v1/candidates/upload-batch", files=files)
                st.session_state["last_upload_result"] = {"ok": ok, "status_code": status_code, "payload": payload}
                if ok:
                    _refresh_candidates(api_base, quiet=True)

            if refresh_after:
                _refresh_candidates(api_base)
                st.success("Đã refresh candidate cache")

    with right:
        with st.container(border=True):
            st.markdown("#### Kết quả upload gần nhất")
            last_upload = st.session_state.get("last_upload_result")
            if last_upload:
                _show_response(last_upload["ok"], last_upload["status_code"], last_upload["payload"])
            else:
                st.info("Chưa có request upload nào trong session này.")

        with st.container(border=True):
            st.markdown("#### Candidate cache sau upload")
            candidates = st.session_state.get("candidate_cache", [])
            st.write(f"Tổng candidate trong cache: **{len(candidates)}**")
            preview = []
            for item in candidates[:15]:
                preview.append(
                    {
                        "id": item.get("id"),
                        "full_name": item.get("full_name"),
                        "title": item.get("current_title"),
                        "company": item.get("current_company"),
                        "skills": ", ".join(item.get("normalized_skills", [])[:6]),
                    }
                )
            if preview:
                st.dataframe(preview, use_container_width=True, hide_index=True)
            else:
                st.caption("Chưa có candidate trong cache.")


def _render_candidate_explorer(api_base: str) -> None:
    st.markdown("### Candidate Explorer")
    st.caption("Mục này gom list, filter và detail về cùng một chỗ để xem được toàn bộ hồ sơ mà không phải mở từng response rời rạc.")

    candidates = _refresh_candidates(api_base, quiet=True)

    filter_col1, filter_col2, filter_col3 = st.columns([1.2, 1.2, 0.8])
    with filter_col1:
        keyword = st.text_input("Lọc theo tên / title / company", value="")
    with filter_col2:
        skill_filter = st.text_input("Lọc theo skill", value="")
    with filter_col3:
        min_years = st.number_input("Min years", min_value=0.0, max_value=50.0, value=0.0, step=0.5)

    filtered = []
    keyword_fold = keyword.strip().lower()
    skill_fold = skill_filter.strip().lower()
    for item in candidates:
        haystack = " ".join(
            str(item.get(field, ""))
            for field in ["full_name", "current_title", "current_company", "summary"]
        ).lower()
        skills = [str(skill).lower() for skill in item.get("normalized_skills", [])]
        years = item.get("total_years_experience") or 0

        if keyword_fold and keyword_fold not in haystack:
            continue
        if skill_fold and not any(skill_fold in skill for skill in skills):
            continue
        if isinstance(years, (int, float)) and float(years) < float(min_years):
            continue
        filtered.append(item)

    st.write(f"Hiển thị **{len(filtered)} / {len(candidates)}** candidates")

    list_col, detail_col = st.columns([0.95, 1.25], gap="large")

    with list_col:
        with st.container(border=True):
            st.markdown("#### Candidate list")
            if filtered:
                options = {_candidate_label(item): item for item in filtered}
                current_label = st.selectbox("Chọn candidate", options=list(options.keys()))
                selected_candidate = options[current_label]
                st.session_state["selected_candidate_id"] = selected_candidate.get("id")
                summary_rows = []
                for item in filtered[:50]:
                    summary_rows.append(
                        {
                            "id": item.get("id"),
                            "full_name": item.get("full_name"),
                            "title": item.get("current_title"),
                            "company": item.get("current_company"),
                            "years": item.get("total_years_experience"),
                        }
                    )
                st.dataframe(summary_rows, use_container_width=True, hide_index=True, height=420)
            else:
                selected_candidate = None
                st.info("Không có candidate phù hợp với bộ lọc hiện tại.")

    with detail_col:
        with st.container(border=True):
            st.markdown("#### Candidate detail")
            selected_id = st.session_state.get("selected_candidate_id")
            if selected_id is None and filtered:
                selected_id = filtered[0].get("id")
                st.session_state["selected_candidate_id"] = selected_id

            top_cols = st.columns([0.9, 1.1, 0.8])
            with top_cols[0]:
                load_detail = st.button("Load detail từ API", use_container_width=True)
            with top_cols[1]:
                st.caption("API endpoint: /api/v1/candidates/{id}")
            with top_cols[2]:
                st.caption(f"Selected ID: {selected_id}")

            if load_detail and selected_id is not None:
                ok, status_code, payload = _request("GET", api_base, f"/api/v1/candidates/{selected_id}")
                st.session_state["last_candidate_detail"] = {"ok": ok, "status_code": status_code, "payload": payload}

            selected_candidate = None
            for item in filtered:
                if item.get("id") == selected_id:
                    selected_candidate = item
                    break
            if selected_candidate is None:
                for item in candidates:
                    if item.get("id") == selected_id:
                        selected_candidate = item
                        break

            if selected_candidate:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Name", selected_candidate.get("full_name") or "—")
                c2.metric("Title", selected_candidate.get("current_title") or "—")
                c3.metric("Company", selected_candidate.get("current_company") or "—")
                c4.metric("Years", selected_candidate.get("total_years_experience") or 0)

                subtab1, subtab2, subtab3 = st.tabs(["Overview", "Raw candidate", "API detail"])
                with subtab1:
                    st.markdown(selected_candidate.get("summary") or "_Không có summary_")
                    _render_chip_list("Skills", selected_candidate.get("normalized_skills", []))
                    st.markdown("**Contact**")
                    st.write(
                        {
                            "email": selected_candidate.get("primary_email"),
                            "phone": selected_candidate.get("primary_phone"),
                            "address": selected_candidate.get("address"),
                        }
                    )
                with subtab2:
                    st.json(selected_candidate)
                with subtab3:
                    last_detail = st.session_state.get("last_candidate_detail")
                    if last_detail:
                        _show_response(last_detail["ok"], last_detail["status_code"], last_detail["payload"])
                    else:
                        st.info("Chưa load API detail trong session này.")
            else:
                st.info("Chưa có candidate nào được chọn.")


def _render_search_page(api_base: str) -> None:
    st.markdown("### Search Workspace")
    st.caption("Chia màn hình thành form bên trái và kết quả bên phải để test hybrid retrieval nhanh hơn.")

    left, right = st.columns([0.95, 1.25], gap="large")
    with left:
        with st.form("search_form"):
            query = st.text_area(
                "Search query",
                value="AI Engineer Python FastAPI RAG vector database 3 years",
                height=140,
            )
            limit = st.number_input("Limit", min_value=1, max_value=100, value=10)
            minimum_years = st.number_input("Minimum years", min_value=0.0, max_value=50.0, value=0.0, step=0.5)
            semantic_weight = st.slider("Semantic weight", min_value=0.0, max_value=1.0, value=0.45, step=0.05)
            must_have_skills = st.text_input("Must-have skills", value="python, fastapi")
            nice_to_have_skills = st.text_input("Nice-to-have skills", value="rag, vector database")
            use_vectors = st.checkbox("Use vectors", value=True)
            submitted = st.form_submit_button("Run search", use_container_width=True)

        if submitted:
            payload = {
                "query": query,
                "limit": int(limit),
                "minimum_years_experience": minimum_years if minimum_years > 0 else None,
                "must_have_skills": _split_csv_input(must_have_skills) or None,
                "nice_to_have_skills": _split_csv_input(nice_to_have_skills) or None,
                "use_vectors": use_vectors,
                "semantic_weight": semantic_weight,
            }
            ok, status_code, result = _request("POST", api_base, "/api/v1/search", json_body=payload)
            st.session_state["last_search_result"] = {
                "ok": ok,
                "status_code": status_code,
                "payload": result,
                "request": payload,
            }

    with right:
        with st.container(border=True):
            st.markdown("#### Search result")
            last_search = st.session_state.get("last_search_result")
            if not last_search:
                st.info("Chưa chạy search trong session này.")
            else:
                _show_payload_preview("Request payload", last_search["request"])
                _show_response(last_search["ok"], last_search["status_code"], last_search["payload"])

                result = last_search["payload"]
                if last_search["ok"] and isinstance(result, list) and result:
                    rows = []
                    for item in result:
                        candidate = item.get("candidate", {})
                        explanation = item.get("explanation", {})
                        rows.append(
                            {
                                "candidate_id": candidate.get("id"),
                                "full_name": candidate.get("full_name"),
                                "title": candidate.get("current_title"),
                                "company": candidate.get("current_company"),
                                "years": candidate.get("total_years_experience"),
                                "score": explanation.get("score"),
                                "semantic_similarity": explanation.get("semantic_similarity"),
                                "matched_required_skills": ", ".join(explanation.get("matched_required_skills", [])),
                                "missing_required_skills": ", ".join(explanation.get("missing_required_skills", [])),
                            }
                        )
                    st.dataframe(rows, use_container_width=True, hide_index=True)

                    st.markdown("#### Result cards")
                    for idx, item in enumerate(result[:10], start=1):
                        candidate = item.get("candidate", {})
                        explanation = item.get("explanation", {})
                        with st.expander(f"#{idx} · {candidate.get('full_name')} · score={explanation.get('score')}", expanded=idx == 1):
                            col1, col2 = st.columns([1, 1])
                            with col1:
                                st.write(
                                    {
                                        "candidate_id": candidate.get("id"),
                                        "title": candidate.get("current_title"),
                                        "company": candidate.get("current_company"),
                                        "years": candidate.get("total_years_experience"),
                                    }
                                )
                            with col2:
                                st.write(
                                    {
                                        "semantic_similarity": explanation.get("semantic_similarity"),
                                        "matched_required_skills": explanation.get("matched_required_skills", []),
                                        "missing_required_skills": explanation.get("missing_required_skills", []),
                                    }
                                )
                elif last_search["ok"]:
                    st.warning("Search chạy thành công nhưng không có kết quả phù hợp.")


def _render_match_page(api_base: str) -> None:
    st.markdown("### JD Matching Workspace")
    st.caption("Tập trung vào 2 lớp nhìn: parsed JD bên trái và ranking breakdown bên phải.")

    left, right = st.columns([0.95, 1.25], gap="large")
    with left:
        with st.form("jd_match_form"):
            jd_text = st.text_area(
                "JD text",
                value=(
                    "Cần AI Engineer có Python, FastAPI, RAG, vector database, tối thiểu 3 năm kinh nghiệm, "
                    "ưu tiên Computer Science"
                ),
                height=220,
            )
            jd_limit = st.number_input("Top K", min_value=1, max_value=100, value=10)
            jd_semantic_weight = st.slider("JD semantic weight", 0.0, 1.0, 0.45, 0.05)
            jd_skill_weight = st.slider("JD skill weight", 0.0, 1.0, 0.30, 0.05)
            jd_role_weight = st.slider("JD role weight", 0.0, 1.0, 0.10, 0.05)
            jd_years_weight = st.slider("JD years weight", 0.0, 1.0, 0.10, 0.05)
            jd_degree_weight = st.slider("JD degree weight", 0.0, 1.0, 0.05, 0.05)
            candidate_filter = st.text_input("Candidate IDs giới hạn", value="")
            submitted = st.form_submit_button("Run JD matching", use_container_width=True)

        if submitted:
            candidate_ids = [int(item.strip()) for item in candidate_filter.split(",") if item.strip().isdigit()] or None
            payload = {
                "jd_text": jd_text,
                "limit": int(jd_limit),
                "candidate_ids": candidate_ids,
                "semantic_weight": jd_semantic_weight,
                "skill_weight": jd_skill_weight,
                "role_weight": jd_role_weight,
                "years_weight": jd_years_weight,
                "degree_weight": jd_degree_weight,
            }
            ok, status_code, result = _request("POST", api_base, "/api/v1/match/jd", json_body=payload)
            st.session_state["last_jd_result"] = {
                "ok": ok,
                "status_code": status_code,
                "payload": result,
                "request": payload,
            }

    with right:
        with st.container(border=True):
            st.markdown("#### JD match result")
            last_jd = st.session_state.get("last_jd_result")
            if not last_jd:
                st.info("Chưa chạy JD matching trong session này.")
            else:
                _show_payload_preview("JD request payload", last_jd["request"])
                _show_response(last_jd["ok"], last_jd["status_code"], last_jd["payload"])

                result = last_jd["payload"]
                if last_jd["ok"] and isinstance(result, dict):
                    parsed_jd = result.get("parsed_jd", {})
                    results = result.get("results", [])
                    col1, col2 = st.columns([0.9, 1.1])
                    with col1:
                        st.markdown("#### Parsed JD")
                        st.json(parsed_jd)
                    with col2:
                        st.markdown("#### Ranking summary")
                        rows = []
                        for item in results:
                            candidate = item.get("candidate", {})
                            breakdown = item.get("breakdown", {})
                            rows.append(
                                {
                                    "candidate_id": candidate.get("id"),
                                    "full_name": candidate.get("full_name"),
                                    "title": candidate.get("current_title"),
                                    "final_score": breakdown.get("final_score"),
                                    "semantic_similarity": breakdown.get("semantic_similarity"),
                                    "skill_alignment": breakdown.get("skill_alignment"),
                                    "role_alignment": breakdown.get("role_alignment"),
                                    "years_alignment": breakdown.get("years_alignment"),
                                    "degree_alignment": breakdown.get("degree_alignment"),
                                }
                            )
                        if rows:
                            st.dataframe(rows, use_container_width=True, hide_index=True)
                        else:
                            st.caption("Không có candidate nào được trả về.")

                    for idx, item in enumerate(results[:10], start=1):
                        candidate = item.get("candidate", {})
                        breakdown = item.get("breakdown", {})
                        with st.expander(f"#{idx} · {candidate.get('full_name')} · final_score={breakdown.get('final_score')}", expanded=idx == 1):
                            left_card, right_card = st.columns([1, 1])
                            with left_card:
                                st.write(candidate)
                            with right_card:
                                st.write(breakdown)


def _render_admin_page(api_base: str) -> None:
    st.markdown("### Admin & Export")
    st.caption("Gom các endpoint vận hành vào một dashboard duy nhất để dễ rebuild, debug và export.")

    action_cols = st.columns(4)
    action_map = [
        ("Rebuild vectors", "POST", "/api/v1/candidates/rebuild-vectors", None),
        ("Load analytics", "GET", "/api/v1/analytics", "analytics_cache"),
        ("Load duplicates", "GET", "/api/v1/duplicates", "duplicates_cache"),
        ("Load review queue", "GET", "/api/v1/review-queue", "review_queue_cache"),
    ]

    for col, (label, method, path, state_key) in zip(action_cols, action_map):
        with col:
            if st.button(label, use_container_width=True):
                ok, status_code, payload = _request(method, api_base, path)
                if ok and state_key:
                    st.session_state[state_key] = payload
                _show_response(ok, status_code, payload)

    st.markdown("### Export CSV")
    if st.button("Get export.csv", use_container_width=True):
        url = _build_url(api_base, "/api/v1/export.csv")
        try:
            response = requests.get(url, timeout=TIMEOUT_SECONDS)
            if response.ok:
                st.success("Export thành công")
                st.download_button(
                    label="Download export.csv",
                    data=response.text,
                    file_name="export.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
                with st.expander("Preview CSV", expanded=False):
                    st.code(response.text[:5000])
            else:
                st.error(f"Request failed ({response.status_code})")
                try:
                    st.json(response.json())
                except Exception:
                    st.code(response.text)
        except requests.RequestException as exc:
            st.error(str(exc))

    bottom_left, bottom_right = st.columns([1, 1], gap="large")
    with bottom_left:
        st.markdown("#### Analytics cache")
        analytics = st.session_state.get("analytics_cache")
        if analytics is not None:
            st.json(analytics)
        else:
            st.caption("Chưa load analytics.")
    with bottom_right:
        st.markdown("#### Duplicate / review signals")
        duplicates = st.session_state.get("duplicates_cache")
        review_queue = st.session_state.get("review_queue_cache")
        st.write(
            {
                "duplicate_count": len(duplicates) if isinstance(duplicates, list) else 0,
                "review_queue_count": len(review_queue) if isinstance(review_queue, list) else 0,
            }
        )
        if duplicates:
            _show_payload_preview("Duplicate preview", duplicates[:10] if isinstance(duplicates, list) else duplicates)
        if review_queue:
            _show_payload_preview("Review queue preview", review_queue[:10] if isinstance(review_queue, list) else review_queue)


with st.sidebar:
    st.header("Cấu hình")
    api_base = st.text_input("API Base URL", value=DEFAULT_API_BASE)
    st.caption("Chạy FastAPI trước: python -m uvicorn app.api.main:app --reload")
    st.divider()
    page = st.radio(
        "Điều hướng",
        options=[
            "Overview",
            "Upload & Parse",
            "Candidate Explorer",
            "Search Workspace",
            "JD Match Workspace",
            "Admin & Export",
        ],
    )
    st.divider()
    if st.button("Refresh all lightweight caches", use_container_width=True):
        _refresh_candidates(api_base, quiet=True)
        _refresh_optional_cache(api_base, "/api/v1/analytics", "analytics_cache")
        _refresh_optional_cache(api_base, "/api/v1/duplicates", "duplicates_cache")
        _refresh_optional_cache(api_base, "/api/v1/review-queue", "review_queue_cache")
        st.success("Đã refresh cache UI")
    st.markdown(
        """
        **Tính năng có trong layout này**
        - health + query plan
        - upload single / batch
        - candidate explorer
        - hybrid search
        - JD matching
        - rebuild vectors
        - analytics / duplicates / review queue
        - export CSV
        """
    )

if page == "Overview":
    _render_overview(api_base)
elif page == "Upload & Parse":
    _render_upload_page(api_base)
elif page == "Candidate Explorer":
    _render_candidate_explorer(api_base)
elif page == "Search Workspace":
    _render_search_page(api_base)
elif page == "JD Match Workspace":
    _render_match_page(api_base)
else:
    _render_admin_page(api_base)

with st.expander("Mẫu payload nhanh", expanded=False):
    st.code(
        json.dumps(
            {
                "search_payload": {
                    "query": "AI Engineer Python FastAPI RAG 3 years",
                    "limit": 10,
                    "must_have_skills": ["python", "fastapi"],
                    "nice_to_have_skills": ["rag", "vector database"],
                    "use_vectors": True,
                    "semantic_weight": 0.45,
                },
                "jd_match_payload": {
                    "jd_text": "Cần AI Engineer có Python, FastAPI, RAG, vector database, tối thiểu 3 năm kinh nghiệm",
                    "limit": 10,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        language="json",
    )