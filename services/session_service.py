import sqlite3

from services.timetable_service import get_session_details


def get_learning_context(
    connection: sqlite3.Connection, session_id: int, user_id: str
) -> dict:
    session = get_session_details(connection, session_id, user_id)
    if session is None:
        raise ValueError("The selected session could not be found.")
    return dict(session)


def get_learning_route(category: str) -> str:
    routes = {
        "Today Learning": "pages/today_learning.py",
        "Level 1": "pages/level_1.py",
        "Level 2": "pages/level_2.py",
        "Problem Solving": "pages/problem_solving.py",
        "Test": "pages/tests.py",
        "On-time Test": "pages/tests.py",
        "Daily Test": "pages/tests.py",
        "Weekly Test": "pages/tests.py",
        "Interview Preparation": "pages/interview_preparation.py",
        "Interview Room": "pages/interview_room.py",
    }
    return routes.get(category, "pages/learning.py")
