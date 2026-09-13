from dataclasses import dataclass, field


INTERVIEW_MODES = {
    "Technical Interview",
    "SQL Interview",
    "Data Analyst Interview",
    "Behavioral Interview",
    "HR Interview",
    "Mock Interview",
}
QUESTION_TYPES = {
    "Conceptual",
    "SQL",
    "Scenario-based",
    "Problem-solving",
    "Behavioral",
    "HR",
    "Experience-based",
    "Mixed technical",
}


@dataclass(frozen=True)
class InterviewQuestionPlan:
    question_text: str
    question_type: str
    topic: str
    expected_points: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InterviewQuestion:
    question_text: str
    question_type: str
    topic: str
    expected_points: list[str]


@dataclass(frozen=True)
class InterviewEvaluation:
    score: float
    correctness: float
    relevance: float
    clarity: float
    technical_depth: float
    communication_quality: float
    strengths: list[str]
    weaknesses: list[str]
    missing_points: list[str]
    corrections: list[str]
    suggested_answer: str
    feedback: str


@dataclass(frozen=True)
class InterviewPlan:
    title: str
    mode: str
    difficulty: str
    topic: str
    questions: list[InterviewQuestionPlan]
