from __future__ import annotations

import json
from typing import Any

import pandas as pd
import requests
import streamlit as st

DEFAULT_API_BASE = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 60


st.set_page_config(page_title="HR Agent Dashboard", layout="wide")


@st.cache_data(show_spinner=False)
def _status_options() -> list[str]:
    return ["approved", "needs_review", "rejected"]



def _build_url(api_base: str, path: str) -> str:
    return f"{api_base.rstrip('/')}{path}"



def fetch_json(method: str, api_base: str, path: str, **kwargs) -> Any:
    url = _build_url(api_base, path)
    response = requests.request(method=method, url=url, timeout=REQUEST_TIMEOUT, **kwargs)
    response.raise_for_status()
    return response.json()



def fetch_text(method: str, api_base: str, path: str, **kwargs) -> str:
    url = _build_url(api_base, path)
    response = requests.request(method=method, url=url, timeout=REQUEST_TIMEOUT, **kwargs)
    response.raise_for_status()
    return response.text



def _render_candidate_card(candidate: dict[str, Any], explanation: dict[str, Any] | None = None) -> None:
    with st.container(border=True):
        st.markdown(f"### {candidate.get('full_name') or 'Unknown Candidate'}")
        st.write(
            f"**Title:** {candidate.get('current_title') or '-'} | "
            f"**Company:** {candidate.get('current_company') or '-'} | "
            f"**Years:** {candidate.get('total_years_experience') or 0}"
        )
        st.write(
            f"**Confidence:** {candidate.get('confidence_score') or 0} | "
            f"**Review:** {candidate.get('review_status') or 'needs_review'}"
        )
        skills = candidate.get("normalized_skills", []) or []
        if skills:
            st.write(f"**Skills:** {', '.join(skills)}")
        if candidate.get("summary"):
            st.caption(candidate["summary"])

        if explanation:
            st.write(
                f"**Score:** {explanation.get('score', 0)} | "
                f"**Semantic:** {explanation.get('semantic_similarity', 0)} | "
                f"**Years bonus:** {explanation.get('years_experience_bonus', 0)}"
            )
            if explanation.get("matched_required_skills"):
                st.write(
                    f"**Required skills matched:** {', '.join(explanation.get('matched_required_skills', []))}"
                )
            if explanation.get("matched_optional_skills"):
                st.write(
                    f"**Optional skills matched:** {', '.join(explanation.get('matched_optional_skills', []))}"
                )
            if explanation.get("matched_roles"):
                st.write(f"**Matched roles:** {', '.join(explanation.get('matched_roles', []))}")
            if explanation.get("matched_locations"):
                st.write(f"**Matched locations:** {', '.join(explanation.get('matched_locations', []))}")
            if explanation.get("matched_degrees"):
                st.write(f"**Matched degrees:** {', '.join(explanation.get('matched_degrees', []))}")
            if explanation.get("keyword_hits"):
                st.write(f"**Keyword hits:** {', '.join(explanation.get('keyword_hits', []))}")
            penalties = explanation.get("penalties", []) or []
            if penalties:
                st.warning(f"Penalties: {', '.join(penalties)}")



def _render_match_card(item: dict[str, Any]) -> None:
    candidate = item.get("candidate", {})
    breakdown = item.get("breakdown", {})
    with st.container(border=True):
        st.markdown(f"### {candidate.get('full_name') or 'Unknown Candidate'}")
        st.write(
            f"**Title:** {candidate.get('current_title') or '-'} | "
            f"**Company:** {candidate.get('current_company') or '-'} | "
            f"**Years:** {candidate.get('total_years_experience') or 0}"
        )
        st.write(
            f"**Final score:** {breakdown.get('final_score', 0)} | "
            f"**Semantic:** {breakdown.get('semantic_similarity', 0)} | "
            f"**Skill alignment:** {breakdown.get('skill_alignment', 0)}"
        )
        if breakdown.get("matched_must_have_skills"):
            st.write(
                f"**Must-have matched:** {', '.join(breakdown.get('matched_must_have_skills', []))}"
            )
        if breakdown.get("matched_nice_to_have_skills"):
            st.write(
                f"**Nice-to-have matched:** {', '.join(breakdown.get('matched_nice_to_have_skills', []))}"
            )
        if breakdown.get("missing_must_have_skills"):
            st.warning(
                f"Missing must-have: {', '.join(breakdown.get('missing_must_have_skills', []))}"
            )
        if breakdown.get("matched_roles"):
            st.write(f"**Matched roles:** {', '.join(breakdown.get('matched_roles', []))}")
        if breakdown.get("matched_degrees"):
            st.write(f"**Matched degrees:** {', '.join(breakdown.get('matched_degrees', []))}")
        notes = breakdown.get("notes", []) or []
        if notes:
            st.info(" | ".join(notes))


