from datetime import date, datetime, timedelta

import streamlit as st
from auth.session import require_current_user

from database.connection import get_connection
from services.module_service import get_modules
from services.progress_service import get_progress_snapshot, get_routine_metrics
from services.timetable_service import CATEGORIES

connection = get_connection()
user_id = require_current_user().user_id
st.title("Progress")
st.caption("Derived from your timetable, attendance, learning, notes, and test results.")

modules = get_modules(connection, user_id)
module_options = {"All modules": None}
module_options.update({row["module_name"]: int(row["module_id"]) for row in modules})
period = st.segmented_control(
    "Time period", ["This week", "This month", "All time"], default="All time"
)
module_name = st.selectbox("Module", list(module_options))
category = st.selectbox("Category", ["All categories", *CATEGORIES])
today = date.today()
since = (
    today - timedelta(days=6) if period == "This week"
    else today - timedelta(days=29) if period == "This month"
    else None
)
snapshot = get_progress_snapshot(
    connection, user_id, module_options[module_name], category, since, datetime.now()
)
routine_metrics = get_routine_metrics(
    connection, user_id,
    since.isoformat() if since else None,
    today.isoformat(),
)

metrics = snapshot.overall
cards = st.columns(5)
cards[0].metric("Completion", f"{metrics.completion_percentage:g}%")
cards[1].metric("Scheduled", metrics.scheduled)
cards[2].metric("Completed", metrics.completed)
cards[3].metric("Missed", metrics.missed)
cards[4].metric("Upcoming", metrics.upcoming)

test_col, consistency_col = st.columns(2)
with test_col:
    st.subheader("Test performance")
    st.metric("Tests completed", snapshot.test_performance.count)
    st.metric(
        "Average score",
        f"{snapshot.test_performance.average_score:g}%"
        if snapshot.test_performance.average_score is not None else "—",
    )
    st.write("Best:", snapshot.test_performance.best_score or "—")
    st.metric(
        "Average interview score",
        f"{snapshot.interview_performance.average_score:g}%"
        if snapshot.interview_performance.average_score is not None else "—",
    )
with consistency_col:
    st.subheader("Consistency")
    st.metric("Active learning days", snapshot.active_learning_days)
    st.metric("Current streak", snapshot.current_streak)
    st.write(f"Learning velocity: {snapshot.learning_velocity:g} completed sessions/week")

st.subheader("Body & Routine (separate)")
routine_cards = st.columns(4)
routine_cards[0].metric("Routine consistency", f"{routine_metrics.consistency_percentage:g}%")
routine_cards[1].metric("Routine completed", routine_metrics.completed)
routine_cards[2].metric("Routine streak", routine_metrics.current_streak)
routine_cards[3].metric("Routine missed", routine_metrics.missed)

st.subheader("Module progress")
if snapshot.modules:
    st.dataframe(
        [
            {
                "Module": item.module_name,
                "Scheduled": item.metrics.scheduled,
                "Completed": item.metrics.completed,
                "Missed": item.metrics.missed,
                "Upcoming": item.metrics.upcoming,
                "Completion %": item.metrics.completion_percentage,
                "Average test %": item.test_performance.average_score or "—",
                "Last activity": item.last_activity or "—",
            }
            for item in snapshot.modules
        ],
        hide_index=True,
        width="stretch",
    )
else:
    st.info("No scheduled learning activity matches this filter.")

left, right = st.columns(2)
with left:
    st.subheader("Topic mastery")
    st.dataframe(
        [
            {
                "Topic": item.topic,
                "Completion %": item.metrics.completion_percentage,
                "Tests": item.test_performance.count,
                "Mastery": f"{item.mastery_score:g} · {item.mastery_label}",
            }
            for item in snapshot.topics
        ],
        hide_index=True,
        width="stretch",
    )
with right:
    st.subheader("Weak areas")
    if snapshot.weak_areas:
        st.dataframe(
            [
                {
                    "Area": item.topic,
                    "Signals": item.signals,
                    "Severity": item.severity,
                    "Confidence": round(item.confidence, 2),
                }
                for item in snapshot.weak_areas
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.success("No accumulated weak-area signals yet.")

st.subheader("Recent activity")
if snapshot.recent_activity:
    for item in snapshot.recent_activity[:10]:
        detail = f" · {item['percentage']:g}%" if item.get("percentage") is not None else ""
        st.write(f"**{item['type']}** · {item.get('topic', '')}{detail} · {item.get('at', '')}")
else:
    st.info("Recent learning activity will appear here.")
