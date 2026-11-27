"""Tests for "Not handed in yet" on the teacher's Class Overview.

WHAT MATTERS HERE
  The student who built the app asked that teachers see "what students have
  done and what they have not done". A wrong list does harm either way: a
  student shown as missing after handing in gets chased for nothing, and one
  shown as done who did nothing slips through. So the tests pin down who is
  counted and what counts as handing in:

    * a student with no work for a set is listed; one with work is not
    * only the teacher's own sets count - not another teacher's, not the
      unowned sample sets, not archived ones, not students' own question sets
    * any attempt counts, whatever its status, and several count once
    * a mock exam paper that borrowed the set's questions is not the set
    * teachers are never listed, and only the students passed in are counted

  The last test drives the real page in demo mode. The sample sets there have
  no owner, so it checks the empty state first, then adds a set of the
  teacher's own and checks the list.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List

from streamlit.testing.v1 import AppTest

from models import Assessment, Question, Role, Submission, SubmissionStatus, User
from models.submission import MOCK_EXAM_SOURCE
from services.analytics_service import not_handed_in

APP = str(Path(__file__).resolve().parent.parent / "app.py")

TEACHER = "usr_t_a"
OTHER_TEACHER = "usr_t_b"
_NOW = datetime(2026, 11, 2, 9, 0)

S1 = User(id="usr_s01", display_name="S-1101", role=Role.STUDENT,
          teacher_id=TEACHER, year_group=10)
S2 = User(id="usr_s02", display_name="S-1102", role=Role.STUDENT,
          teacher_id=TEACHER, year_group=10)
S3 = User(id="usr_s03", display_name="S-1103", role=Role.STUDENT,
          teacher_id=TEACHER, year_group=9)
CLASS = [S1, S2, S3]


def _set(set_id: str, *, owner_id=TEACHER, weeks_ago: int = 0, **extra) -> Assessment:
    return Assessment(
        id=set_id,
        title=f"Homework {set_id}",
        grade_level=10,
        topic="Linear Equations",
        owner_id=owner_id,
        created_at=_NOW - timedelta(weeks=weeks_ago),
        questions=[
            Question(question_text="Solve 2x + 1 = 7.", model_answer="x = 3", max_marks=2)
        ],
        **extra,
    )


def _work(assessment: Assessment, student: User, **extra) -> Submission:
    return Submission(
        assessment_id=assessment.id,
        student_identifier=student.display_name,
        student_id=student.id,
        submission_text="2x = 6, so x = 3.",
        **extra,
    )


def _only(entries: List[dict]) -> dict:
    assert len(entries) == 1, entries
    return entries[0]


def _names(users: Iterable[User]) -> List[str]:
    return [u.display_name for u in users]


def _ids(entries: List[dict]) -> List[str]:
    return [e["assessment"].id for e in entries]


# --------------------------------------------------------------------------
# Who is missing
# --------------------------------------------------------------------------
def test_a_student_with_no_work_for_the_set_is_listed():
    homework = _set("as_hw1")

    # Passed in out of order: the list still comes back by display name.
    entry = _only(
        not_handed_in([homework], [S3, S2, S1], [_work(homework, S2)], teacher_id=TEACHER)
    )

    assert entry["assessment"].id == "as_hw1"
    assert _names(entry["missing"]) == ["S-1101", "S-1103"]
    assert (entry["handed_in"], entry["total"]) == (1, 3)


def test_work_for_a_different_set_does_not_count():
    first, second = _set("as_hw1", weeks_ago=1), _set("as_hw2")

    entries = not_handed_in([first, second], CLASS, [_work(first, S1)], teacher_id=TEACHER)
    by_id = {e["assessment"].id: e for e in entries}

    assert "S-1101" not in _names(by_id["as_hw1"]["missing"])
    assert "S-1101" in _names(by_id["as_hw2"]["missing"])


def test_the_newest_assessment_comes_first():
    """The page shows the first entry by default, so newest must lead."""
    sets = [_set("as_old", weeks_ago=4), _set("as_new"), _set("as_mid", weeks_ago=2)]

    assert _ids(not_handed_in(sets, CLASS, [], teacher_id=TEACHER)) == [
        "as_new", "as_mid", "as_old",
    ]


# --------------------------------------------------------------------------
# Which assessments count
# --------------------------------------------------------------------------
def test_only_the_teachers_own_assessments_count():
    sets = [
        _set("as_mine"),
        _set("as_theirs", owner_id=OTHER_TEACHER),
        _set("as_sample", owner_id=None),
        _set("as_students_own", owner_id=S1.id, student_created=True),
    ]

    assert _ids(not_handed_in(sets, CLASS, [], teacher_id=TEACHER)) == ["as_mine"]


def test_archived_assessments_are_left_out():
    sets = [_set("as_live"), _set("as_archived", is_archived=True)]

    assert _ids(not_handed_in(sets, CLASS, [], teacher_id=TEACHER)) == ["as_live"]


def test_without_a_teacher_the_sample_sets_are_nobodys():
    """An empty id must not match the unowned sets as somebody's own."""
    sample = _set("as_sample", owner_id=None)

    assert not_handed_in([sample], CLASS, [], teacher_id="") == []
    assert not_handed_in([sample], CLASS, [], teacher_id=None) == []


