import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_test(connection, user_id, plan, module_id=None, session_id=None, context_id=""):
    test_id = str(uuid4())
    now = _now()
    connection.execute(
        """INSERT INTO tests
        (test_id,user_id,module_id,session_id,context_id,title,description,category,topic,
         difficulty,total_questions,duration_minutes,status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (test_id, user_id, module_id, session_id, context_id, plan.title, plan.description,
         plan.category, plan.topic, plan.difficulty, plan.total_questions,
         plan.duration_minutes, "Ready", now, now),
    )
    question_ids = []
    for question in plan.questions:
        question_id = str(uuid4())
        question_ids.append(question_id)
        connection.execute(
            """INSERT INTO test_questions
            (question_id,test_id,order_index,question_type,question_text,options_json,
             correct_answer_json,explanation,points,weak_area)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (question_id, test_id, question.order_index, question.question_type,
             question.question_text, json.dumps(question.options),
             json.dumps(question.correct_answer), question.explanation,
             question.points, question.weak_area),
        )
    connection.commit()
    return test_id


def get_test(connection, test_id, user_id):
    return connection.execute(
        "SELECT * FROM tests WHERE test_id=? AND user_id=?", (test_id, user_id)
    ).fetchone()


def list_tests(connection, user_id):
    return connection.execute(
        "SELECT * FROM tests WHERE user_id=? ORDER BY created_at DESC", (user_id,)
    ).fetchall()


def list_questions(connection, test_id):
    return connection.execute(
        "SELECT * FROM test_questions WHERE test_id=? ORDER BY order_index", (test_id,)
    ).fetchall()


def get_question(connection, question_id):
    return connection.execute(
        "SELECT * FROM test_questions WHERE question_id=?", (question_id,)
    ).fetchone()


def create_attempt(connection, test_id, user_id):
    if get_test(connection, test_id, user_id) is None:
        raise ValueError("The selected test could not be found.")
    attempt_id = str(uuid4())
    connection.execute(
        "INSERT INTO test_attempts (attempt_id,test_id,user_id,started_at) VALUES (?,?,?,?)",
        (attempt_id, test_id, user_id, _now()),
    )
    connection.commit()
    return attempt_id


def get_attempt(connection, attempt_id, user_id):
    return connection.execute(
        """SELECT a.*, t.title, t.topic, t.difficulty, t.total_questions,
        t.duration_minutes, t.module_id, t.session_id
        FROM test_attempts a JOIN tests t ON t.test_id=a.test_id
        WHERE a.attempt_id=? AND a.user_id=?""", (attempt_id, user_id)
    ).fetchone()


def list_attempts(connection, user_id):
    return connection.execute(
        """SELECT a.*, t.title, t.topic, t.difficulty
        FROM test_attempts a JOIN tests t ON t.test_id=a.test_id
        WHERE a.user_id=? ORDER BY a.started_at DESC""", (user_id,)
    ).fetchall()


def save_answer(connection, attempt_id, question_id, answer, evaluation):
    connection.execute(
        """INSERT INTO test_answers
        (answer_id,attempt_id,question_id,answer_json,is_correct,points_awarded,feedback,explanation)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(attempt_id,question_id) DO UPDATE SET
        answer_json=excluded.answer_json,is_correct=excluded.is_correct,
        points_awarded=excluded.points_awarded,feedback=excluded.feedback,
        explanation=excluded.explanation""",
        (str(uuid4()), attempt_id, question_id, json.dumps(answer),
         None if evaluation["correct"] is None else int(evaluation["correct"]),
         evaluation["points_awarded"], evaluation["feedback"], evaluation["explanation"]),
    )


def list_answers(connection, attempt_id):
    return connection.execute(
        "SELECT * FROM test_answers WHERE attempt_id=?", (attempt_id,)
    ).fetchall()


def submit_attempt(connection, attempt_id, user_id, score, percentage, summary, weak_areas):
    attempt = get_attempt(connection, attempt_id, user_id)
    if attempt is None:
        raise ValueError("The selected attempt could not be found.")
    if attempt["status"] in {"Submitted", "Evaluated", "Expired"}:
        raise ValueError("This test attempt has already been submitted.")
    connection.execute(
        """UPDATE test_attempts SET submitted_at=?,status='Evaluated',score=?,
        percentage=?,evaluation_summary=?,weak_areas_json=? WHERE attempt_id=? AND user_id=?""",
        (_now(), score, percentage, summary, json.dumps(weak_areas), attempt_id, user_id),
    )
    connection.commit()


def expire_attempt(connection, attempt_id, user_id):
    attempt = get_attempt(connection, attempt_id, user_id)
    if attempt is None:
        raise ValueError("The selected attempt could not be found.")
    if attempt["status"] in {"Submitted", "Evaluated", "Expired"}:
        return
    connection.execute(
        "UPDATE test_attempts SET status='Expired', submitted_at=? WHERE attempt_id=? AND user_id=?",
        (_now(), attempt_id, user_id),
    )
    connection.commit()
