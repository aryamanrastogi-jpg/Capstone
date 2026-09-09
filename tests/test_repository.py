"""Tests for the storage backends.

The session-state backend is already exercised all over the suite, because it is
what every other test runs on. What is new and untested is `SupabaseRepository`,
and it cannot be pointed at the real project: db/policies.sql grants to
`authenticated`, so an anonymous test run would be refused every row - and a
test that needs a signed-in user and a live network is not a unit test.

So this file drives it with `FakeSupabase`, an in-memory stand-in that answers
the same small slice of the PostgREST builder the repository actually uses. That
is enough to assert the things that would genuinely break:

  * parent and child rows both get written, and in the right shape
  * re-saving replaces children rather than accumulating duplicates
  * children are fetched in ONE batched query, not one per parent
  * a study camp's baseline is never rewritten by a re-save

What it deliberately does NOT prove is that the SQL is right - that the policies
permit what they should. That needs a signed-in integration test against a real
project, and is noted in db/README.md as outstanding.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

import pytest

from models import (
    Assessment,
    GradingResult,
    Question,
    ReviewStatus,
    Role,
    StudyCamp,
    StudySession,
    Submission,
    SubmissionStatus,
    User,
)
from services.repository import SessionRepository, SupabaseRepository


# --------------------------------------------------------------------------
# A minimal in-memory stand-in for the Supabase client
# --------------------------------------------------------------------------
class _Response:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class _Query:
    """One PostgREST request being built up."""

    def __init__(self, db: "FakeSupabase", table: str) -> None:
        self._db = db
        self._table = table
        self._filters: List[Any] = []
        self._op = "select"
        self._payload: Any = None

    # --- builder ---
    def select(self, *_columns: str) -> "_Query":
        self._op = "select"
        self._db.select_calls.append(self._table)
        return self

    def insert(self, payload: Any) -> "_Query":
        self._op = "insert"
        self._payload = payload
        return self

    def upsert(self, payload: Any) -> "_Query":
        self._op = "upsert"
        self._payload = payload
        return self

    def update(self, payload: Dict[str, Any]) -> "_Query":
        self._op = "update"
        self._payload = payload
        return self

    def delete(self) -> "_Query":
        self._op = "delete"
        return self

    def eq(self, column: str, value: Any) -> "_Query":
        self._filters.append(lambda row: row.get(column) == value)
        return self

    def in_(self, column: str, values: List[Any]) -> "_Query":
        self._filters.append(lambda row: row.get(column) in set(values))
        return self

    def limit(self, _n: int) -> "_Query":
        return self

    # --- execution ---
    def _matches(self, row: Dict[str, Any]) -> bool:
        return all(f(row) for f in self._filters)

    def execute(self) -> _Response:
        rows = self._db.tables.setdefault(self._table, [])

        if self._op == "select":
            return _Response([dict(r) for r in rows if self._matches(r)])

        if self._op in ("insert", "upsert"):
            incoming = (
                self._payload if isinstance(self._payload, list) else [self._payload]
            )
            keys = self._db.primary_keys[self._table]
            for new_row in incoming:
                identity = tuple(new_row.get(k) for k in keys)
                for index, existing in enumerate(rows):
                    if tuple(existing.get(k) for k in keys) == identity:
                        if self._op == "insert":
                            raise AssertionError(
                                f"duplicate key in {self._table}: {identity}"
                            )
                        rows[index] = dict(new_row)
                        break
                else:
                    rows.append(dict(new_row))
            return _Response([dict(r) for r in incoming])

        if self._op == "update":
            touched = []
            for row in rows:
                if self._matches(row):
                    row.update(self._payload)
                    touched.append(dict(row))
            return _Response(touched)

        if self._op == "delete":
            removed = [dict(r) for r in rows if self._matches(r)]
            self._db.tables[self._table] = [r for r in rows if not self._matches(r)]
            return _Response(removed)

        raise AssertionError(f"unsupported operation {self._op}")


class FakeSupabase:
    """Just enough PostgREST to run the repository against."""

    primary_keys = {
        "profiles": ("id",),
        "assessments": ("id",),
        "questions": ("id",),
        "submissions": ("id",),
        "submission_answers": ("submission_id", "question_id"),
        "grading_results": ("submission_id", "question_id"),
        "study_camps": ("id",),
        "study_sessions": ("camp_id", "day"),
    }

    def __init__(self) -> None:
        self.tables: Dict[str, List[Dict[str, Any]]] = {
            name: [] for name in self.primary_keys
        }
        # Every select, in order, so a test can assert on round trips.
        self.select_calls: List[str] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)


@pytest.fixture()
def db() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture()
def repo(db: FakeSupabase) -> SupabaseRepository:
    return SupabaseRepository(db)


def _assessment(assessment_id: str = "as_1", **kwargs: Any) -> Assessment:
    """A two-question assessment.

    Question ids are derived from the assessment id because `questions.id` is a
    primary key across the whole table, not per assessment. Reusing "q_1" for
    two different assessments is a collision the database would refuse, and
    FakeSupabase refuses it too.
    """
    defaults: Dict[str, Any] = dict(
        id=assessment_id,
        title="Linear Equations",
        grade_level=10,
        topic="Algebra",
        questions=[
            Question(id=f"q_{assessment_id}_1", question_text="Solve 2x = 8",
                     model_answer="x = 4", max_marks=2),
            Question(id=f"q_{assessment_id}_2", question_text="Solve x + 1 = 4",
                     model_answer="x = 3", max_marks=3),
        ],
    )
    defaults.update(kwargs)
    return Assessment(**defaults)


def _submission(submission_id: str = "sub_1", **kwargs: Any) -> Submission:
    defaults: Dict[str, Any] = dict(
        id=submission_id,
        assessment_id="as_1",
        student_identifier="S-1101",
        submission_text="Q1. x = 4",
        answers={"q_1": "x = 4", "q_2": ""},
        student_id="usr_s01",
    )
    defaults.update(kwargs)
    return Submission(**defaults)


# --------------------------------------------------------------------------
# Assessments
# --------------------------------------------------------------------------
def test_saving_an_assessment_writes_parent_and_question_rows(
    repo: SupabaseRepository, db: FakeSupabase
) -> None:
    repo.save_assessment(_assessment())

    assert len(db.tables["assessments"]) == 1
    assert len(db.tables["questions"]) == 2
    assert {q["assessment_id"] for q in db.tables["questions"]} == {"as_1"}
    assert sorted(q["position"] for q in db.tables["questions"]) == [0, 1]


def test_assessment_round_trips_through_the_backend(
    repo: SupabaseRepository,
) -> None:
    repo.save_assessment(_assessment())

    restored = repo.get_assessment("as_1")

    assert restored is not None
    assert restored.title == "Linear Equations"
    assert [q.id for q in restored.questions] == ["q_as_1_1", "q_as_1_2"]
    assert restored.max_marks == 5
    assert restored.is_gradable is True


def test_resaving_replaces_questions_rather_than_duplicating_them(
    repo: SupabaseRepository, db: FakeSupabase
) -> None:
    """The bug this guards against: edit a set, get every question twice."""
    repo.save_assessment(_assessment())

    edited = _assessment(
        questions=[
            Question(id="q_as_1_1", question_text="Solve 2x = 10", model_answer="x = 5",
                     max_marks=2),
        ]
    )
    repo.save_assessment(edited)

    assert len(db.tables["questions"]) == 1
    restored = repo.get_assessment("as_1")
    assert restored is not None
    assert restored.question_count == 1
    assert restored.questions[0].question_text == "Solve 2x = 10"


def test_missing_assessment_is_none_not_an_error(repo: SupabaseRepository) -> None:
    assert repo.get_assessment("as_nope") is None


def test_delete_reports_whether_anything_was_removed(
    repo: SupabaseRepository,
) -> None:
    repo.save_assessment(_assessment())

    assert repo.delete_assessment("as_1") is True
    assert repo.delete_assessment("as_1") is False


def test_listing_fetches_questions_in_one_batched_query(
    repo: SupabaseRepository, db: FakeSupabase
) -> None:
    """A query per assessment would make a term of history unusable."""
    for index in range(5):
        repo.save_assessment(_assessment(f"as_{index}"))
    db.select_calls.clear()

    repo.list_assessments()

    assert db.select_calls.count("assessments") == 1
    assert db.select_calls.count("questions") == 1


# --------------------------------------------------------------------------
# Submissions
# --------------------------------------------------------------------------
def test_submission_round_trips_with_its_answers(repo: SupabaseRepository) -> None:
    repo.save_submission(_submission())

    restored = repo.get_submission("sub_1")

    assert restored is not None
    assert restored.answers == {"q_1": "x = 4", "q_2": ""}
    assert restored.answer_for("q_2") == ""
    assert restored.answer_for("q_3") == ""


def test_submissions_can_be_scoped_to_one_student(repo: SupabaseRepository) -> None:
    repo.save_submission(_submission("sub_1", student_id="usr_s01"))
    repo.save_submission(_submission("sub_2", student_id="usr_s02"))

    mine = repo.list_submissions(student_id="usr_s01")

    assert [s.id for s in mine] == ["sub_1"]


def test_status_change_is_written_to_the_row(
    repo: SupabaseRepository, db: FakeSupabase
) -> None:
    """Assigning to the model would not have updated the column."""
    repo.save_submission(_submission())

    repo.set_submission_status("sub_1", SubmissionStatus.REVIEWED)

    assert db.tables["submissions"][0]["status"] == "reviewed"
    restored = repo.get_submission("sub_1")
    assert restored is not None
    assert restored.status is SubmissionStatus.REVIEWED


def test_resaving_a_submission_replaces_its_answers(
    repo: SupabaseRepository, db: FakeSupabase
) -> None:
    repo.save_submission(_submission())
    repo.save_submission(_submission(answers={"q_1": "x = 4"}))

    assert len(db.tables["submission_answers"]) == 1


# --------------------------------------------------------------------------
# Grading
# --------------------------------------------------------------------------
def test_regrading_updates_the_existing_row(
    repo: SupabaseRepository, db: FakeSupabase
) -> None:
    """(submission_id, question_id) is the key, so a re-grade is an upsert."""
    first = GradingResult(
        submission_id="sub_1", question_id="q_1", max_marks=2,
        suggested_score=1, confidence=0.5,
    )
    repo.save_grading_result(first)

    approved = GradingResult(
        submission_id="sub_1", question_id="q_1", max_marks=2,
        suggested_score=1, confidence=0.5,
        review_status=ReviewStatus.APPROVED,
    )
    repo.save_grading_result(approved)

    assert len(db.tables["grading_results"]) == 1
    stored = repo.list_grading_results("sub_1")
    assert len(stored) == 1
    assert stored[0].review_status is ReviewStatus.APPROVED
    assert stored[0].final_score == 1


def test_grading_results_scope_to_one_submission(repo: SupabaseRepository) -> None:
    repo.save_grading_result(
        GradingResult(submission_id="sub_1", question_id="q_1", max_marks=2,
                      suggested_score=1, confidence=0.5)
    )
    repo.save_grading_result(
        GradingResult(submission_id="sub_2", question_id="q_1", max_marks=2,
                      suggested_score=2, confidence=0.9)
    )

    assert len(repo.list_grading_results("sub_1")) == 1
    assert len(repo.list_grading_results()) == 2


# --------------------------------------------------------------------------
# Study camps
# --------------------------------------------------------------------------
def _camp(**kwargs: Any) -> StudyCamp:
    defaults: Dict[str, Any] = dict(
        id="camp_1",
        student_id="usr_s01",
        topics=["Algebra"],
        started_on=date(2026, 4, 1),
        duration_days=2,
        baseline_percentage=60,
        sessions=[
            StudySession(day=1, topic="Algebra", questions=["a", "b"]),
            StudySession(day=2, topic="Algebra", questions=["c"]),
        ],
    )
    defaults.update(kwargs)
    return StudyCamp(**defaults)


def test_study_camp_round_trips_with_its_sessions(repo: SupabaseRepository) -> None:
    repo.save_study_camp(_camp())

    camps = repo.list_study_camps("usr_s01")

    assert len(camps) == 1
    assert [s.day for s in camps[0].sessions] == [1, 2]
    assert camps[0].baseline_percentage == 60


def test_progress_is_saved_without_rewriting_the_baseline(
    repo: SupabaseRepository, db: FakeSupabase
) -> None:
    """The camp row is written once. There is no UPDATE policy on it by design.

    A re-save carries progress on the sessions; if it also re-wrote the camp
    row, the baseline could drift and "60% -> 90%" would stop meaning anything.
    """
    repo.save_study_camp(_camp())

    progressed = _camp(
        baseline_percentage=95,  # a caller getting this wrong must not win
        sessions=[
            StudySession(day=1, topic="Algebra", questions=["a", "b"],
                         completed=True, score=2),
            StudySession(day=2, topic="Algebra", questions=["c"]),
        ],
    )
    repo.save_study_camp(progressed)

    assert len(db.tables["study_camps"]) == 1
    assert float(db.tables["study_camps"][0]["baseline_percentage"]) == 60

    stored = repo.list_study_camps("usr_s01")[0]
    assert stored.baseline_percentage == 60
    assert stored.sessions[0].completed is True
    assert stored.sessions[0].score == 2


def test_deleting_a_camp_reports_whether_it_existed(
    repo: SupabaseRepository,
) -> None:
    repo.save_study_camp(_camp())

    assert repo.delete_study_camp("camp_1") is True
    assert repo.delete_study_camp("camp_1") is False


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
def test_saving_a_user_never_writes_the_role(
    repo: SupabaseRepository, db: FakeSupabase
) -> None:
    """Promotion to teacher is not something the app can perform.

    db/policies.sql grants UPDATE on (display_name, year_group) only, so a save
    that included `role` would be rejected outright. The repository narrows the
    write to what is permitted, and this asserts it stays narrow.
    """
    db.tables["profiles"].append(
        {"id": "usr_s01", "display_name": "S-1101", "role": "student",
         "teacher_id": "usr_t1", "year_group": 10}
    )

    repo.save_user(
        User(id="usr_s01", display_name="S-9999", role=Role.TEACHER,
             year_group=11)
    )

    stored = db.tables["profiles"][0]
    assert stored["display_name"] == "S-9999"
    assert stored["year_group"] == 11
    assert stored["role"] == "student"


# --------------------------------------------------------------------------
# Backend selection
# --------------------------------------------------------------------------
def test_both_backends_satisfy_the_same_interface() -> None:
    """Anything the service calls has to exist on both, or demo mode breaks."""
    session_repo = SessionRepository()
    supabase_repo = SupabaseRepository(FakeSupabase())

    for name in (
        "list_assessments", "get_assessment", "save_assessment",
        "delete_assessment", "list_submissions", "get_submission",
        "save_submission", "set_submission_status", "list_grading_results",
        "save_grading_result", "list_users", "save_user", "list_study_camps",
        "save_study_camp", "delete_study_camp",
    ):
        assert callable(getattr(session_repo, name))
        assert callable(getattr(supabase_repo, name))


def test_repository_falls_back_to_session_state_when_signed_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credentials alone must not switch the backend.

    Every policy grants to `authenticated`. A Supabase repository with no signed
    in user would read nothing and silently discard every write - worse than
    demo mode, and far harder to diagnose.
    """
    import services.repository as repository_module
    import services.supabase_client as client_module

    monkeypatch.setattr(client_module, "get_authenticated_client", lambda: None)
    repository_module.set_repository(None)
    try:
        assert isinstance(repository_module.get_repository(), SessionRepository)
    finally:
        repository_module.set_repository(None)


def test_repository_uses_supabase_when_a_session_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.repository as repository_module
    import services.supabase_client as client_module

    fake = FakeSupabase()
    monkeypatch.setattr(client_module, "get_authenticated_client", lambda: fake)
    repository_module.set_repository(None)
    try:
        active = repository_module.get_repository()
        assert isinstance(active, SupabaseRepository)
    finally:
        repository_module.set_repository(None)
