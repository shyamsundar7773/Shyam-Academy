from dataclasses import dataclass, field


QUESTION_TYPES = {"mcq", "multiple_select", "short_answer", "sql", "mixed"}


@dataclass(frozen=True)
class TestQuestion:
    __test__ = False
    order_index: int
    question_type: str
    question_text: str
    options: list[str]
    correct_answer: str | list[str]
    explanation: str
    points: float
    weak_area: str


@dataclass(frozen=True)
class TestPlan:
    __test__ = False
    title: str
    description: str
    category: str
    topic: str
    difficulty: str
    duration_minutes: int | None
    questions: list[TestQuestion] = field(default_factory=list)

    @property
    def total_questions(self) -> int:
        return len(self.questions)
