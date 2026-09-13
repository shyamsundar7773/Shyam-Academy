import json
import re
import sqlite3
from datetime import datetime, timezone

from ai.gateway import AIGateway, AIProviderError
from database.repositories import test_repository as repo
from models.test_plan import QUESTION_TYPES, TestPlan, TestQuestion

VALID_DIFFICULTIES = {"Beginner", "Intermediate", "Advanced"}
TEST_CONTEXTS = {
    "HR Screening": "hr_screening",
    "MCQ Technical Test": "mcq_technical",
    "Coding Technical Test": "coding_technical",
    "Problem Solving Test": "problem_solving",
}


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Test field '{field}' is required.")
    return value.strip()


def _parse_questions(raw_questions):
    if not isinstance(raw_questions, list) or not raw_questions:
        raise ValueError("The test must contain at least one question.")
    questions = []
    seen = set()
    for index, raw in enumerate(raw_questions, 1):
        if not isinstance(raw, dict):
            raise ValueError("Each question must be an object.")
        question_type = _text(raw.get("question_type"), "question_type").lower()
        if question_type not in QUESTION_TYPES - {"mixed"}:
            raise ValueError(f"Question {index} has an invalid question type.")
        text = _text(raw.get("question_text"), "question_text")
        fingerprint = re.sub(r"\s+", " ", text.casefold())
        if fingerprint in seen:
            raise ValueError("The test contains duplicate questions.")
        seen.add(fingerprint)
        options = raw.get("options", [])
        if not isinstance(options, list) or any(not isinstance(item, str) or not item.strip() for item in options):
            raise ValueError(f"Question {index} has invalid options.")
        options = [item.strip() for item in options]
        if question_type in {"mcq", "multiple_select"} and len(options) < 2:
            raise ValueError(f"Question {index} requires at least two options.")
        correct = raw.get("correct_answer")
        if question_type == "multiple_select":
            if not isinstance(correct, list) or not correct or any(item not in options for item in correct):
                raise ValueError(f"Question {index} has an invalid answer key.")
        elif not isinstance(correct, str) or not correct.strip():
            raise ValueError(f"Question {index} has an invalid answer key.")
        points = raw.get("points", 1)
        if isinstance(points, bool) or not isinstance(points, (int, float)) or points <= 0:
            raise ValueError(f"Question {index} has invalid points.")
        order = raw.get("order_index", index)
        if not isinstance(order, int) or order < 1:
            raise ValueError(f"Question {index} has invalid order.")
        questions.append(TestQuestion(
            order, question_type, text, options, correct,
            _text(raw.get("explanation"), "explanation"),
            float(points), _text(raw.get("weak_area", ""), "weak_area")
            if raw.get("weak_area", "") else "",
        ))
    questions.sort(key=lambda item: item.order_index)
    if [q.order_index for q in questions] != list(range(1, len(questions) + 1)):
        raise ValueError("Question order must be consecutive starting at 1.")
    return questions


def parse_test(response: str) -> TestPlan:
    if not isinstance(response, str) or not response.strip():
        raise ValueError("The AI returned an empty test.")
    raw = _extract_json_object(response)
    if not isinstance(raw, dict):
        raise ValueError("The AI test response must be an object.")
    difficulty = _text(raw.get("difficulty"), "difficulty").title()
    if difficulty not in VALID_DIFFICULTIES:
        raise ValueError("The test has an invalid difficulty.")
    duration = raw.get("duration_minutes")
    if duration is not None and (isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0):
        raise ValueError("The test duration must be a positive number of minutes.")
    questions = _parse_questions(raw.get("questions"))
    return TestPlan(
        _text(raw.get("title"), "title"),
        _text(raw.get("description"), "description"),
        _text(raw.get("category"), "category"),
        _text(raw.get("topic"), "topic"),
        difficulty,
        duration,
        questions,
    )


def _extract_json_object(response: str) -> dict:
    """Accept JSON returned directly, in a fence, or with short surrounding prose."""
    candidate = response.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate).strip()
    try:
        raw = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("The AI test response did not contain valid JSON.")
        try:
            raw = json.loads(candidate[start:end + 1])
        except json.JSONDecodeError as error:
            raise ValueError("The AI test response contained malformed JSON.") from error
    if not isinstance(raw, dict):
        raise ValueError("The AI test response must be a JSON object.")
    return raw


def generate_test(gateway: AIGateway, request: str) -> TestPlan:
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Describe the test you want first.")
    try:
        response = gateway.generate_test(request.strip())
    except AIProviderError:
        raise
    except Exception as error:
        raise AIProviderError("The AI provider is currently unavailable.") from error
    return parse_test(response)


