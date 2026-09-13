from datetime import date, timedelta

import streamlit as st
from auth.session import require_current_user

from ai.gateway import get_gateway
from ai.routine_creator import RoutineCreatorService
from database.connection import get_connection
from database.repositories import routine_repository
from services.routine_service import (
    academic_conflicts,
    complete_occurrence,
    create_routine,
    get_metrics,
    list_upcoming,
    skip_occurrence,
)

connection = get_connection()
user_id = require_current_user().user_id
st.title("Body & Routine")
st.caption("Track personal routines separately from academic progress.")

metrics = get_metrics(connection, user_id)
cards = st.columns(5)
cards[0].metric("Consistency", f"{metrics.consistency_percentage:g}%")
cards[1].metric("Completed", metrics.completed)
cards[2].metric("Current streak", metrics.current_streak)
cards[3].metric("Best streak", metrics.best_streak)
cards[4].metric("Missed", metrics.missed)

with st.expander("Create a routine", expanded=not routine_repository.list_routines(connection, user_id)):
    with st.form("routine_creator"):
        natural = st.text_area(
            "Describe it naturally",
            placeholder="Daily stretching at 7:00 pm for 20 minutes",
        )
        preview = st.form_submit_button("Preview")
    if preview:
        try:
                st.session_state.routine_preview = RoutineCreatorService(get_gateway()).preview(natural)
        except ValueError as error:
            st.error(str(error))
    values = st.session_state.get("routine_preview")
    if values:
        st.write(values)
        conflicts = academic_conflicts(
            connection, user_id,
            [(values["start_date"], __import__("datetime").datetime.combine(
                date.fromisoformat(values["start_date"]),
                __import__("datetime").time.fromisoformat(values["time_local"]),
            ))],
            values["duration_minutes"],
        )
        if conflicts:
            st.warning("This preview overlaps an academic session; adjust it before confirming.")
        if st.button("Confirm and create routine", type="primary", disabled=bool(conflicts)):
            create_routine(connection, user_id, values)
            st.session_state.pop("routine_preview", None)
            st.success("Routine created.")
            st.rerun()

st.subheader("Upcoming")
rows = list_upcoming(connection, user_id, end=date.today().isoformat())
if not rows:
    st.info("No routines scheduled yet.")
for row in rows[:30]:
    with st.container(border=True):
        st.write(f"**{row['occurrence_date']} · {row['scheduled_at'][11:16]}**")
        st.caption(row["routine_id"])
        left, middle, right = st.columns(3)
        if row["status"] in {"UPCOMING", "DUE"}:
            if left.button("Complete", key=f"complete-{row['occurrence_id']}"):
                complete_occurrence(connection, user_id, row["occurrence_id"])
                st.rerun()
            if middle.button("Skip", key=f"skip-{row['occurrence_id']}"):
                skip_occurrence(connection, user_id, row["occurrence_id"])
                st.rerun()
        else:
            right.write(row["status"].title())

st.subheader("History")
history = routine_repository.list_occurrences(connection, user_id, start=(date.today() - timedelta(days=30)).isoformat())
if history:
    st.dataframe(
        [{"Date": row["occurrence_date"], "Status": row["status"], "Note": row["note"]} for row in history],
        hide_index=True, width="stretch",
    )
else:
    st.info("Routine history will appear here.")
