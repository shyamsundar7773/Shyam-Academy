from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProgressMetrics:
    scheduled: int = 0
    completed: int = 0
    missed: int = 0
    upcoming: int = 0
    completion_percentage: float = 0.0


@dataclass(frozen=True)
class TestPerformance:
    count: int = 0
    latest_score: float | None = None
    best_score: float | None = None
    average_score: float | None = None


@dataclass(frozen=True)
class ModuleProgress:
    module_id: int
    module_name: str
    metrics: ProgressMetrics
    test_performance: TestPerformance = field(default_factory=TestPerformance)
    last_activity: str | None = None


@dataclass(frozen=True)
class CategoryProgress:
    category: str
    metrics: ProgressMetrics
    test_performance: TestPerformance = field(default_factory=TestPerformance)


@dataclass(frozen=True)
class TopicProgress:
    topic: str
    metrics: ProgressMetrics
    test_performance: TestPerformance = field(default_factory=TestPerformance)
    mastery_score: float = 0.0
    mastery_label: str = "Not started"


@dataclass(frozen=True)
class WeakArea:
    topic: str
    category: str | None
    signals: int
    severity: str
    confidence: float
    improving: bool = False


@dataclass(frozen=True)
class ProgressSnapshot:
    overall: ProgressMetrics
    test_performance: TestPerformance
    interview_performance: TestPerformance = field(default_factory=TestPerformance)
    modules: list[ModuleProgress] = field(default_factory=list)
    categories: list[CategoryProgress] = field(default_factory=list)
    topics: list[TopicProgress] = field(default_factory=list)
    weak_areas: list[WeakArea] = field(default_factory=list)
    recent_activity: list[dict] = field(default_factory=list)
    active_learning_days: int = 0
    current_streak: int = 0
    learning_velocity: float = 0.0
    period_label: str = "All time"
