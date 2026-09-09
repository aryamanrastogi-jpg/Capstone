"""Storage backends.

WHAT THIS IS
  One interface, two implementations. `SessionRepository` keeps everything in
  Streamlit session state, which is what demo mode has always done.
  `SupabaseRepository` puts the same objects in Postgres.

  `assessment_service` talks to whichever one `get_repository()` returns and
  cannot tell the difference. That is the whole point: the pages, the analytics
  and the grading code never learn where the data lives.

WHY THE INTERFACE IS SHAPED LIKE SESSION STATE AND NOT LIKE SQL
  It would be tempting to expose something richer here - filters, joins, paging
  - now that a real database is underneath. That would leak SQL thinking into
  every caller and make the session-state backend impossible to keep honest.
  So the interface stays deliberately small and list-shaped, and the Supabase
  implementation does the work of making that efficient.

ON SCOPING
  Every method that returns a student's data takes a `student_id` and filters on
  it. That filtering is real work in the session backend and belt-and-braces in
  the Supabase one, where db/policies.sql would refuse the rows anyway. Both are
  kept: the Python filter is what protects demo mode, and the policy is what
  protects everything else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from models import (
    Assessment,
    GradingResult,
    StudyCamp,
    Submission,
    SubmissionStatus,
    User,
)
from services import mappers
from services import state as store


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------
class Repository(ABC):
    """Everything the application needs to store and retrieve."""

    # --- Assessments ---
    @abstractmethod
    def list_assessments(self) -> List[Assessment]: ...

    @abstractmethod
    def get_assessment(self, assessment_id: str) -> Optional[Assessment]: ...

    @abstractmethod
    def save_assessment(self, assessment: Assessment) -> Assessment: ...

    @abstractmethod
    def delete_assessment(self, assessment_id: str) -> bool: ...

    # --- Submissions ---
    @abstractmethod
    def list_submissions(
        self,
        assessment_id: Optional[str] = None,
        student_id: Optional[str] = None,
    ) -> List[Submission]: ...

    @abstractmethod
    def get_submission(self, submission_id: str) -> Optional[Submission]: ...

    @abstractmethod
    def save_submission(self, submission: Submission) -> Submission: ...

    @abstractmethod
    def set_submission_status(
        self, submission_id: str, status: SubmissionStatus
    ) -> None: ...

    # --- Grading ---
    @abstractmethod
    def list_grading_results(
        self, submission_id: Optional[str] = None
    ) -> List[GradingResult]: ...

    @abstractmethod
    def save_grading_result(self, result: GradingResult) -> GradingResult: ...

    # --- Users ---
    @abstractmethod
    def list_users(self) -> List[User]: ...

    @abstractmethod
    def save_user(self, user: User) -> User: ...

    # --- Study camps ---
    @abstractmethod
    def list_study_camps(self, student_id: Optional[str] = None) -> List[StudyCamp]: ...

    @abstractmethod
    def save_study_camp(self, camp: StudyCamp) -> StudyCamp: ...

    @abstractmethod
    def delete_study_camp(self, camp_id: str) -> bool: ...


# --------------------------------------------------------------------------
# Session state backend (demo mode)
# --------------------------------------------------------------------------
class SessionRepository(Repository):
    """The original store: Python lists living in st.session_state.

    Objects are held by reference, so a caller mutating a returned model is
    mutating the store. That has always been true here and several pages rely on
    it. `SupabaseRepository` deliberately does NOT behave that way, which is why
    `assessment_service` now saves explicitly after every mutation rather than
    trusting the reference.
    """

    def list_assessments(self) -> List[Assessment]:
        return list(store.get_assessments())

    def get_assessment(self, assessment_id: str) -> Optional[Assessment]:
        return next(
            (a for a in store.get_assessments() if a.id == assessment_id), None
        )

    def save_assessment(self, assessment: Assessment) -> Assessment:
        assessments = store.get_assessments()
        for index, existing in enumerate(assessments):
            if existing.id == assessment.id:
                assessments[index] = assessment
                return assessment
        assessments.append(assessment)
        return assessment

    def delete_assessment(self, assessment_id: str) -> bool:
        assessments = store.get_assessments()
        for index, existing in enumerate(assessments):
            if existing.id == assessment_id:
                assessments.pop(index)
                return True
        return False

    def list_submissions(
        self,
        assessment_id: Optional[str] = None,
        student_id: Optional[str] = None,
    ) -> List[Submission]:
        subs = list(store.get_submissions())
        if assessment_id:
            subs = [s for s in subs if s.assessment_id == assessment_id]
        if student_id:
            subs = [s for s in subs if s.student_id == student_id]
        return subs

    def get_submission(self, submission_id: str) -> Optional[Submission]:
        return next(
            (s for s in store.get_submissions() if s.id == submission_id), None
        )

    def save_submission(self, submission: Submission) -> Submission:
        submissions = store.get_submissions()
        for index, existing in enumerate(submissions):
            if existing.id == submission.id:
                submissions[index] = submission
                return submission
        submissions.append(submission)
        return submission

    def set_submission_status(
        self, submission_id: str, status: SubmissionStatus
    ) -> None:
        submission = self.get_submission(submission_id)
        if submission is not None:
            submission.status = status

    def list_grading_results(
        self, submission_id: Optional[str] = None
    ) -> List[GradingResult]:
        results = list(store.get_grading_results())
        if submission_id:
            results = [r for r in results if r.submission_id == submission_id]
        return results

    def save_grading_result(self, result: GradingResult) -> GradingResult:
        results = store.get_grading_results()
        for index, existing in enumerate(results):
            if (
                existing.submission_id == result.submission_id
                and existing.question_id == result.question_id
            ):
                results[index] = result
                return result
        results.append(result)
        return result

    def list_users(self) -> List[User]:
        return list(store.get_users())

    def save_user(self, user: User) -> User:
        users = store.get_users()
        for index, existing in enumerate(users):
            if existing.id == user.id:
                users[index] = user
                return user
        users.append(user)
        return user

    def list_study_camps(self, student_id: Optional[str] = None) -> List[StudyCamp]:
        camps = list(store.get_study_camps())
        if student_id:
            camps = [c for c in camps if c.student_id == student_id]
        return camps

    def save_study_camp(self, camp: StudyCamp) -> StudyCamp:
        camps = store.get_study_camps()
        for index, existing in enumerate(camps):
            if existing.id == camp.id:
                camps[index] = camp
                return camp
        camps.append(camp)
        return camp

    def delete_study_camp(self, camp_id: str) -> bool:
        camps = store.get_study_camps()
        for index, existing in enumerate(camps):
            if existing.id == camp_id:
                camps.pop(index)
                return True
        return False


# --------------------------------------------------------------------------
# Supabase backend
# --------------------------------------------------------------------------
class SupabaseRepository(Repository):
    """Postgres via PostgREST.

    TWO THINGS TO KNOW WHEN READING THIS

    1. Parent and child rows are written in two steps - the assessment then its
       questions, the camp then its sessions. PostgREST has no transaction
       across requests, so a save that fails halfway leaves the parent without
       its children. Children are therefore deleted-then-inserted rather than
       merged, so a retry converges instead of accumulating duplicates.

    2. Children are fetched with one `in_` query for the whole batch rather than
       one query per parent. Listing a term of submissions is otherwise a
       hundred round trips.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    # --- small helpers -------------------------------------------------
    def _rows(self, table: str) -> List[Dict[str, Any]]:
        return self._client.table(table).select("*").execute().data or []

    def _children(
        self, table: str, key: str, parent_ids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """All child rows for a batch of parents, grouped by parent id."""
        grouped: Dict[str, List[Dict[str, Any]]] = {pid: [] for pid in parent_ids}
        if not parent_ids:
            return grouped
        response = (
            self._client.table(table).select("*").in_(key, parent_ids).execute()
        )
        for row in response.data or []:
            grouped.setdefault(row[key], []).append(row)
        return grouped

    def _replace_children(
        self, table: str, key: str, parent_id: str, rows: List[Dict[str, Any]]
    ) -> None:
        self._client.table(table).delete().eq(key, parent_id).execute()
        if rows:
            self._client.table(table).insert(rows).execute()

    # --- Assessments ---------------------------------------------------
    def list_assessments(self) -> List[Assessment]:
        rows = self._rows("assessments")
        questions = self._children(
            "questions", "assessment_id", [r["id"] for r in rows]
        )
        return [
            mappers.assessment_from_rows(row, questions.get(row["id"], []))
            for row in rows
        ]

    def get_assessment(self, assessment_id: str) -> Optional[Assessment]:
        rows = (
            self._client.table("assessments")
            .select("*")
            .eq("id", assessment_id)
            .execute()
            .data
            or []
        )
        if not rows:
            return None
        questions = (
            self._client.table("questions")
            .select("*")
            .eq("assessment_id", assessment_id)
            .execute()
            .data
            or []
        )
        return mappers.assessment_from_rows(rows[0], questions)

    def save_assessment(self, assessment: Assessment) -> Assessment:
        row, question_rows = mappers.assessment_to_rows(assessment)
        self._client.table("assessments").upsert(row).execute()
        self._replace_children(
            "questions", "assessment_id", assessment.id, question_rows
        )
        return assessment

    def delete_assessment(self, assessment_id: str) -> bool:
        # Questions go with it: the foreign key is ON DELETE CASCADE.
        response = (
            self._client.table("assessments")
            .delete()
            .eq("id", assessment_id)
            .execute()
        )
        return bool(response.data)

    # --- Submissions ---------------------------------------------------
    def list_submissions(
        self,
        assessment_id: Optional[str] = None,
        student_id: Optional[str] = None,
    ) -> List[Submission]:
        query = self._client.table("submissions").select("*")
        if assessment_id:
            query = query.eq("assessment_id", assessment_id)
        if student_id:
            query = query.eq("student_id", student_id)
        rows = query.execute().data or []
        answers = self._children(
            "submission_answers", "submission_id", [r["id"] for r in rows]
        )
        return [
            mappers.submission_from_rows(row, answers.get(row["id"], []))
            for row in rows
        ]

    def get_submission(self, submission_id: str) -> Optional[Submission]:
        rows = (
            self._client.table("submissions")
            .select("*")
            .eq("id", submission_id)
            .execute()
            .data
            or []
        )
        if not rows:
            return None
        answers = (
            self._client.table("submission_answers")
            .select("*")
            .eq("submission_id", submission_id)
            .execute()
            .data
            or []
        )
        return mappers.submission_from_rows(rows[0], answers)

    def save_submission(self, submission: Submission) -> Submission:
        row, answer_rows = mappers.submission_to_rows(submission)
        self._client.table("submissions").upsert(row).execute()
        self._replace_children(
            "submission_answers", "submission_id", submission.id, answer_rows
        )
        return submission

    def set_submission_status(
        self, submission_id: str, status: SubmissionStatus
    ) -> None:
        self._client.table("submissions").update({"status": status.value}).eq(
            "id", submission_id
        ).execute()

    # --- Grading -------------------------------------------------------
    def list_grading_results(
        self, submission_id: Optional[str] = None
    ) -> List[GradingResult]:
        query = self._client.table("grading_results").select("*")
        if submission_id:
            query = query.eq("submission_id", submission_id)
        return [mappers.grading_result_from_row(r) for r in query.execute().data or []]

    def save_grading_result(self, result: GradingResult) -> GradingResult:
        # (submission_id, question_id) is the primary key, so upsert is the
        # re-grade path as well as the first-grade path.
        self._client.table("grading_results").upsert(
            mappers.grading_result_to_row(result)
        ).execute()
        return result

    # --- Users ---------------------------------------------------------
    def list_users(self) -> List[User]:
        return [mappers.user_from_row(r) for r in self._rows("profiles")]

    def save_user(self, user: User) -> User:
        # Only display_name and year_group are writable by a signed-in user;
        # `role` is refused by the column grant in db/policies.sql. Sending the
        # whole row would fail, so the update is narrowed to what is allowed.
        self._client.table("profiles").update(
            {"display_name": user.display_name, "year_group": user.year_group}
        ).eq("id", user.id).execute()
        return user

    # --- Study camps ---------------------------------------------------
    def list_study_camps(self, student_id: Optional[str] = None) -> List[StudyCamp]:
        query = self._client.table("study_camps").select("*")
        if student_id:
            query = query.eq("student_id", student_id)
        rows = query.execute().data or []
        sessions = self._children("study_sessions", "camp_id", [r["id"] for r in rows])
        return [
            mappers.study_camp_from_rows(row, sessions.get(row["id"], []))
            for row in rows
        ]

    def save_study_camp(self, camp: StudyCamp) -> StudyCamp:
        row, session_rows = mappers.study_camp_to_rows(camp)
        # Insert, not upsert. There is no UPDATE policy on study_camps, by
        # design: the baseline must not be rewritten after the fact. An existing
        # camp keeps the row it has, and only its sessions move.
        if not self._camp_exists(camp.id):
            self._client.table("study_camps").insert(row).execute()
        self._replace_children("study_sessions", "camp_id", camp.id, session_rows)
        return camp

    def _camp_exists(self, camp_id: str) -> bool:
        rows = (
            self._client.table("study_camps")
            .select("id")
            .eq("id", camp_id)
            .execute()
            .data
            or []
        )
        return bool(rows)

    def delete_study_camp(self, camp_id: str) -> bool:
        response = (
            self._client.table("study_camps").delete().eq("id", camp_id).execute()
        )
        return bool(response.data)


# --------------------------------------------------------------------------
# Which backend is in use
# --------------------------------------------------------------------------
_repository: Optional[Repository] = None


def get_repository() -> Repository:
    """The active backend.

    Supabase is used only when it is configured AND somebody is signed in.
    Credentials alone are not enough: db/policies.sql grants to `authenticated`,
    so an anonymous session can read nothing and write nothing. Handing the app
    a Supabase repository in that state would produce an app that silently loses
    every write, which is worse than demo mode and much harder to diagnose.

    So the check is for a session, not for a key, and the answer is reported in
    the sidebar rather than guessed at.
    """
    global _repository
    if _repository is None:
        from services.supabase_client import get_authenticated_client

        client = get_authenticated_client()
        _repository = (
            SupabaseRepository(client) if client is not None else SessionRepository()
        )
    return _repository


def set_repository(repository: Optional[Repository]) -> None:
    """Test hook: force a backend, or pass None to re-detect."""
    global _repository
    _repository = repository
