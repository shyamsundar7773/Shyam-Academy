from datetime import datetime

from models.mentor import MentorRecommendation


def get_next_learning_recommendations(
    snapshot, upcoming_sessions=None, missed_sessions=None, routine_metrics=None
):
    recommendations = []
    for session in missed_sessions or []:
        recommendations.append(MentorRecommendation(
            "HIGH", session.get("module_id"), session.get("module_name"),
            session.get("category"), session.get("topic", "Unknown topic"),
            "Recover a missed scheduled session.",
            [f"Scheduled for {session.get('session_date', 'an unknown date')}"],
            "Review the original prompt and schedule a focused recovery block.",
        ))
    for session in upcoming_sessions or []:
        recommendations.append(MentorRecommendation(
            "HIGH", session.get("module_id"), session.get("module_name"),
            session.get("category"), session.get("topic", "Unknown topic"),
            "Prepare for the next scheduled session.",
            [f"Upcoming on {session.get('session_date', 'an unknown date')}"],
            "Review prerequisites and attempt one practice question.",
        ))
    for weak in snapshot.weak_areas[:3]:
        recommendations.append(MentorRecommendation(
            "HIGH" if weak.severity == "High" else "MEDIUM",
            None, None, weak.category, weak.topic,
            "Repeated evidence suggests this area needs review.",
            [f"{weak.signals} weakness signal(s)", f"Confidence {weak.confidence:g}"],
            "Review the concept and complete targeted practice.",
        ))
    for topic in snapshot.topics:
        if topic.mastery_label == "Needs review":
            recommendations.append(MentorRecommendation(
                "MEDIUM", None, None, None, topic.topic,
                "Topic mastery is currently developing or incomplete.",
                [f"Mastery score {topic.mastery_score:g}"],
                "Study the fundamentals and verify understanding with practice.",
            ))
    if not recommendations and snapshot.overall.scheduled == 0:
        recommendations.append(MentorRecommendation(
            "LOW", None, None, None, "Your learning plan",
            "There is not enough scheduled learning data yet.", [],
            "Create a timetable or add a learning goal first.",
        ))
    if routine_metrics and routine_metrics.missed:
        recommendations.append(MentorRecommendation(
            "LOW", None, None, "Body & Routine", "Routine consistency",
            "Your routine history includes missed occurrences.",
            [f"{routine_metrics.missed} missed occurrence(s)"],
            "Review your routine timing or shorten the routine; this does not affect academic progress.",
        ))
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted(recommendations, key=lambda item: (order[item.priority], item.topic.casefold()))
