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


class User(BaseModel):
    """A person using the app.

    Students are identified by an anonymous code (S-8201), never a real name.
    """

    id: str = Field(default_factory=lambda: f"usr_{uuid.uuid4().hex[:8]}")
    display_name: str = Field(min_length=1, max_length=60)
    role: Role = Role.STUDENT
    # Which teacher's roster this student belongs to. None for teachers.
    teacher_id: Optional[str] = None
    year_group: Optional[int] = None

    @field_validator("display_name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Display name must not be blank.")
        return cleaned

    @property
    def is_student(self) -> bool:
        return self.role is Role.STUDENT

    @property
    def is_teacher(self) -> bool:
        return self.role is Role.TEACHER


def students_of(users: List[User], teacher_id: str) -> List[User]:
    """Every student on one teacher's roster."""
    return [u for u in users if u.is_student and u.teacher_id == teacher_id]
