"""Users and roles.

Two roles for now. Students are the primary users of the app; teachers get an
oversight view of the students linked to them.

There is no real authentication yet - the role is chosen in the sidebar in demo
mode. Real sign-in belongs in Supabase Auth, where the role is stored server
side and cannot be self-declared. Until then, treat `Role` as a UI convenience,
not a security boundary.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Role(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"

    @property
    def label(self) -> str:
        return self.value.title()


SCHOOL_MAX_CHARS = 80
CLASS_NAME_MAX_CHARS = 60
# What a teacher's first class is called when it is made for them: by migration
# 013 for codes and students that existed before classes had names, or when a
# teacher issues a code before naming any class. They can rename it.
DEFAULT_CLASS_NAME = "My class"


def clean_school(value: Optional[str]) -> Optional[str]:
    """One spelling of a school: inner spaces collapsed, ends trimmed, blank -> None.

    The school is typed by hand, so "Greenfield  School " and "Greenfield School"
    must not become two schools. Capitals are left alone; the list of schools
    (db/migrations/013) treats them as the same school anyway.
    """
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


class User(BaseModel):
    """A person using the app.

    Signed-in users go by the name they gave at sign-up. Demo students, and
    accounts created without a name, get an anonymous code such as S-8201.
    """

    id: str = Field(default_factory=lambda: f"usr_{uuid.uuid4().hex[:8]}")
    display_name: str = Field(min_length=1, max_length=60)
    role: Role = Role.STUDENT
    # Which teacher's roster this student belongs to. None for teachers.
    teacher_id: Optional[str] = None
    # Which of that teacher's classes they sit in (migration 013). Always set
    # together with teacher_id; None for teachers.
    class_id: Optional[str] = None
    year_group: Optional[int] = None
    # Free text, from sign-up or Profile (migration 013). Tidied, not trusted.
    school: Optional[str] = None
    # Public URL of a profile photo in the `avatars` bucket, if one was added.
    avatar_url: Optional[str] = None

    @field_validator("display_name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Display name must not be blank.")
        return cleaned

    @field_validator("school")
    @classmethod
    def _tidy_school(cls, value: Optional[str]) -> Optional[str]:
        return clean_school(value)

    @property
    def is_student(self) -> bool:
        return self.role is Role.STUDENT

    @property
    def is_teacher(self) -> bool:
        return self.role is Role.TEACHER


def students_of(users: List[User], teacher_id: str) -> List[User]:
    """Every student on one teacher's roster."""
    return [u for u in users if u.is_student and u.teacher_id == teacher_id]


class Classroom(BaseModel):
    """One of a teacher's classes (migration 013).

    A teacher can run several - Year 9 Maths, Year 10 Maths - each with its own
    name and its own join code. A student sits in at most one class, which also
    decides their teacher.
    """

    id: str = Field(default_factory=lambda: f"cls_{uuid.uuid4().hex[:12]}")
    teacher_id: str
    name: str = Field(min_length=1, max_length=CLASS_NAME_MAX_CHARS)
    # The live join code, if one has been issued. Issuing a new one replaces it,
    # which is what stops the old one working.
    code: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _tidy_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("A class needs a name.")
        return cleaned


class ClassMembership(BaseModel):
    """What a student is told about the class they are in.

    A separate, small object on purpose: a student may not read their teacher's
    profile (db/policies.sql, profiles_select_self), so the database hands over
    just these names through my_class() in migration 013.
    """

    teacher_name: str
    class_name: Optional[str] = None
    teacher_school: Optional[str] = None
