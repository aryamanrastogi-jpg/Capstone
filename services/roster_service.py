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
  A display name - an anonymous code like S-1102 - a year group, and their work.
  There is no name, no email, and nothing here that would produce one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from models import User, students_of
from services.repository import get_repository


@dataclass(frozen=True)
class RosterOutcome:
    ok: bool
    message: str


def list_roster(teacher_id: str) -> List[User]:
    """Every student on one teacher's roster, ordered by display name."""
    roster = students_of(get_repository().list_users(), teacher_id)
    return sorted(roster, key=lambda u: u.display_name)


def class_code(teacher_id: str) -> Optional[str]:
    """The teacher's live class code, or None if they have not issued one."""
    return get_repository().get_class_code(teacher_id)


def rotate_class_code(teacher_id: str) -> str:
    """Issue a new code, revoking the previous one.

    Revoking is the point: a code that has been shared too widely has to stop
    working, and a rotation that left the old one live would be a decoration.
    Students already on the roster are unaffected - the code is how you join,
    not what keeps you there.
    """
    return get_repository().rotate_class_code(teacher_id)


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

    return RosterOutcome(True, "You have joined the class.")


def leave_class(student_id: str) -> RosterOutcome:
    """A student removes themselves.

    Their own uploads and question sets are untouched and stay theirs. What
    changes is that the teacher stops seeing their work, and they stop seeing
    the class's assessments.
    """
    get_repository().leave_class(student_id)
    return RosterOutcome(True, "You have left the class.")


def remove_from_roster(teacher_id: str, student_id: str) -> RosterOutcome:
    """A teacher removes a student. Nothing the student made is deleted."""
    removed = get_repository().remove_from_roster(teacher_id, student_id)
    if not removed:
        return RosterOutcome(False, "That student is not on your roster.")
    return RosterOutcome(True, "Removed from your class.")
