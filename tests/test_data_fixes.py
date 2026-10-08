"""Data-layer fixes: grading_results read grants, avatar URLs, analytics scope.

  * Migration 008 and db/policies.sql must leave column-level SELECT on
    grading_results: upserts need to read the key columns, but the teacher-only
    columns must stay ungranted.
  * A profile photo URL is only trusted inside this project's avatars bucket.
  * Class Analytics counts teacher-marked work only, like the review queue.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")

UPSERT_KEYS = ("submission_id", "question_id")
TEACHER_ONLY = ("teacher_note", "errors", "correct_elements")


def _grading_results_select_grant(sql: str) -> list[str]:
    text = re.sub(r"--[^\n]*", "", sql)
    match = re.search(
        r"grant\s+select\s*\(([^)]*)\)\s*on\s+public\.grading_results\s+to\s+authenticated",
        text,
        re.IGNORECASE,
    )
    assert match, "grading_results needs a column-level SELECT grant"
    return [c.strip() for c in match.group(1).split(",")]


@pytest.mark.parametrize(
    "path", ["db/migrations/008_qa_hardening.sql", "db/policies.sql"]
)
def test_grading_results_keeps_column_reads_for_upserts(path):
    columns = _grading_results_select_grant((ROOT / path).read_text())
    for key in UPSERT_KEYS:
        assert key in columns
    for hidden in TEACHER_ONLY:
        assert hidden not in columns


def test_migration_and_policies_grant_the_same_columns():
    migration = (ROOT / "db/migrations/008_qa_hardening.sql").read_text()
    policies = (ROOT / "db/policies.sql").read_text()
    assert _grading_results_select_grant(migration) == _grading_results_select_grant(
        policies
    )


@pytest.fixture
def project_url(monkeypatch):
    from utils.config import get_settings

    monkeypatch.setenv("SUPABASE_URL", "https://abc123.supabase.co")
    get_settings.cache_clear()
    yield "https://abc123.supabase.co"
    get_settings.cache_clear()


def test_avatar_inside_the_project_bucket_is_kept(project_url):
    from services.mappers import safe_avatar_url

    url = f"{project_url}/storage/v1/object/public/avatars/u1/avatar.png?v=1"
    assert safe_avatar_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://tracker.example.com/pixel.png",
        "https://abc123.supabase.co.evil.com/storage/v1/object/public/avatars/x.png",
        "https://other.supabase.co/storage/v1/object/public/avatars/x.png",
        "https://abc123.supabase.co/storage/v1/object/public/other-bucket/x.png",
        "",
        None,
    ],
)
def test_avatar_outside_the_project_bucket_is_dropped(project_url, url):
    from services.mappers import safe_avatar_url

    assert safe_avatar_url(url) is None


def test_profile_rows_go_through_the_avatar_check(project_url):
    from services.mappers import user_from_row

    user = user_from_row(
        {
            "id": "p1",
            "display_name": "Sam",
            "role": "student",
            "avatar_url": "https://tracker.example.com/pixel.png",
        }
    )
    assert user.avatar_url is None


def _teacher_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    teacher = next(u for u in at.session_state["users"] if u.role.value == "teacher")
    at.session_state["current_user_id"] = teacher.id
    at.session_state["entered_demo"] = True
    at.run()
    assert not at.exception, at.exception
    return at


def _analytics_awaiting(at: AppTest) -> int:
    at.switch_page("pages/analytics.py")
    at.run()
    assert not at.exception, at.exception
    return int(next(m for m in at.metric if m.label == "Results awaiting review").value)


def test_class_analytics_leaves_out_self_study_results():
    at = _teacher_app()
    before = _analytics_awaiting(at)

    submissions = at.session_state["submissions"]
    results = at.session_state["grading_results"]
    pending = {r.submission_id for r in results if not r.is_reviewed}
    index = next(i for i, s in enumerate(submissions) if s.id in pending)
    pending_here = sum(
        1 for r in results if r.submission_id == submissions[index].id and not r.is_reviewed
    )
    submissions[index] = submissions[index].model_copy(update={"is_self_study": True})
    at.session_state["submissions"] = submissions

    assert _analytics_awaiting(at) == before - pending_here
