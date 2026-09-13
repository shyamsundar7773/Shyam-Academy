from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from database.repositories import progress_repository as repo
from models.progress import (
    CategoryProgress,
    ModuleProgress,
    ProgressMetrics,
    ProgressSnapshot,
    TestPerformance,
    TopicProgress,
    WeakArea,
)
PROGRESS_CATEGORY_VOCABULARY = (
    "Today Learning", "Level 1", "Level 2", "Problem Solving",
    "On-time Test", "Daily Test", "Weekly Test",
    "Interview Preparation", "Interview Room",
)


def _as_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _metrics(rows, now):
    scheduled = len(rows)
    completed = 0
    missed = 0
    upcoming = 0
    for row in rows:
        status = row["attendance_status"]
        if status == "Attended":
            completed += 1
            continue
        if status == "Missed":
            missed += 1
            continue
        try:
            starts = datetime.strptime(
                f"{row['session_date']} {row['scheduled_time']}", "%Y-%m-%d %I:%M %p"
            )
        except (TypeError, ValueError):
            continue
        if starts > now:
            upcoming += 1
        else:
            missed += 1
    denominator = completed + missed
    return ProgressMetrics(
        scheduled=scheduled,
        completed=completed,
        missed=missed,
        upcoming=upcoming,
        completion_percentage=round(completed / denominator * 100, 1)
        if denominator else 0.0,
    )


def _performance(rows):
    values = [float(row["percentage"]) for row in rows if row["percentage"] is not None]
    if not values:
        return TestPerformance()
    return TestPerformance(
        count=len(values),
        latest_score=values[-1],
        best_score=max(values),
        average_score=round(sum(values) / len(values), 1),
    )


def _mastery(metrics, performance):
    if not metrics.scheduled:
        return 0.0, "Not started"
    completion = metrics.completed / metrics.scheduled
    score = (performance.average_score or 0.0) / 100
    consistency = 1.0 if metrics.missed == 0 and metrics.completed else 0.0
    value = round((completion * 40) + (score * 50) + (consistency * 10), 1)
    if performance.count < 2:
        value = min(value, 59.9)
    label = "Mastered" if value >= 80 else "Developing" if value >= 50 else "Needs review"
    return value, label


def _date_for_activity(row):
    return (
        _as_datetime(row.get("at")) if isinstance(row, dict)
        else _as_datetime(row["at"]) if "at" in row.keys() else None
    )


def _activity(sessions, attempts, notes, interviews=()):
    items = []
    for row in sessions:
        if row["attendance_status"] == "Attended" and row["attended_at"]:
            items.append({
                "type": "Learning completed", "topic": row["topic"],
                "module_name": row["module_name"], "at": row["attended_at"],
                "activity_date": row["session_date"],
                "session_id": row["session_id"],
            })
        elif row["attendance_status"] == "Missed":
            items.append({
                "type": "Session missed", "topic": row["topic"],
                "module_name": row["module_name"], "at": row["session_date"],
                "activity_date": row["session_date"],
                "session_id": row["session_id"],
            })
    for row in interviews:
        items.append({
            "type": "Interview completed", "topic": row["topic"],
            "module_id": row["module_id"], "at": row["completed_at"],
            "activity_date": (row["completed_at"] or "")[:10],
            "score": row["score"], "interview_session_id": row["interview_session_id"],
        })
    for row in attempts:
        items.append({
            "type": "Test completed", "topic": row["topic"],
            "module_id": row["module_id"], "at": row["submitted_at"] or row["started_at"],
            "activity_date": (row["submitted_at"] or row["started_at"] or "")[:10],
            "percentage": row["percentage"], "attempt_id": row["attempt_id"],
        })
    for row in notes:
        items.append({
            "type": "Note saved", "topic": row["topic"], "at": row["saved_at"],
            "activity_date": (row["saved_at"] or "")[:10],
            "note_id": row["note_id"],
        })
    items.sort(key=lambda item: item.get("at") or "", reverse=True)
    return items[:20]