def create_test(connection, user_id, plan, module_id=None, session_id=None, context_id=""):
    if module_id is not None:
        module = connection.execute(
            "SELECT module_id FROM modules WHERE module_id=? AND owner_user_id=?",
            (module_id, user_id),
        ).fetchone()
        if module is None:
            raise ValueError("The selected module could not be found.")
    if session_id is not None:
        session = connection.execute(
            """SELECT session_id,module_id,owner_user_id,category,topic
            FROM sessions WHERE session_id=? AND owner_user_id=?""",
            (session_id, user_id),
        ).fetchone()
        if session is None:
            raise ValueError("The selected timetable session could not be found.")
        if module_id is not None and int(session["module_id"]) != int(module_id):
            raise ValueError("The test module does not match its timetable session.")
        module_id = int(session["module_id"])
    return repo.create_test(
        connection, user_id, plan, module_id, session_id, context_id
    )


def public_test(connection, test_id, user_id):
    test = repo.get_test(connection, test_id, user_id)
    if test is None:
        raise ValueError("The selected test could not be found.")
    return test, [
        {
            "question_id": row["question_id"],
            "order_index": row["order_index"],
            "question_type": row["question_type"],
            "question_text": row["question_text"],
            "options": json.loads(row["options_json"]),
            "points": row["points"],
        }
        for row in repo.list_questions(connection, test_id)
    ]


def start_attempt(connection, test_id, user_id):
    return repo.create_attempt(connection, test_id, user_id)


def _normalize(value):
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _deterministic_evaluation(question, answer):
    qtype = question["question_type"]
    expected = json.loads(question["correct_answer_json"])
    if qtype == "multiple_select":
        correct = set(answer or []) == set(expected)
    else:
        correct = _normalize(answer) == _normalize(expected)
    return {
        "correct": correct,
        "points_awarded": float(question["points"]) if correct else 0.0,
        "feedback": "Correct." if correct else "Review this topic and compare your approach with the expected answer.",
        "explanation": question["explanation"],
    }


def evaluate_test(connection, gateway, attempt_id, user_id, submitted_answers):
    attempt = repo.get_attempt(connection, attempt_id, user_id)
    if attempt is None:
        raise ValueError("The selected attempt could not be found.")
    if attempt["status"] in {"Submitted", "Evaluated", "Expired"}:
        raise ValueError("This test attempt has already been submitted.")
    questions = repo.list_questions(connection, attempt["test_id"])
    evaluations = []
    for question in questions:
        answer = submitted_answers.get(question["question_id"])
        if answer in (None, "", []):
            evaluation = {
                "correct": False, "points_awarded": 0.0,
                "feedback": "This question was unanswered.",
                "explanation": question["explanation"],
            }
        elif question["question_type"] in {"mcq", "multiple_select"}:
            evaluation = _deterministic_evaluation(question, answer)
        else:
            try:
                response = gateway.evaluate_test_answer(json.dumps({
                    "question": question["question_text"],
                    "expected_answer": json.loads(question["correct_answer_json"]),
                    "user_answer": answer,
                    "topic": attempt["topic"],
                }))
                raw = json.loads(response)
                evaluation = {
                    "correct": bool(raw.get("correct")),
                    "points_awarded": min(float(raw.get("points_awarded", 0)), float(question["points"])),
                    "feedback": _text(raw.get("feedback"), "feedback"),
                    "explanation": question["explanation"],
                }
            except Exception as error:
                connection.rollback()
                raise AIProviderError("The AI evaluator is currently unavailable.") from error
        repo.save_answer(connection, attempt_id, question["question_id"], answer, evaluation)
        evaluations.append((question, evaluation))

    total_points = sum(float(q["points"]) for q in questions)
    score = sum(result["points_awarded"] for _, result in evaluations)
    weak_areas = sorted({q["weak_area"] for q, result in evaluations if not result["correct"] and q["weak_area"]})
    percentage = round(score / total_points * 100, 1) if total_points else 0.0
    summary = f"{score:g} of {total_points:g} points earned."
    repo.submit_attempt(connection, attempt_id, user_id, score, percentage, summary, weak_areas)
    return {
        "score": score, "total_points": total_points, "percentage": percentage,
        "weak_areas": weak_areas, "evaluations": evaluations,
    }


def get_result(connection, attempt_id, user_id):
    attempt = repo.get_attempt(connection, attempt_id, user_id)
    if attempt is None:
        raise ValueError("The selected result could not be found.")
    return attempt, repo.list_answers(connection, attempt_id)


def attempt_expired(attempt, now=None):
    if not attempt["duration_minutes"]:
        return False
    now = now or datetime.now(timezone.utc)
    started = datetime.fromisoformat(attempt["started_at"])
    return (now - started).total_seconds() >= int(attempt["duration_minutes"]) * 60


def expire_attempt(connection, attempt_id, user_id):
    repo.expire_attempt(connection, attempt_id, user_id)


def completed_test_event(attempt, result):
    return {
        "event": "TestCompleted",
        "user_id": attempt["user_id"],
        "module_id": attempt["module_id"],
        "session_id": attempt["session_id"],
        "test_id": attempt["test_id"],
        "attempt_id": attempt["attempt_id"],
        "score": result["score"],
        "percentage": result["percentage"],
        "weak_areas": result["weak_areas"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
