import json


def list_sessions(connection, user_id, module_id=None):
    clauses = ["s.owner_user_id = ?"]
    params = [user_id]
    if module_id is not None:
        clauses.append("s.module_id = ?")
        params.append(module_id)
    return connection.execute(
        f"""
        SELECT s.*, m.module_name, a.status AS attendance_status,
               a.attended_at, a.updated_at AS attendance_updated_at
        FROM sessions s
        JOIN modules m ON m.module_id = s.module_id
        LEFT JOIN attendance a ON a.session_id = s.session_id
                              AND a.user_id = s.owner_user_id
        WHERE {' AND '.join(clauses)}
        ORDER BY s.session_date, s.scheduled_time, s.session_id
        """,
        params,
    ).fetchall()


def list_attempts(connection, user_id, module_id=None):
    clauses = ["a.user_id = ?", "a.status IN ('Evaluated', 'Submitted')"]
    params = [user_id]
    if module_id is not None:
        clauses.append("t.module_id = ?")
        params.append(module_id)
    return connection.execute(
        f"""
        SELECT a.rowid AS attempt_order, a.attempt_id, a.test_id, t.session_id,
               a.score, a.percentage,
               a.submitted_at, a.started_at, a.weak_areas_json,
               t.module_id, t.category, t.topic, t.title
        FROM test_attempts a
        JOIN tests t ON t.test_id = a.test_id
        WHERE {' AND '.join(clauses)}
        ORDER BY a.rowid
        """,
        params,
    ).fetchall()


def list_notes(connection, user_id, module_id=None):
    clauses = ["user_id = ?"]
    params = [user_id]
    if module_id is not None:
        clauses.append("module_id = ?")
        params.append(module_id)
    return connection.execute(
        f"""
        SELECT note_id, module_id, category, topic, title, saved_at
        FROM learning_notes
        WHERE {' AND '.join(clauses)}
        ORDER BY saved_at DESC, note_id DESC
        """,
        params,
    ).fetchall()


def parse_weak_areas(value):
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]


def list_interviews(connection, user_id, module_id=None):
    clauses = ["i.user_id = ?", "i.status = 'Completed'"]
    params = [user_id]
    if module_id is not None:
        clauses.append("i.module_id = ?")
        params.append(module_id)
    return connection.execute(
        f"""
        SELECT i.interview_session_id, i.module_id, i.session_id, i.mode, i.topic,
               i.completed_at, AVG(e.score) AS score
        FROM interview_sessions i
        JOIN interview_questions q ON q.interview_session_id=i.interview_session_id
        JOIN interview_answers a ON a.question_id=q.question_id
        JOIN interview_evaluations e ON e.answer_id=a.answer_id
        WHERE {' AND '.join(clauses)}
        GROUP BY i.interview_session_id
        ORDER BY i.completed_at, i.interview_session_id
        """,
        params,
    ).fetchall()


def list_interview_weaknesses(connection, user_id, module_id=None):
    clauses = ["i.user_id = ?", "i.status = 'Completed'"]
    params = [user_id]
    if module_id is not None:
        clauses.append("i.module_id = ?")
        params.append(module_id)
    rows = connection.execute(
        f"""
        SELECT e.weaknesses_json, i.mode, i.topic, i.completed_at
        FROM interview_sessions i
        JOIN interview_questions q ON q.interview_session_id=i.interview_session_id
        JOIN interview_answers a ON a.question_id=q.question_id
        JOIN interview_evaluations e ON e.answer_id=a.answer_id
        WHERE {' AND '.join(clauses)}
        """,
        params,
    ).fetchall()
    return rows
