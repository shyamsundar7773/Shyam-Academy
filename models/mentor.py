from dataclasses import dataclass, field


MENTOR_ACTIONS = {
    "GENERAL_GUIDANCE",
    "STUDY_RECOMMENDATION",
    "WEAK_AREA_REVIEW",
    "PROGRESS_REVIEW",
    "MISSED_SESSION_REVIEW",
    "UPCOMING_SESSION_PREP",
    "TEST_PREPARATION",
    "INTERVIEW_PREPARATION",
    "CAREER_GUIDANCE",
    "STUDY_PLAN",
}


@dataclass(frozen=True)
class MentorRecommendation:
    priority: str
    module_id: int | None
    module_name: str | None
    category: str | None
    topic: str
    reason: str
    evidence: list[str] = field(default_factory=list)
    suggested_action: str = ""


@dataclass(frozen=True)
class MentorContext:
    user_id: str
    module_id: int | None
    progress: dict
    upcoming_sessions: list[dict]
    missed_sessions: list[dict]
    recent_activity: list[dict]
    notes: list[dict]
    recommendations: list[MentorRecommendation]
    routine_evidence: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class MentorResponse:
    response: str
    recommendations: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