# --------------------------------------------------------------------------
# What counts as handing in
# --------------------------------------------------------------------------
def test_any_attempt_counts_and_several_attempts_count_once():
    homework = _set("as_hw1")
    work = [
        _work(homework, S1, attempt_number=1, status=SubmissionStatus.REVIEWED),
        _work(homework, S1, attempt_number=2, status=SubmissionStatus.GRADED),
        _work(homework, S1, attempt_number=3, status=SubmissionStatus.PENDING),
        # Handed in from My Work, which saves it as self-study.
        _work(homework, S2, is_self_study=True),
    ]

    entry = _only(not_handed_in([homework], CLASS, work, teacher_id=TEACHER))

    assert _names(entry["missing"]) == ["S-1103"]
    assert (entry["handed_in"], entry["total"]) == (2, 3)


def test_a_mock_exam_paper_is_not_handing_the_set_in():
    homework = _set("as_hw1")
    paper = _work(homework, S1, uploaded_filename=MOCK_EXAM_SOURCE, is_self_study=True)
    assert paper.is_mock_exam

    entry = _only(not_handed_in([homework], CLASS, [paper], teacher_id=TEACHER))

    assert "S-1101" in _names(entry["missing"])
    assert entry["handed_in"] == 0


# --------------------------------------------------------------------------
# Who is counted
# --------------------------------------------------------------------------
def test_teachers_are_never_listed():
    homework = _set("as_hw1")
    teacher = User(id=TEACHER, display_name="Ms Rao", role=Role.TEACHER)

    entry = _only(not_handed_in([homework], [teacher, *CLASS], [], teacher_id=TEACHER))

    assert "Ms Rao" not in _names(entry["missing"])
    assert entry["total"] == 3


def test_only_the_students_passed_in_are_counted():
    """A caller narrowing the list to one class gets that class's numbers."""
    homework = _set("as_hw1")

    entry = _only(
        not_handed_in([homework], [S1, S2], [_work(homework, S3)], teacher_id=TEACHER)
    )

    assert _names(entry["missing"]) == ["S-1101", "S-1102"]
    assert (entry["handed_in"], entry["total"]) == (0, 2)


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------
def _app_as(role: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, at.exception

    users = at.session_state["users"]
    wanted = next(u for u in users if u.role.value == role)
    at.session_state["current_user_id"] = wanted.id
    at.session_state["entered_demo"] = True
    at.run()
    assert not at.exception, at.exception
    return at


def test_the_class_overview_shows_who_has_not_handed_in():
    at = _app_as("teacher")
    teacher_id = at.session_state["current_user_id"]
    at.switch_page("views/dashboard.py").run()
    assert not at.exception, at.exception

    assert "## Not handed in yet" in [m.value for m in at.markdown]
    # The sample sets have no owner, so the demo teacher has none of their own.
    assert any("no assessments of your own" in i.value for i in at.info)

    # Set some homework, and have the first student on the roster hand it in.
    roster = sorted(
        (u for u in at.session_state["users"]
         if u.is_student and u.teacher_id == teacher_id),
        key=lambda u: (u.display_name.casefold(), u.id),
    )
    homework = Assessment(
        title="Simultaneous Equations - Homework 1",
        grade_level=10,
        topic="Simultaneous Equations",
        owner_id=teacher_id,
        questions=[
            Question(
                question_text="Solve x + y = 5 and x - y = 1.",
                model_answer="Adding the equations gives 2x = 6, so x = 3 and y = 2.",
                max_marks=2,
            )
        ],
    )
    at.session_state["assessments"] = [*at.session_state["assessments"], homework]
    at.session_state["submissions"] = [
        *at.session_state["submissions"],
        Submission(
            assessment_id=homework.id,
            student_identifier=roster[0].display_name,
            student_id=roster[0].id,
            submission_text="x = 3 and y = 2.",
            is_self_study=True,
        ),
    ]
    at.switch_page("views/dashboard.py").run()
    assert not at.exception, at.exception

    picker = next(s for s in at.selectbox if s.label == "Assessment")
    assert picker.value == homework.id
    assert f"**1 of {len(roster)}** handed in" in [m.value for m in at.markdown]

    # Display name and year group only - never an email or anything else.
    missing = next(
        d.value for d in at.dataframe if list(d.value.columns) == ["Student", "Year"]
    )
    assert missing["Student"].tolist() == [u.display_name for u in roster[1:]]
    assert missing["Year"].tolist() == [
        str(u.year_group) if u.year_group else "—" for u in roster[1:]
    ]
