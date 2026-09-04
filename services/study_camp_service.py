"""Study camp builder.

Turns a weakness analysis into a short, dated revision programme. This is the
"and then do something about it" step that separates the app from asking a
chatbot to mark one question.

Questions come from the existing template generator in `practice_service`, so
the camp is deterministic: the same weaknesses produce the same programme.
Phase 2 swaps that generator for a real AI service and this module keeps
working unchanged.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Sequence

import pandas as pd

from models import ErrorType, StudyCamp, StudySession
from services import analytics_service as analytics
from services.practice_service import (
    available_topics,
    generate_practice_questions,
)

DEFAULT_DURATION_DAYS = 7
MIN_DURATION_DAYS = 3
MAX_DURATION_DAYS = 14
QUESTIONS_PER_SESSION = 4

# Below this average, a topic is worth building a camp around.
WEAKNESS_CEILING = 75.0

# Which error category to drill for a topic, based on what actually went wrong.
_DEFAULT_FOCUS = ErrorType.MISSING_WORKING


def dominant_error_for_topic(frame: pd.DataFrame, topic: str) -> ErrorType:
    """The error category that appeared most often in this topic's results."""
    if frame.empty or "error_types" not in frame:
        return _DEFAULT_FOCUS

    rows = frame[frame["topic"] == topic]
    counts: Dict[str, int] = {}
    for entry in rows.get("error_types", []):
        for error_type in entry or []:
            counts[error_type] = counts.get(error_type, 0) + 1

    if not counts:
        return _DEFAULT_FOCUS
    best = max(counts.items(), key=lambda item: item[1])[0]
    try:
        return ErrorType(best)
    except ValueError:
        return _DEFAULT_FOCUS


def suggest_topics(frame: pd.DataFrame, limit: int = 3) -> List[str]:
    """Topics worth a camp: weakest first, and only those with templates.

    A topic with no practice templates cannot be drilled yet, so offering it
    would produce an empty camp.
    """
    candidates = analytics.weakest_topics(frame, limit=limit * 3, ceiling=WEAKNESS_CEILING)
    supported = set(available_topics())
    return [topic for topic in candidates if topic in supported][:limit]


def available_topics_for(frame: pd.DataFrame) -> List[str]:
    """Every topic a camp could be built from, weakest first.

    A topic is offered only if practice templates exist for it - otherwise the
    camp would have no questions to give. Topics the student has worked on are
    listed first (weakest first), then any remaining supported topics.
    """
    supported = available_topics()
    if frame.empty:
        return list(supported)

    ranked = analytics.topic_performance(frame)["topic"].tolist()
    seen = [t for t in ranked if t in supported]
    rest = [t for t in supported if t not in seen]
    return seen + rest


def baseline_for(frame: pd.DataFrame, topics: Sequence[str]) -> float:
    """The student's current average across the chosen topics.

    Captured once, when the camp is created, so improvement is measured against
    a fixed starting point rather than a moving one.
    """
    if frame.empty or not topics:
        return 0.0
    rows = frame[frame["topic"].isin(list(topics))]
    if rows.empty:
        return 0.0
    return round(float(rows["percentage"].mean()), 1)


def difficulty_for(baseline: float) -> str:
    """Start where the student actually is, not where the syllabus is.

    A camp is built on a student's *weak* topics, so the bands are deliberately
    generous: someone averaging 75% on their worst topic still needs practice
    at the standard level, not extension work.
    """
    if baseline < 55:
        return "Foundation"
    if baseline < 80:
        return "Core"
    return "Extension"


def build_camp(
    student_id: str,
    frame: pd.DataFrame,
    topics: Optional[Sequence[str]] = None,
    duration_days: int = DEFAULT_DURATION_DAYS,
    started_on: Optional[date] = None,
) -> StudyCamp:
    """Build a camp for one student from their own performance history.

    Raises ValueError when there is nothing to work on - the caller shows a
    friendly message rather than an empty programme.
    """
    duration_days = max(MIN_DURATION_DAYS, min(int(duration_days), MAX_DURATION_DAYS))

    chosen = list(topics) if topics else suggest_topics(frame)
    chosen = [t for t in chosen if t in set(available_topics())]
    if not chosen:
        raise ValueError(
            "There is not enough marked work yet to build a study camp. "
            "Upload a few more pieces of past work first."
        )

    baseline = baseline_for(frame, chosen)
    difficulty = difficulty_for(baseline)

    sessions: List[StudySession] = []
    for day in range(1, duration_days + 1):
        # Rotate through the weak topics so each gets repeated exposure across
        # the camp rather than being covered once and dropped.
        topic = chosen[(day - 1) % len(chosen)]
        focus = dominant_error_for_topic(frame, topic)
        questions = generate_practice_questions(
            topic=topic,
            error_type=focus,
            difficulty=difficulty,
            count=QUESTIONS_PER_SESSION,
        )
        sessions.append(
            StudySession(
                day=day,
                topic=topic,
                questions=[q.question_text for q in questions],
                method_hints=[q.method_hint for q in questions],
                skill_focus=questions[0].skill_focus if questions else "",
            )
        )

    return StudyCamp(
        student_id=student_id,
        topics=chosen,
        started_on=started_on or date.today(),
        duration_days=duration_days,
        baseline_percentage=baseline,
        sessions=sessions,
    )


def record_session_result(camp: StudyCamp, day: int, score: int) -> StudyCamp:
    """Mark one day complete with the number of questions answered correctly."""
    session = camp.get_session(day)
    if session is None:
        raise ValueError(f"This camp has no day {day}.")
    if not 0 <= score <= session.question_count:
        raise ValueError(
            f"Score must be between 0 and {session.question_count} for day {day}."
        )
    session.score = int(score)
    session.completed = True
    return camp


def reopen_session(camp: StudyCamp, day: int) -> StudyCamp:
    """Undo a completed day, so a mis-click is recoverable."""
    session = camp.get_session(day)
    if session is None:
        raise ValueError(f"This camp has no day {day}.")
    session.score = None
    session.completed = False
    return camp


def progress_summary(camp: StudyCamp) -> Dict[str, object]:
    """Everything the progress panel needs, computed in one place."""
    latest = camp.latest_percentage
    return {
        "baseline": camp.baseline_percentage,
        "latest": latest,
        "improvement": camp.improvement,
        "completed": len([s for s in camp.sessions if s.completed]),
        "total": len(camp.sessions),
        "progress": camp.progress,
        "is_complete": camp.is_complete,
        "topics": camp.topics,
    }
