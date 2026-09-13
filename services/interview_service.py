import json
from datetime import datetime, timezone

from ai.gateway import AIGateway, AIProviderError
from database.repositories import interview_repository as repo
from models.interview import (
    INTERVIEW_MODES,
    QUESTION_TYPES,
    InterviewEvaluation,
    InterviewPlan,
    InterviewQuestionPlan,
)

DIFFICULTIES = {"Beginner", "Intermediate", "Advanced"}
INTERVIEW_CONTEXTS = {
    "HR Screening": "hr_screening",
    "Technical Interview": "technical_interview",
    "Managerial Round": "managerial_round",
}


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Interview field '{field}' is required.")
    return value.strip()


def _bounded(value, field):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Interview field '{field}' must be numeric.") from error
    if not 0 <= number <= 100:
        raise ValueError(f"Interview field '{field}' must be between 0 and 100.")
    return number


def parse_interview(response):
    if not isinstance(response, str) or not response.strip():
        raise ValueError("The AI returned an empty interview question.")
    raw = _extract_json_object(response, "interview response")
    if not isinstance(raw, dict):
        raise ValueError("The interview response must be an object.")
    mode = _text(raw.get("mode"), "mode")
    if mode not in INTERVIEW_MODES:
        raise ValueError("The interview mode is invalid.")
    difficulty = _text(raw.get("difficulty"), "difficulty").title()
    if difficulty not in DIFFICULTIES:
        raise ValueError("The interview difficulty is invalid.")
    questions = raw.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("The interview must contain at least one question.")
    parsed = []
    seen = set()
    for item in questions:
        if not isinstance(item, dict):
            raise ValueError("Each interview question must be an object.")
        text = _text(item.get("question_text"), "question_text")
        if text.casefold() in seen:
            raise ValueError("The interview contains duplicate questions.")
        seen.add(text.casefold())
        question_type = _text(item.get("question_type"), "question_type")
        if question_type not in QUESTION_TYPES:
            raise ValueError("The interview question type is invalid.")
        points = item.get("expected_points", [])
        if not isinstance(points, list) or any(not isinstance(point, str) for point in points):
            raise ValueError("Interview expected points must be a list of strings.")
        parsed.append(InterviewQuestionPlan(
            text, question_type, _text(item.get("topic"), "topic"),
            [point.strip() for point in points if point.strip()],
        ))
    return InterviewPlan(
        _text(raw.get("title"), "title"), mode, difficulty,
        _text(raw.get("topic"), "topic"), parsed,
    )


def _extract_json_object(response: str, label: str) -> dict:
    candidate = response.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1]
        candidate = candidate.rsplit("```", 1)[0].strip()
    try:
        raw = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(f"The AI {label} did not contain valid JSON.")
        try:
            raw = json.loads(candidate[start:end + 1])
        except json.JSONDecodeError as error:
            raise ValueError(f"The AI {label} contained malformed JSON.") from error
    if not isinstance(raw, dict):
        raise ValueError(f"The AI {label} must be a JSON object.")
    return raw


def parse_evaluation(response):
    if not isinstance(response, str) or not response.strip():
        raise ValueError("The AI returned an empty interview evaluation.")
    raw = _extract_json_object(response, "interview evaluation")
    if not isinstance(raw, dict):
        raise ValueError("The interview evaluation must be an object.")
    return InterviewEvaluation(
        _bounded(raw.get("score"), "score"),
        _bounded(raw.get("correctness"), "correctness"),
        _bounded(raw.get("relevance"), "relevance"),
        _bounded(raw.get("clarity"), "clarity"),
        _bounded(raw.get("technical_depth"), "technical_depth"),
        _bounded(raw.get("communication_quality"), "communication_quality"),
        _list(raw.get("strengths"), "strengths"),
        _list(raw.get("weaknesses"), "weaknesses"),
        _list(raw.get("missing_points"), "missing_points"),
        _list(raw.get("corrections"), "corrections"),
        _text(raw.get("suggested_answer"), "suggested_answer"),
        _text(raw.get("feedback"), "feedback"),
    )