st.title("HR Agent - CV Screening Dashboard")

with st.sidebar:
    st.header("Connection")
    api_base = st.text_input("API Base URL", value=DEFAULT_API_BASE)
    if st.button("Health Check", use_container_width=True):
        try:
            health = fetch_json("GET", api_base, "/health")
            st.success(f"Backend OK - version {health.get('version')}")
        except Exception as exc:
            st.error(f"Health check failed: {exc}")

    st.divider()
    st.caption("Run backend first:")
    st.code("python -m uvicorn app.api.main:app --reload", language="bash")
    st.caption("Then launch dashboard:")
    st.code("streamlit run app/ui/dashboard.py", language="bash")


tab_upload, tab_search, tab_match, tab_review, tab_analytics = st.tabs(
    ["Upload CV", "Search Candidates", "JD Match", "Review Queue", "Analytics"]
)

with tab_upload:
    st.subheader("Upload one or multiple CV files")
    upload_mode = st.radio("Upload mode", options=["Single", "Batch"], horizontal=True)
    uploaded_files = st.file_uploader(
        "Upload CVs (.pdf, .docx, .txt)",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Process Uploaded CVs", use_container_width=True):
            if not uploaded_files:
                st.warning("Please upload at least one file.")
            else:
                try:
                    if upload_mode == "Single":
                        first = uploaded_files[0]
                        payload = {
                            "file": (
                                first.name,
                                first.getvalue(),
                                first.type or "application/octet-stream",
                            )
                        }
                        data = fetch_json("POST", api_base, "/api/v1/candidates/upload", files=payload)
                        st.success("Upload finished.")
                        st.json(data)
                    else:
                        files_payload = [
                            ("files", (item.name, item.getvalue(), item.type or "application/octet-stream"))
                            for item in uploaded_files
                        ]
                        data = fetch_json(
                            "POST",
                            api_base,
                            "/api/v1/candidates/upload-batch",
                            files=files_payload,
                        )
                        st.success("Batch processing finished.")
                        st.dataframe(pd.DataFrame(data), use_container_width=True)
                except Exception as exc:
                    st.error(f"Upload failed: {exc}")
    with col2:
        if st.button("Rebuild Vectors", use_container_width=True):
            try:
                data = fetch_json("POST", api_base, "/api/v1/candidates/rebuild-vectors")
                st.success("Vector rebuild finished.")
                st.json(data)
            except Exception as exc:
                st.error(f"Vector rebuild failed: {exc}")

with tab_search:
    st.subheader("Search by recruiter query")
    query = st.text_input(
        "Example: AI engineer 3 năm python fastapi rag vector database",
        value="AI engineer 3 năm python fastapi rag",
    )
    limit = st.slider("Limit", min_value=5, max_value=100, value=20)
    review_status = st.selectbox(
        "Review status filter",
        options=["all", "approved", "needs_review", "rejected"],
        index=0,
    )
    col_filters_1, col_filters_2 = st.columns(2)
    with col_filters_1:
        must_have_skills = st.text_input("Must-have skills", value="python, fastapi")
        role_keywords = st.text_input("Role keywords", value="ai engineer")
        degree_keywords = st.text_input("Degree keywords", value="")
    with col_filters_2:
        nice_to_have_skills = st.text_input("Nice-to-have skills", value="rag, vector database")
        location_keywords = st.text_input("Location keywords", value="")
        minimum_years_experience = st.number_input(
            "Minimum years experience",
            min_value=0.0,
            max_value=50.0,
            value=0.0,
            step=0.5,
        )
    use_vectors = st.checkbox("Use vector similarity", value=True)
    semantic_weight = st.slider("Semantic weight", min_value=0.0, max_value=1.0, value=0.45, step=0.05)

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Preview Query Plan", use_container_width=True):
            try:
                data = fetch_json("GET", api_base, "/api/v1/query-plan", params={"query": query})
                st.json(data)
            except Exception as exc:
                st.error(f"Failed to preview query plan: {exc}")
    with col2:
        if st.button("Search Now", use_container_width=True):
            try:
                data = fetch_json(
                    "POST",
                    api_base,
                    "/api/v1/search",
                    json={
                        "query": query,
                        "limit": limit,
                        "review_status": None if review_status == "all" else review_status,
                        "must_have_skills": [item.strip() for item in must_have_skills.split(",") if item.strip()] or None,
                        "nice_to_have_skills": [item.strip() for item in nice_to_have_skills.split(",") if item.strip()] or None,
                        "role_keywords": [item.strip() for item in role_keywords.split(",") if item.strip()] or None,
                        "location_keywords": [item.strip() for item in location_keywords.split(",") if item.strip()] or None,
                        "degree_keywords": [item.strip() for item in degree_keywords.split(",") if item.strip()] or None,
                        "minimum_years_experience": minimum_years_experience or None,
                        "use_vectors": use_vectors,
                        "semantic_weight": semantic_weight,
                    },
                )
                if not data:
                    st.info("No candidates matched.")
                else:
                    summary_rows: list[dict[str, Any]] = []
                    for item in data:
                        candidate = item["candidate"]
                        explanation = item["explanation"]
                        summary_rows.append(
                            {
                                "candidate_id": candidate.get("id"),
                                "full_name": candidate.get("full_name"),
                                "title": candidate.get("current_title"),
                                "company": candidate.get("current_company"),
                                "years": candidate.get("total_years_experience"),
                                "score": explanation.get("score"),
                                "semantic_similarity": explanation.get("semantic_similarity"),
                                "matched_required_skills": ", ".join(explanation.get("matched_required_skills", [])),
                            }
                        )
                    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)
                    st.divider()
                    for item in data:
                        _render_candidate_card(item["candidate"], item["explanation"])
            except Exception as exc:
                st.error(f"Search failed: {exc}")