def get_progress_snapshot(
    connection, user_id: str, module_id: int | None = None,
    category: str | None = None, since: date | None = None, now: datetime | None = None,
) -> ProgressSnapshot:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("A user identity is required for progress.")
    now = now or datetime.now()
    sessions = list(repo.list_sessions(connection, user_id, module_id))
    if category and category != "All categories":
        sessions = [row for row in sessions if row["category"] == category]
    if since:
        sessions = [row for row in sessions if row["session_date"] >= since.isoformat()]
    attempts = list(repo.list_attempts(connection, user_id, module_id))
    interviews = list(repo.list_interviews(connection, user_id, module_id))
    if category and category != "All categories":
        attempts = [row for row in attempts if row["category"] == category]
    if since:
        attempts = [
            row for row in attempts
            if (row["submitted_at"] or row["started_at"] or "")[:10] >= since.isoformat()
        ]
        interviews = [
            row for row in interviews
            if (row["completed_at"] or "")[:10] >= since.isoformat()
        ]
    notes = list(repo.list_notes(connection, user_id, module_id))
    metrics = _metrics(sessions, now)
    performance = _performance(attempts)
    interview_performance = _performance(interviews)

    module_groups = defaultdict(list)
    category_groups = defaultdict(list)
    topic_groups = defaultdict(list)
    for row in sessions:
        module_groups[(row["module_id"], row["module_name"])].append(row)
        category_groups[row["category"]].append(row)
        topic_groups[row["topic"]].append(row)

    module_results = []
    for (key, name), rows in module_groups.items():
        module_attempts = [a for a in attempts if a["module_id"] == key]
        module_interviews = [i for i in interviews if i["module_id"] == key]
        activity = _activity(rows, module_attempts, [], module_interviews)
        module_results.append(ModuleProgress(
            int(key), name, _metrics(rows, now), _performance(module_attempts),
            activity[0]["at"] if activity else None,
        ))
    module_results.sort(key=lambda item: item.module_name.casefold())

    category_results = []
    for name in PROGRESS_CATEGORY_VOCABULARY:
        rows = category_groups.get(name, [])
        category_attempts = [a for a in attempts if a["category"] == name]
        category_results.append(CategoryProgress(
            name, _metrics(rows, now), _performance(category_attempts)
        ))

    topic_results = []
    for name, rows in sorted(topic_groups.items(), key=lambda item: item[0].casefold()):
        topic_attempts = [a for a in attempts if a["topic"] == name]
        score, label = _mastery(_metrics(rows, now), _performance(topic_attempts))
        topic_results.append(TopicProgress(
            name, _metrics(rows, now), _performance(topic_attempts), score, label
        ))

    weak_counts = defaultdict(int)
    weak_latest = {}
    weak_category = {}
    for attempt in attempts:
        for weak in repo.parse_weak_areas(attempt["weak_areas_json"]):
            weak_counts[weak] += 1
            weak_latest[weak] = attempt["submitted_at"] or attempt["started_at"]
            weak_category[weak] = attempt["category"]
    for row in repo.list_interview_weaknesses(connection, user_id, module_id):
        for weak in repo.parse_weak_areas(row["weaknesses_json"]):
            weak_counts[weak] += 1
            weak_latest[weak] = row["completed_at"]
            weak_category[weak] = row["mode"]
    weak_results = []
    for topic, count in weak_counts.items():
        severity = "High" if count >= 3 else "Medium" if count >= 2 else "Low"
        weak_results.append(WeakArea(
            topic, weak_category.get(topic), count, severity,
            min(1.0, count / 3), False,
        ))
    weak_results.sort(key=lambda item: (-item.signals, item.topic.casefold()))

    activity = _activity(sessions, attempts, notes, interviews)
    active_days = {
        item["activity_date"] for item in activity
        if item.get("activity_date") and len(item["activity_date"]) >= 10
    }
    streak = 0
    cursor = now.date()
    while cursor.isoformat() in active_days:
        streak += 1
        cursor -= timedelta(days=1)
    period_days = max(1, (now.date() - since).days + 1) if since else 30
    velocity = round(metrics.completed / (period_days / 7), 2)
    return ProgressSnapshot(
        metrics, performance, interview_performance, module_results, category_results, topic_results,
        weak_results, activity, len(active_days), streak, velocity,
        "Filtered period" if since else "All time",
    )


def get_routine_metrics(connection, user_id, start=None, end=None):
    """Return routine-only metrics without changing the academic snapshot."""
    from services.routine_service import get_metrics
    return get_metrics(connection, user_id, start, end)


def get_ai_assistance_metrics(connection, user_id):
    """Return AI activity separately from academic completion metrics."""
    row = connection.execute(
        """SELECT COUNT(*) AS tasks,
        SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) AS completed_tasks
        FROM ai_tasks WHERE user_id=?""", (user_id,)
    ).fetchone()
    proposals = connection.execute(
        """SELECT COUNT(*) AS completed_proposals FROM ai_action_proposals
        WHERE user_id=? AND status='EXECUTED'""", (user_id,)
    ).fetchone()
    return {
        "tasks": int(row["tasks"] or 0),
        "completed_tasks": int(row["completed_tasks"] or 0),
        "completed_proposals": int(proposals["completed_proposals"] or 0),
    }
