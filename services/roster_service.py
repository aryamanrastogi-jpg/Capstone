"""Class rosters: who is in a teacher's class, and how they got there.

WHY A ROSTER EXISTS AT ALL
  `profiles.teacher_id` is what makes a student's app non-empty. Their teacher's
  assessments are visible because of it, and a teacher's oversight pages are
  scoped by it. Before this module the only way to set it was an operator
  running UPDATE by hand.

JOINING IS CONSENSUAL IN BOTH DIRECTIONS
  A teacher issues a code. A student chooses to enter it. Neither writes the
  other's row - a student cannot attach themselves to a teacher who never gave
  out the code, and a teacher cannot claim a student who never entered one.

  That is not a convention this module keeps. `teacher_id` is not in the column
  grant in db/policies.sql, so no write from here could set it whatever this
  code did; the `security definer` functions in db/migrations/003_roster.sql are
  the only path, and each checks the caller before it writes.

WHAT A TEACHER CAN SEE OF A STUDENT
  The name they signed up with (or an anonymous code like S-1102 in the demo),
  their class, year group, school, and their work. Never their email.

SEVERAL CLASSES PER TEACHER (db/migrations/013_classes_and_schools.sql)
  A teacher can run Year 9 Maths and Year 10 Maths side by side. Each class has
  its own name and its own code, so the code a student types decides both
  their teacher and their class. `profiles.teacher_id` still decides what they
  can see; the class only groups the roster. A student is in one class at a
  time: entering another code moves them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from models import (
    CLASS_NAME_MAX_CHARS,
    ClassMembership,
    Classroom,
    User,
    students_of,
)
from services.repository import get_repository

NOT_SET_UP_MESSAGE = (
    "Classes need a database update that has not been applied yet "
    "(db/migrations/013_classes_and_schools.sql). Ask whoever runs the app "
    "to apply it."
)


class ClassesNotSetUp(RuntimeError):
    """The database has no `classes` table yet: migration 013 is not applied."""


@dataclass(frozen=True)
class RosterOutcome:
    ok: bool
    message: str


def list_roster(teacher_id: str) -> List[User]:
    """Every student on one teacher's roster, ordered by display name."""
    roster = students_of(get_repository().list_users(), teacher_id)
    return sorted(roster, key=lambda u: u.display_name)


# --------------------------------------------------------------------------
# Classes
# --------------------------------------------------------------------------
def _missing_table(exc: Exception) -> bool:
    text = str(exc).lower()
    return "pgrst205" in text or "42p01" in text or "could not find the table" in text


def list_classes(teacher_id: str) -> List[Classroom]:
    """A teacher's classes, oldest first, each with its live code (or None).

    Raises ClassesNotSetUp when the database predates migration 013, so the page
    can say so instead of showing an error from Postgres.
    """
    try:
        return get_repository().list_classes(teacher_id)
    except Exception as exc:  # noqa: BLE001 - only a missing table is translated
        if _missing_table(exc):
            raise ClassesNotSetUp(NOT_SET_UP_MESSAGE) from exc
        raise


def _tidy(name: str) -> str:
    return " ".join((name or "").split())


def class_name_problem(name: str) -> Optional[str]:
    """Why a class name cannot be used, or None."""
    cleaned = _tidy(name)
    if not cleaned:
        return "Give the class a name, like Year 9 Maths."
    if len(cleaned) > CLASS_NAME_MAX_CHARS:
        return f"Keep the class name under {CLASS_NAME_MAX_CHARS} characters."
    return None


def _name_taken(teacher_id: str, name: str, except_id: Optional[str] = None) -> bool:
    wanted = _tidy(name).lower()
    return any(
        c.name.lower() == wanted and c.id != except_id
        for c in list_classes(teacher_id)
    )


def create_class(teacher_id: str, name: str) -> RosterOutcome:
    """Add a class. It has no code until the teacher issues one."""
    problem = class_name_problem(name)
    if problem:
        return RosterOutcome(False, problem)
    if _name_taken(teacher_id, name):
        return RosterOutcome(False, "You already have a class with that name.")
    get_repository().create_class(teacher_id, _tidy(name))
    return RosterOutcome(True, f"Class added: {_tidy(name)}.")


