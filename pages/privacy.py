"""Read-only privacy details shown to visitors and signed-in users."""

from __future__ import annotations

import streamlit as st

from components.layout import page_header
from utils.config import PRIVACY_DETAILS

page_header(
    "Privacy",
    "What Camp Prep AI stores and how it is used.",
    "This is the same privacy information shown beside the sign-in form.",
)

for detail in PRIVACY_DETAILS:
    st.markdown(detail)
