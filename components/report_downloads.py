"""The "Download results" block shared by Review Grading and Class Analytics.

One renderer so both pages state the same exclusion rule in the same words;
what goes into the files is decided in services/report_service.py.
"""

from __future__ import annotations

from typing import Sequence

import streamlit as st

from models import Assessment, GradingResult, Submission
from services import report_service as reports


def report_downloads(
    results: Sequence[GradingResult],
    assessments: Sequence[Assessment],
    submissions: Sequence[Submission],
    key_prefix: str,
) -> None:
    """CSV and PDF buttons for the teacher-settled results the caller can see."""
    st.subheader("Download results")
    report = reports.build_report(results, assessments, submissions)
    st.caption(
        f"{reports.OFFICIAL_NOTE} Currently excluded: {report.awaiting_excluded} "
        f"awaiting review, {report.flagged_excluded} flagged."
    )
    if report.is_empty:
        st.info(
            "No approved or edited results yet, so there is nothing to download.",
            icon=":material/info:",
        )
        return

    csv_col, pdf_col = st.columns(2)
    csv_col.download_button(
        "Download CSV",
        data=reports.to_csv(report),
        file_name="assessai_results.csv",
        mime="text/csv",
        icon=":material/table_view:",
        width="stretch",
        key=f"{key_prefix}_report_csv",
    )
    pdf = reports.to_pdf(report)
    if pdf is None:
        pdf_col.caption("PDF export needs PyMuPDF installed.")
        return
    pdf_col.download_button(
        "Download PDF",
        data=pdf,
        file_name="assessai_results.pdf",
        mime="application/pdf",
        icon=":material/picture_as_pdf:",
        width="stretch",
        key=f"{key_prefix}_report_pdf",
    )
