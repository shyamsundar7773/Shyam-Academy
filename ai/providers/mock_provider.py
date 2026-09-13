import json
import re
from datetime import date, timedelta

from ai.gateway import AIGateway, ClassroomContext


class MockProvider(AIGateway):
    """Deterministic local provider for development and UI testing."""

    def generate_timetable(self, prompt: str) -> str:
        module_match = re.search(
            r"(?:as|for|learn)\s+(?:a\s+)?([A-Za-z][A-Za-z ]{2,40}?)(?:\s+in|\s+over|\s+plan|\.|$)",
            prompt,
            re.IGNORECASE,
        )
        module_name = (module_match.group(1).strip() if module_match else "SQL Developer")
        days_match = re.search(r"(\d+)\s*[- ]?day", prompt, re.IGNORECASE)
        days = max(1, min(int(days_match.group(1)) if days_match else 5, 30))
        start = date.today() + timedelta(days=1)
        topics = [
            ("Today Learning", "Foundations"),
            ("Level 1", "Core concepts"),
            ("Level 2", "Applied practice"),
            ("Problem Solving", "Practice problems"),
            ("Interview Preparation", "Interview preparation"),
        ]
        sessions = []
        for index in range(days):
            session_date = (start + timedelta(days=index)).isoformat()
            category, topic = topics[index % len(topics)]
            sessions.append(
                {
                    "session_date": session_date,
                    "scheduled_time": "07:00 PM",
                    "category": category,
                    "topic": f"{module_name} {topic}",
                    "session_title": f"{topic} lesson",
                    "prompt": (
                        f"Teach {module_name} {topic} with a clear explanation, "
                        "realistic examples, common mistakes, and practice questions."
                    ),
                    "day_number": index + 1,
                    "status": "Scheduled",
                }
            )
        return json.dumps(
            {
                "title": f"{module_name} learning plan",
                "module_name": module_name,
                "description": f"Free-form {module_name} preparation plan",
                "start_date": start.isoformat(),
                "end_date": (start + timedelta(days=days - 1)).isoformat(),
                "timezone": "local",
                "assumptions": [
                    "The plan starts tomorrow.",
                    "One evening session is scheduled per day.",
                    "The development provider uses a progressive category rotation.",
                ],
                "sessions": sessions,
            }
        )

    def generate_advanced(self, task_type: str, prompt: str) -> str:
        """Return a deterministic structured response for orchestration tests."""
        data = {
            "answer": (
                f"Deterministic guidance for {task_type.replace('_', ' ').lower()}. "
                "Use the supplied evidence, take one bounded next step, and review the result."
            ),
            "evidence": ["The response used the bounded cross-system context."],
            "suggested_actions": ["Review the evidence and choose an explicit next step."],
            "proposals": [],
        }
        if task_type in {"STUDY_PLAN", "DAILY_PLAN"}:
            data["answer"] = "A bounded study plan is ready for your review; it does not rewrite your timetable."
            data["proposals"] = [{
                "action_type": "CREATE_STUDY_PLAN_PROPOSAL",
                "target_reference": "daily-plan",
                "summary": "Review a proposed study plan",
                "payload": {"title": "Bounded study plan", "plan": [
                    {"period": "today", "activity": "Review one weak area"}
                ]},
            }]
        elif task_type == "ROUTINE_ANALYSIS":
            data["proposals"] = [{
                "action_type": "CREATE_ROUTINE_PROPOSAL",
                "target_reference": "routine-review",
                "summary": "Review a routine suggestion",
                "payload": {
                    "name": "Focused review block", "description": "Optional review block",
                    "category": "CUSTOM", "frequency": "DAILY",
                    "start_date": "2026-09-12", "time_local": "19:00",
                    "duration_minutes": 20, "timezone": "Asia/Kolkata",
                    "selected_days": [],
                },
            }]
        return json.dumps(data)

    def generate_test(self, prompt: str) -> str:
        topic = prompt.strip().split(" on ", 1)[-1].rstrip(".") or "core concepts"
        questions = [
            {
                "order_index": 1,
                "question_type": "mcq",
                "question_text": f"Which statement best describes {topic}?",
                "options": ["A practical concept", "A password", "A file extension", "A keyboard"],
                "correct_answer": "A practical concept",
                "explanation": f"{topic} should be understood as a practical learning concept.",
                "points": 1,
                "weak_area": topic,
            },
            {
                "order_index": 2,
                "question_type": "multiple_select",
                "question_text": f"Which are useful ways to learn {topic}?",
                "options": ["Study examples", "Practice problems", "Ignore feedback", "Review mistakes"],
                "correct_answer": ["Study examples", "Practice problems", "Review mistakes"],
                "explanation": "Examples, practice, and review reinforce durable understanding.",
                "points": 2,
                "weak_area": topic,
            },
            {
                "order_index": 3,
                "question_type": "short_answer",
                "question_text": f"In one sentence, explain why {topic} matters.",
                "options": [],
                "correct_answer": f"{topic} helps solve practical problems.",
                "explanation": "A strong answer connects the topic to practical problem solving.",
                "points": 2,
                "weak_area": topic,
            },
        ]
        return json.dumps({
            "title": f"{topic} assessment",
            "description": f"A focused assessment of {topic}.",
            "category": "Test",
            "topic": topic,
            "difficulty": "Intermediate",
            "duration_minutes": 20,
            "questions": questions,
        })

    def generate_routine(self, prompt: str) -> str:
        return json.dumps({
            "name": "Personal routine",
            "description": prompt.strip(),
            "category": "CUSTOM",
            "frequency": "DAILY",
            "start_date": "2026-09-12",
            "time_local": "19:00",
            "duration_minutes": 20,
            "timezone": "Asia/Kolkata",
            "selected_days": [],
        })

    def evaluate_test_answer(self, prompt: str) -> str:
        return json.dumps({
            "correct": False,
            "points_awarded": 0,
            "feedback": "Compare your answer with the expected concept and revise the weak area.",
        })

    def generate_interview(self, prompt: str) -> str:
        mode = "SQL Interview" if "sql" in prompt.lower() else "Technical Interview"
        topic = prompt.split("Topic:", 1)[-1].strip().split(".", 1)[0] or "core concepts"
        questions = [
            {
                "question_text": f"Explain {topic} and describe one practical example.",
                "question_type": "SQL" if mode == "SQL Interview" else "Conceptual",
                "topic": topic,
                "expected_points": ["clear definition", "practical example", "tradeoffs"],
            }
        ]
        return json.dumps({
            "title": f"{mode}: {topic}",
            "mode": mode,
            "difficulty": "Intermediate",
            "topic": topic,
            "questions": questions,
        })

    def evaluate_interview(self, prompt: str) -> str:
        return json.dumps({
            "score": 75,
            "correctness": 75,
            "relevance": 80,
            "clarity": 75,
            "technical_depth": 70,
            "communication_quality": 80,
            "strengths": ["Clear attempt", "Relevant direction"],
            "weaknesses": ["Add a concrete example"],
            "missing_points": ["Tradeoffs"],
            "corrections": ["Explain the reasoning step by step."],
            "suggested_answer": "Define the concept, show a practical example, and explain tradeoffs.",
            "feedback": "Good foundation. Add specificity and explain the reasoning.",
        })

    def interview_action(self, prompt: str) -> str:
        return f"## Interview coaching\n\n{prompt}\n\nUse a structured answer: context, reasoning, example, and tradeoffs."

    def mentor_response(self, prompt: str) -> str:
        return json.dumps({
            "response": (
                "Based on your current Academy activity, focus first on the highest-priority "
                "scheduled or weak area shown in the evidence. Use a short study block, "
                "practice one example, and review the result."
            ),
            "recommendations": ["Follow the highest-priority evidence-backed recommendation."],
            "evidence": ["The Mentor used your current Progress snapshot and recent activity."],
            "next_actions": ["Review the recommended topic.", "Complete one practice exercise."],
        })

    def generate_lesson(self, prompt: str, context: ClassroomContext) -> str:
        return (
            f"# {context.topic}\n\n"
            f"## Topic overview\n{prompt}\n\n"
            "## Learning objectives\n"
            f"- Understand the core ideas behind {context.topic}.\n"
            "- Apply the concept to a practical problem.\n"
            "- Explain the result clearly in an interview.\n\n"
            "## Core explanation\n"
            f"This development lesson introduces **{context.topic}** using a practical, "
            "step-by-step approach.\n\n"
            "## Example\n"
            "Start with a small example, inspect each step, and verify the expected result "
            "before moving to a larger problem.\n\n"
            "## Common mistakes\n"
            "- Skipping assumptions and expected results.\n"
            "- Trying to memorize syntax without understanding the reasoning.\n\n"
            "## Quick recap\n"
            f"Practice {context.topic}, explain your reasoning, and check your output."
        )

    def ask_followup(self, prompt, context, lesson, history):
        return (
            f"Regarding **{context.topic}**: {prompt}\n\n"
            "Use the lesson's core idea, work through one concrete example, and verify "
            "the result step by step."
        )

    def generate_explanation(self, context, lesson):
        return (
            f"## Clearer explanation of {context.topic}\n\n"
            f"Think of **{context.topic}** as a sequence of small decisions. "
            "First identify the inputs, then apply the rule, and finally check the output."
        )

    def generate_example(self, context, lesson):
        return (
            f"## Practical example: {context.topic}\n\n"
            "1. Define a small realistic scenario.\n"
            "2. Apply the concept one step at a time.\n"
            "3. Compare the expected result with the observed result.\n\n"
            "This example is generated locally for classroom UI testing."
        )
