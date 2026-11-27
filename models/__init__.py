"""Pydantic domain models for Camp Prep AI."""

from models.assessment import (
    CURRICULA,
    DEFAULT_CURRICULUM,
    GRADE_LEVELS,
    Assessment,
    AssessmentType,
    Question,
    Subject,
)
from models.attempt import AttemptState, QuestionStanding
from models.guidance import GENERIC_SHAPE, Guidance
from models.grading import ErrorItem, ErrorType, GradingResult, ReviewStatus
from models.study_plan import StudyCamp, StudySession
from models.submission import Submission, SubmissionStatus
from models.user import (
    CLASS_NAME_MAX_CHARS,
    DEFAULT_CLASS_NAME,
    SCHOOL_MAX_CHARS,
    ClassMembership,
    Classroom,
    Role,
    User,
    clean_school,
    students_of,
)

__all__ = [
    "Assessment",
    "AssessmentType",
    "Question",
    "Subject",
    "Guidance",
    "GENERIC_SHAPE",
    "AttemptState",
    "QuestionStanding",
    "CURRICULA",
    "DEFAULT_CURRICULUM",
    "GRADE_LEVELS",
    "Submission",
    "SubmissionStatus",
    "GradingResult",
    "ErrorItem",
    "ErrorType",
    "ReviewStatus",
    "StudyCamp",
    "StudySession",
    "Role",
    "User",
    "students_of",
    "Classroom",
    "ClassMembership",
    "clean_school",
    "CLASS_NAME_MAX_CHARS",
    "DEFAULT_CLASS_NAME",
    "SCHOOL_MAX_CHARS",
]