with tab_match:
    st.subheader("Match JD with vectorized candidate profiles")
    jd_text = st.text_area(
        "JD text",
        value=(
            "Cần AI Engineer có Python, FastAPI, RAG, vector database, "
            "tối thiểu 3 năm kinh nghiệm, ưu tiên Computer Science"
        ),
        height=180,
    )
    candidate_ids_text = st.text_input("Candidate IDs filter (optional)", value="")
    col1, col2, col3 = st.columns(3)
    with col1:
        jd_limit = st.slider("Top K", min_value=1, max_value=100, value=10)
    with col2:
        semantic_weight = st.slider("JD semantic weight", min_value=0.0, max_value=1.0, value=0.45, step=0.05)
    with col3:
        skill_weight = st.slider("JD skill weight", min_value=0.0, max_value=1.0, value=0.30, step=0.05)
    col4, col5 = st.columns(2)
    with col4:
        role_weight = st.slider("JD role weight", min_value=0.0, max_value=1.0, value=0.10, step=0.05)
    with col5:
        years_weight = st.slider("JD years weight", min_value=0.0, max_value=1.0, value=0.10, step=0.05)
    degree_weight = st.slider("JD degree weight", min_value=0.0, max_value=1.0, value=0.05, step=0.05)

    if st.button("Run JD Match", use_container_width=True):
        try:
            candidate_ids = [int(item.strip()) for item in candidate_ids_text.split(",") if item.strip().isdigit()] or None
            data = fetch_json(
                "POST",
                api_base,
                "/api/v1/match/jd",
                json={
                    "jd_text": jd_text,
                    "limit": jd_limit,
                    "candidate_ids": candidate_ids,
                    "semantic_weight": semantic_weight,
                    "skill_weight": skill_weight,
                    "role_weight": role_weight,
                    "years_weight": years_weight,
                    "degree_weight": degree_weight,
                },
            )
            st.markdown("#### Parsed JD")
            st.json(data.get("parsed_jd", {}))
            results = data.get("results", [])
            if not results:
                st.info("No candidates matched this JD.")
            else:
                summary_rows: list[dict[str, Any]] = []
                for item in results:
                    candidate = item.get("candidate", {})
                    breakdown = item.get("breakdown", {})
                    summary_rows.append(
                        {
                            "candidate_id": candidate.get("id"),
                            "full_name": candidate.get("full_name"),
                            "title": candidate.get("current_title"),
                            "final_score": breakdown.get("final_score"),
                            "semantic_similarity": breakdown.get("semantic_similarity"),
                            "skill_alignment": breakdown.get("skill_alignment"),
                            "missing_must_have_skills": ", ".join(breakdown.get("missing_must_have_skills", [])),
                        }
                    )
                st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)
                st.divider()
                for item in results:
                    _render_match_card(item)
        except Exception as exc:
            st.error(f"JD matching failed: {exc}")

