import json
from datetime import datetime, timezone
from uuid import uuid4


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_session(connection, user_id, plan, module_id=None, session_id=None, context_id=""):
    interview_session_id = str(uuid4())
    now = _now()
    connection.execute(
        """INSERT INTO interview_sessions
        (interview_session_id,user_id,module_id,session_id,context_id,title,mode,difficulty,topic,
         status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (interview_session_id, user_id, module_id, session_id, context_id, plan.title,
         plan.mode, plan.difficulty, plan.topic, "In Progress", now, now),
    )
    question_ids = []
    for index, question in enumerate(plan.questions, 1):
        question_id = str(uuid4())
        question_ids.append(question_id)
        connection.execute(
            """INSERT INTO interview_questions
            (question_id,interview_session_id,order_index,question_text,question_type,
             topic,expected_points_json)
            VALUES (?,?,?,?,?,?,?)""",
            (question_id, interview_session_id, index, question.question_text,
             question.question_type, question.topic, json.dumps(question.expected_points)),
        )
    connection.commit()
    return interview_session_id, question_ids


def get_session(connection, interview_session_id, user_id):
    return connection.execute(
        """SELECT * FROM interview_sessions
        WHERE interview_session_id=? AND user_id=?""",
        (interview_session_id, user_id),
    ).fetchone()


def list_sessions(connection, user_id):
    return connection.execute(
        """SELECT i.*, COUNT(q.question_id) AS question_count,
        AVG(e.score) AS average_score
        FROM interview_sessions i
        LEFT JOIN interview_questions q ON q.interview_session_id=i.interview_session_id
        LEFT JOIN interview_answers a ON a.question_id=q.question_id
        LEFT JOIN interview_evaluations e ON e.answer_id=a.answer_id
        WHERE i.user_id=?
        GROUP BY i.interview_session_id
        ORDER BY i.created_at DESC""",
        (user_id,),
    ).fetchall()


def list_questions(connection, interview_session_id):
    return connection.execute(
        """SELECT * FROM interview_questions
        WHERE interview_session_id=? ORDER BY order_index""",
        (interview_session_id,),
    ).fetchall()


def get_question(connection, question_id):
    return connection.execute(
        "SELECT * FROM interview_questions WHERE question_id=?",
        (question_id,),
    ).fetchone()


def save_answer(connection, interview_session_id, question_id, user_id, answer):
    session = get_session(connection, interview_session_id, user_id)
    if session is None:
        raise ValueError("The selected interview session could not be found.")
    existing = connection.execute(
        """SELECT answer_id FROM interview_answers
        WHERE interview_session_id=? AND question_id=?""",
        (interview_session_id, question_id),
    ).fetchone()
    if existing:
        raise ValueError("This interview answer has already been submitted.")
    answer_id = str(uuid4())
    connection.execute(
        """INSERT INTO interview_answers
        (answer_id,interview_session_id,question_id,user_id,answer,submitted_at)
        VALUES (?,?,?,?,?,?)""",
        (answer_id, interview_session_id, question_id, user_id, answer, _now()),
    )
    connection.commit()
    return answer_id


def save_evaluation(connection, answer_id, evaluation):
    connection.execute(
        """INSERT INTO interview_evaluations
        (evaluation_id,answer_id,score,correctness,relevance,clarity,technical_depth,
         communication_quality,strengths_json,weaknesses_json,missing_points_json,
         corrections_json,suggested_answer,feedback,evaluated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (str(uuid4()), answer_id, evaluation.score, evaluation.correctness,
         evaluation.relevance, evaluation.clarity, evaluation.technical_depth,
         evaluation.communication_quality, json.dumps(evaluation.strengths),
         json.dumps(evaluation.weaknesses), json.dumps(evaluation.missing_points),
         json.dumps(evaluation.corrections), evaluation.suggested_answer,
         evaluation.feedback, _now()),
    )
    connection.commit()


def list_answers(connection, interview_session_id, user_id):
    if get_session(connection, interview_session_id, user_id) is None:
        raise ValueError("The selected interview session could not be found.")
    return connection.execute(
        """SELECT q.order_index,q.question_id,q.question_text,q.question_type,q.topic,
        a.answer_id,a.answer,a.submitted_at,e.score,e.correctness,e.relevance,e.clarity,
        e.technical_depth,e.communication_quality,e.strengths_json,e.weaknesses_json,
        e.missing_points_json,e.corrections_json,e.suggested_answer,e.feedback,e.evaluated_at
        FROM interview_questions q
        JOIN interview_answers a ON a.question_id=q.question_id
        LEFT JOIN interview_evaluations e ON e.answer_id=a.answer_id
        WHERE q.interview_session_id=? ORDER BY q.order_index""",
        (interview_session_id,),
    ).fetchall()


def complete_session(connection, interview_session_id, user_id):
    session = get_session(connection, interview_session_id, user_id)
    if session is None:
        raise ValueError("The selected interview session could not be found.")
    connection.execute(
        """UPDATE interview_sessions SET status='Completed',completed_at=?,updated_at=?
        WHERE interview_session_id=? AND user_id=?""",
        (_now(), _now(), interview_session_id, user_id),
    )
    connection.commit()
