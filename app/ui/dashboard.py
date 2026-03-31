from __future__ import annotations

import pandas as pd
import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"


def fetch_json(method: str, path: str, **kwargs):
    url = f"{API_BASE}{path}"
    response = requests.request(method=method, url=url, timeout=60, **kwargs)
    response.raise_for_status()
    return response.json()


st.set_page_config(page_title="HR Agent Dashboard", layout="wide")
st.title("HR Agent - CV Screening Dashboard")

tab_upload, tab_search, tab_review, tab_analytics = st.tabs(
    ["Upload CV", "Search Candidates", "Review Queue", "Analytics"]
)

with tab_upload:
    st.subheader("Upload one or multiple CV files")
    uploaded_files = st.file_uploader(
        "Upload CVs (.pdf, .docx, .txt)",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
    )

    if st.button("Process Uploaded CVs", use_container_width=True):
        if not uploaded_files:
            st.warning("Please upload at least one file.")
        else:
            files_payload = []
            for item in uploaded_files:
                files_payload.append(
                    ("files", (item.name, item.getvalue(), "application/octet-stream"))
                )
            try:
                data = fetch_json("POST", "/api/v1/candidates/upload-batch", files=files_payload)
                st.success("Batch processing finished.")
                st.dataframe(pd.DataFrame(data), use_container_width=True)
            except Exception as exc:
                st.error(f"Upload failed: {exc}")

with tab_search:
    st.subheader("Search by recruiter query")
    query = st.text_input(
        "Example: data engineer 3 năm aws airflow spark",
        value="data engineer 3 năm aws",
    )
    limit = st.slider("Limit", min_value=5, max_value=100, value=20)

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Preview Query Plan", use_container_width=True):
            try:
                data = fetch_json("GET", "/api/v1/query-plan", params={"query": query})
                st.json(data)
            except Exception as exc:
                st.error(f"Failed to preview query plan: {exc}")

    with col2:
        if st.button("Search Now", use_container_width=True):
            try:
                data = fetch_json(
                    "POST",
                    "/api/v1/search",
                    json={
                        "query": query,
                        "limit": limit,
                    },
                )
                if not data:
                    st.info("No candidates matched.")
                else:
                    for item in data:
                        candidate = item["candidate"]
                        explanation = item["explanation"]

                        with st.container(border=True):
                            st.markdown(
                                f"### {candidate.get('full_name') or 'Unknown Candidate'}"
                            )
                            st.write(
                                f"**Title:** {candidate.get('current_title')} | "
                                f"**Company:** {candidate.get('current_company')} | "
                                f"**Years:** {candidate.get('total_years_experience')}"
                            )
                            st.write(
                                f"**Score:** {explanation.get('score')} | "
                                f"**Confidence:** {candidate.get('confidence_score')} | "
                                f"**Review:** {candidate.get('review_status')}"
                            )
                            st.write(
                                f"**Skills:** {', '.join(candidate.get('normalized_skills', []))}"
                            )
                            st.write(
                                f"**Required skills matched:** {', '.join(explanation.get('matched_required_skills', []))}"
                            )
                            st.write(
                                f"**Optional skills matched:** {', '.join(explanation.get('matched_optional_skills', []))}"
                            )
                            st.write(
                                f"**Matched roles:** {', '.join(explanation.get('matched_roles', []))}"
                            )
                            st.write(
                                f"**Keyword hits:** {', '.join(explanation.get('keyword_hits', []))}"
                            )
                            penalties = explanation.get("penalties", [])
                            if penalties:
                                st.warning(f"Penalties: {', '.join(penalties)}")
            except Exception as exc:
                st.error(f"Search failed: {exc}")

with tab_review:
    st.subheader("Candidates needing review")
    if st.button("Refresh Review Queue", use_container_width=True):
        try:
            data = fetch_json("GET", "/api/v1/review-queue")
            if not data:
                st.info("No candidates in review queue.")
            else:
                for candidate in data:
                    with st.container(border=True):
                        st.markdown(f"### {candidate.get('full_name') or 'Unknown Candidate'}")
                        st.write(
                            f"**Candidate ID:** {candidate.get('id')} | "
                            f"**Confidence:** {candidate.get('confidence_score')} | "
                            f"**Title:** {candidate.get('current_title')}"
                        )
                        st.write(f"**Skills:** {', '.join(candidate.get('normalized_skills', []))}")

                        new_status = st.selectbox(
                            f"Update review status for #{candidate.get('id')}",
                            options=["approved", "needs_review", "rejected"],
                            key=f"status_{candidate.get('id')}",
                        )
                        reason = st.text_input(
                            "Review reason",
                            key=f"reason_{candidate.get('id')}",
                        )

                        if st.button(f"Save Review #{candidate.get('id')}", key=f"save_{candidate.get('id')}"):
                            payload = {
                                "review_status": new_status,
                                "review_reason": reason,
                            }
                            try:
                                fetch_json("POST", f"/api/v1/review/{candidate.get('id')}", json=payload)
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
            analytics = fetch_json("GET", "/api/v1/analytics")
            with col1:
                st.metric("Total Candidates", analytics.get("total_candidates", 0))
                st.metric("Avg Confidence Score", analytics.get("avg_confidence_score", 0.0))
                st.write("Review Status Breakdown")
                st.json(analytics.get("review_status_breakdown", {}))

            with col2:
                st.write("Top Roles")
                st.dataframe(pd.DataFrame(analytics.get("top_roles", []), columns=["role", "count"]))
                st.write("Top Skills")
                st.dataframe(pd.DataFrame(analytics.get("top_skills", []), columns=["skill", "count"]))
        except Exception as exc:
            st.error(f"Failed to load analytics: {exc}")

    st.divider()
    st.subheader("Export CSV")
    if st.button("Export Candidates CSV", use_container_width=True):
        try:
            response = requests.get(f"{API_BASE}/api/v1/export.csv", timeout=60)
            response.raise_for_status()
            st.download_button(
                "Download candidates.csv",
                data=response.text,
                file_name="candidates.csv",
                mime="text/csv",
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"Export failed: {exc}")