def _list(value, field):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Interview field '{field}' must be a list of strings.")
    return [item.strip() for item in value if item.strip()]


def generate_interview(gateway: AIGateway, user_id, mode, difficulty, topic, prompt=""):
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("A user identity is required.")
    if mode not in INTERVIEW_MODES:
        raise ValueError("The interview mode is invalid.")
    if difficulty not in DIFFICULTIES:
        raise ValueError("The interview difficulty is invalid.")
    if not topic.strip():
        raise ValueError("Interview topic is required.")
    request = (
        f"User: {user_id}\nMode: {mode}\nDifficulty: {difficulty}\n"
        f"Topic: {topic.strip()}\nRequest: {prompt.strip()}"
    )
    try:
        return parse_interview(gateway.generate_interview(request))
    except AIProviderError:
        raise
    except Exception as error:
        raise AIProviderError("The interview provider is currently unavailable.") from error


def create_interview(connection, user_id, plan, module_id=None, session_id=None, context_id=""):
    if session_id is not None:
        session = connection.execute(
            "SELECT module_id,category,topic FROM sessions WHERE session_id=? AND owner_user_id=?",
            (session_id, user_id),
        ).fetchone()
        if session is None:
            raise ValueError("The selected timetable session could not be found.")
        module_id = int(session["module_id"])
    if module_id is not None and connection.execute(
        "SELECT module_id FROM modules WHERE module_id=? AND owner_user_id=?",
        (module_id, user_id),
    ).fetchone() is None:
        raise ValueError("The selected module could not be found.")
    return repo.create_session(
        connection, user_id, plan, module_id, session_id, context_id
    )[0]


def submit_answer(connection, gateway, interview_session_id, question_id, user_id, answer):
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("Enter an answer before submitting.")
    question = repo.get_question(connection, question_id)
    if question is None:
        raise ValueError("The selected interview question could not be found.")
    answer_id = repo.save_answer(
        connection, interview_session_id, question_id, user_id, answer.strip()
    )
    request = json.dumps({
        "question": question["question_text"],
        "question_type": question["question_type"],
        "expected_points": json.loads(question["expected_points_json"]),
        "answer": answer.strip(),
    })
    try:
        evaluation = parse_evaluation(gateway.evaluate_interview(request))
    except AIProviderError:
        raise
    except Exception as error:
        raise AIProviderError("The interview evaluator is currently unavailable.") from error
    repo.save_evaluation(connection, answer_id, evaluation)
    return evaluation


def interview_action(gateway, action, topic, context):
    if action not in {"Explain Again", "Give Example", "Give Interview Tip",
                      "Show Common Mistakes", "Show Strong Answer Structure"}:
        raise ValueError("Unsupported interview action.")
    try:
        return gateway.interview_action(
            f"Action: {action}\nTopic: {topic}\nContext: {context}"
        )
    except Exception as error:
        raise AIProviderError("The interview coach is currently unavailable.") from error


def complete_interview(connection, interview_session_id, user_id):
    repo.complete_session(connection, interview_session_id, user_id)


def interview_completed_event(connection, interview_session_id, user_id):
    session = repo.get_session(connection, interview_session_id, user_id)
    if session is None:
        raise ValueError("The selected interview session could not be found.")
    answers = repo.list_answers(connection, interview_session_id, user_id)
    evaluations = [row for row in answers if row["score"] is not None]
    scores = [float(row["score"]) for row in evaluations]
    weaknesses = []
    for row in evaluations:
        weaknesses.extend(json.loads(row["weaknesses_json"] or "[]"))
    return {
        "event": "InterviewCompleted",
        "user_id": user_id,
        "interview_session_id": interview_session_id,
        "module_id": session["module_id"],
        "session_id": session["session_id"],
        "mode": session["mode"],
        "question_count": len(answers),
        "score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "weaknesses": sorted(set(weaknesses)),
        "completed_at": session["completed_at"],
    }
