"""Start a question set from a file instead of typing it.

Shared by My Questions and Create Assessment. Upload a worksheet, past paper
or Google Doc (downloaded as .docx or PDF); the questions are read out of it
(services/question_import.py) and previewed; one click puts them in the page's
question table, where they are checked and saved as usual.

The page owns its table. This panel hands it the rows through `apply`, a
callback the page writes, and never saves anything itself.
"""

from __future__ import annotations

import zlib
from typing import Any, Callable, Dict, List

import streamlit as st

from services import document_service, llm_service
from services import question_import as importer
from utils.config import ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_BYTES

ApplyRows = Callable[[List[Dict[str, Any]], str], None]

PREVIEW_LIMIT = 12
# The raw text is shown for reference only; a very long file is cut here so
# it is not re-sent to the browser in full on every rerun.
TEXT_VIEW_LIMIT = 20_000


def _keys(key: str) -> Dict[str, str]:
    return {
        name: f"{key}_{name}"
        for name in ("file", "file_id", "text", "filename", "error", "ai", "note", "plain")
    }


def import_panel(*, key: str, apply: ApplyRows, teacher: bool) -> None:
    """Upload, read, preview, and put the questions in the page's table."""
    keys = _keys(key)
    allowed = sorted(ext.lstrip(".") for ext in ALLOWED_UPLOAD_EXTENSIONS)
    st.caption(
        f"Allowed: {', '.join(allowed)} (a Google Doc can be downloaded as .docx or "
        f"PDF). Max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. Photos and scans of "
        "printed pages are not readable yet."
    )
    uploaded = st.file_uploader("Your question paper", type=allowed, key=keys["file"])
    _read_new_upload(uploaded, keys)

    if st.session_state.get(keys["error"]):
        st.error(st.session_state[keys["error"]], icon=":material/error:")
    text = st.session_state.get(keys["text"])
    if not text:
        return

    note = st.session_state.pop(keys["note"], None)
    if note:
        st.success(note, icon=":material/check_circle:")

    result = st.session_state.get(keys["ai"]) or _plain_reading(keys, text)
    if not result.found:
        st.warning(result.message, icon=":material/info:")
    else:
        st.info(result.message, icon=":material/description:")
        shown = result.questions[:PREVIEW_LIMIT]
        st.text(importer.summarise(shown))
        if len(result.questions) > len(shown):
            st.caption(f"...and {len(result.questions) - len(shown)} more.")
        if teacher and result.answers_found_count < len(result.questions):
            st.caption(
                "Every question needs a model answer before it can be marked - add "
                "the ones the file did not have in the table."
            )
        count = len(result.questions)
        st.button(
            f"Put {'this question' if count == 1 else f'these {count} questions'} in the table",
            key=f"{key}_apply",
            type="primary",
            on_click=_apply,
            args=(keys, result, apply),
        )

    if result.method == importer.METHOD_AI:
        st.button(
            "Use the plain reading instead",
            key=f"{key}_plain",
            on_click=st.session_state.pop,
            args=(keys["ai"], None),
        )
    elif llm_service.ai_enabled():
        st.button(
            "Not split right? Let the AI find the questions",
            key=f"{key}_ask_ai",
            on_click=_read_with_ai,
            args=(keys, text),
        )
        st.caption(
            "This sends the file's text (never your name or email) to Google's "
            "Gemini. It only copies what is in the file - nothing is made up."
        )

    with st.expander("The text that was read from the file"):
        # Keyed to this text: a fixed key would keep showing the first file
        # after a second one is uploaded.
        st.text_area(
            "Text from the file",
            value=text[:TEXT_VIEW_LIMIT],
            height=200,
            disabled=True,
            key=f"{key}_text_view_{zlib.crc32(text.encode('utf-8')):08x}",
        )
        if len(text) > TEXT_VIEW_LIMIT:
            st.caption(f"Only the first {TEXT_VIEW_LIMIT:,} characters are shown here.")


def _plain_reading(keys: Dict[str, str], text: str) -> importer.QuestionImport:
    """The file's questions, read once per file rather than on every rerun."""
    cached = st.session_state.get(keys["plain"])
    if cached is not None and cached[0] == text:
        return cached[1]
    result = importer.import_questions(text)
    st.session_state[keys["plain"]] = (text, result)
    return result


def _read_new_upload(uploaded, keys: Dict[str, str]) -> None:
    if uploaded is None:
        # The file was removed: forget what was read from it. (Text put here
        # without an upload - by a test - has no file id and is kept.)
        if st.session_state.get(keys["file_id"]):
            for name in ("file_id", "text", "filename", "error", "ai", "plain"):
                st.session_state.pop(keys[name], None)
        return
    file_id = getattr(uploaded, "file_id", None) or uploaded.name
    if st.session_state.get(keys["file_id"]) == file_id:
        return  # already read; reruns do not read it again
    st.session_state[keys["file_id"]] = file_id
    for name in ("text", "filename", "error", "ai", "plain"):
        st.session_state.pop(keys[name], None)
    extraction = document_service.read_uploaded_file(uploaded)
    if extraction.success:
        st.session_state[keys["text"]] = extraction.text
        st.session_state[keys["filename"]] = extraction.filename
    else:
        st.session_state[keys["error"]] = extraction.message


def _apply(keys: Dict[str, str], result: importer.QuestionImport, apply: ApplyRows) -> None:
    title = importer.suggested_title(st.session_state.get(keys["filename"], ""))
    apply(result.editor_rows(), title)
    st.session_state.pop(keys["error"], None)
    count = len(result.questions)
    st.session_state[keys["note"]] = (
        f"Put {count} question{'s' if count != 1 else ''} in the table below. "
        "Check them, then save."
    )


def _read_with_ai(keys: Dict[str, str], text: str) -> None:
    result = importer.ai_import_questions(text)
    if result is None:
        st.session_state[keys["error"]] = (
            "The AI could not read the file just now (it may be busy). The plain "
            "reading is still below - try the AI again in a minute."
        )
        return
    st.session_state.pop(keys["error"], None)
    if result.found:
        st.session_state[keys["ai"]] = result
    else:
        st.session_state[keys["error"]] = result.message