with tab_review:
    st.subheader("Candidates needing review")
    if st.button("Refresh Review Queue", use_container_width=True):
        try:
            data = fetch_json("GET", api_base, "/api/v1/review-queue")
            if not data:
                st.info("No candidates in review queue.")
            else:
                for candidate in data:
                    with st.container(border=True):
                        st.markdown(f"### {candidate.get('full_name') or 'Unknown Candidate'}")
                        st.write(
                            f"**Candidate ID:** {candidate.get('id')} | "
                            f"**Confidence:** {candidate.get('confidence_score')} | "
                            f"**Title:** {candidate.get('current_title') or '-'}"
                        )
                        st.write(f"**Skills:** {', '.join(candidate.get('normalized_skills', []))}")
                        new_status = st.selectbox(
                            f"Update review status for #{candidate.get('id')}",
                            options=_status_options(),
                            key=f"status_{candidate.get('id')}",
                        )
                        reason = st.text_input(
                            "Review reason",
                            key=f"reason_{candidate.get('id')}",
                        )
                        if st.button(f"Save Review #{candidate.get('id')}", key=f"save_{candidate.get('id')}"):
                            payload = {"review_status": new_status, "review_reason": reason}
                            try:
                                fetch_json(
                                    "POST",
                                    api_base,
                                    f"/api/v1/review/{candidate.get('id')}",
                                    json=payload,
                                )
                                st.success("Review updated.")
                            except Exception as exc:
                                st.error(f"Failed to update review: {exc}")
        except Exception as exc:
            st.error(f"Failed to load review queue: {exc}")

with tab_analytics:
    st.subheader("System analytics")
    col1, col2 = st.columns(2)
    if st.button("Load Analytics", use_container_width=True):
        try:
            analytics = fetch_json("GET", api_base, "/api/v1/analytics")
            with col1:
                st.metric("Total Candidates", analytics.get("total_candidates", 0))
                st.metric("Avg Confidence Score", analytics.get("avg_confidence_score", 0.0))
                st.write("Review Status Breakdown")
                st.json(analytics.get("review_status_breakdown", {}))
            with col2:
                st.write("Top Roles")
                st.dataframe(
                    pd.DataFrame(analytics.get("top_roles", []), columns=["role", "count"]),
                    use_container_width=True,
                )
                st.write("Top Skills")
                st.dataframe(
                    pd.DataFrame(analytics.get("top_skills", []), columns=["skill", "count"]),
                    use_container_width=True,
                )
        except Exception as exc:
            st.error(f"Failed to load analytics: {exc}")

    st.divider()
    st.subheader("Duplicate Groups")
    if st.button("Load Duplicates", use_container_width=True):
        try:
            duplicates = fetch_json("GET", api_base, "/api/v1/duplicates")
            if duplicates:
                st.json(duplicates)
            else:
                st.info("No duplicate groups found.")
        except Exception as exc:
            st.error(f"Failed to load duplicates: {exc}")

    st.divider()
    st.subheader("Export CSV")
    if st.button("Export Candidates CSV", use_container_width=True):
        try:
            csv_text = fetch_text("GET", api_base, "/api/v1/export.csv")
            st.download_button(
                "Download candidates.csv",
                data=csv_text,
                file_name="candidates.csv",
                mime="text/csv",
                use_container_width=True,
            )
            with st.expander("CSV preview"):
                st.code(csv_text[:5000])
        except Exception as exc:
            st.error(f"Export failed: {exc}")

with st.expander("Quick payload examples"):
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