def rename_class(teacher_id: str, class_id: str, name: str) -> RosterOutcome:
    problem = class_name_problem(name)
    if problem:
        return RosterOutcome(False, problem)
    if _name_taken(teacher_id, name, except_id=class_id):
        return RosterOutcome(False, "You already have a class with that name.")
    if not get_repository().rename_class(teacher_id, class_id, _tidy(name)):
        return RosterOutcome(False, "That class is not one of yours.")
    return RosterOutcome(True, f"Class renamed to {_tidy(name)}.")


def delete_class(teacher_id: str, class_id: str) -> RosterOutcome:
    """Delete an empty class, and its code with it.

    Only an empty one: deleting a class with students in it would leave them on
    the roster in no class, which nobody asked for. Its code stops working.
    """
    if any(s.class_id == class_id for s in list_roster(teacher_id)):
        return RosterOutcome(
            False,
            "Only an empty class can be deleted. Remove its students first, or "
            "keep the class.",
        )
    if not get_repository().delete_class(teacher_id, class_id):
        return RosterOutcome(False, "That class is not one of yours.")
    return RosterOutcome(True, "Class deleted. Its code no longer works.")


def my_class(student: User) -> Optional[ClassMembership]:
    """The class a student is in and who teaches it, or None if they are in none.

    Before migration 013 the database cannot say more than "your teacher", so a
    failed lookup falls back to that rather than claiming they have no class.
    """
    if not student.teacher_id:
        return None
    try:
        membership = get_repository().my_class(student.id)
    except Exception:  # noqa: BLE001 - see the docstring
        membership = None
    return membership or ClassMembership(teacher_name="your teacher")


# --------------------------------------------------------------------------
# Codes
# --------------------------------------------------------------------------
def class_code(teacher_id: str) -> Optional[str]:
    """The live code of the teacher's first class, or None if it has none."""
    return get_repository().get_class_code(teacher_id)


def rotate_class_code(teacher_id: str, class_id: Optional[str] = None) -> str:
    """Issue a new code for one class, revoking the previous one.

    Revoking is the point: a code that has been shared too widely has to stop
    working, and a rotation that left the old one live would be a decoration.
    Students already in the class are unaffected - the code is how you join,
    not what keeps you there. With no class given, the teacher's first class is
    used (and made, as "My class", if they have none).
    """
    return get_repository().rotate_class_code(teacher_id, class_id)


def join_class(student_id: str, code: str) -> RosterOutcome:
    """Attach a student to the class that issued `code`."""
    cleaned = (code or "").strip().upper()
    if not cleaned:
        return RosterOutcome(False, "Enter the code your teacher gave you.")

    teacher_id = get_repository().join_class(student_id, cleaned)
    if teacher_id is None:
        # Deliberately the same message for "no such code" and "revoked code".
        # Distinguishing them would turn this box into a way of testing which
        # codes exist.
        return RosterOutcome(False, "That class code is not valid.")

    from services.auth_service import invalidate_cached_profile

    invalidate_cached_profile()

    return RosterOutcome(True, "You have joined the class.")


def leave_class(student_id: str) -> RosterOutcome:
    """A student removes themselves.

    Their own uploads and question sets are untouched and stay theirs. What
    changes is that the teacher stops seeing their work, and they stop seeing
    the class's assessments.
    """
    get_repository().leave_class(student_id)
    from services.auth_service import invalidate_cached_profile

    invalidate_cached_profile()
    return RosterOutcome(True, "You have left the class.")


def remove_from_roster(teacher_id: str, student_id: str) -> RosterOutcome:
    """A teacher removes a student. Nothing the student made is deleted."""
    removed = get_repository().remove_from_roster(teacher_id, student_id)
    if not removed:
        return RosterOutcome(False, "That student is not on your roster.")
    return RosterOutcome(True, "Removed from your class.")
