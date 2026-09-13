from datetime import datetime, timezone
from uuid import uuid4


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_conversation(connection, user_id, title="AI Mentor"):
    conversation_id = str(uuid4())
    connection.execute(
        """INSERT INTO mentor_conversations
        (conversation_id,user_id,title,created_at,updated_at)
        VALUES (?,?,?,?,?)""",
        (conversation_id, user_id, title.strip() or "AI Mentor", _now(), _now()),
    )
    connection.commit()
    return conversation_id


def get_conversation(connection, conversation_id, user_id):
    return connection.execute(
        "SELECT * FROM mentor_conversations WHERE conversation_id=? AND user_id=?",
        (conversation_id, user_id),
    ).fetchone()


def list_conversations(connection, user_id, limit=20):
    return connection.execute(
        """SELECT * FROM mentor_conversations WHERE user_id=?
        ORDER BY updated_at DESC LIMIT ?""",
        (user_id, max(1, min(int(limit), 100))),
    ).fetchall()


def list_messages(connection, conversation_id, user_id, limit=30):
    if get_conversation(connection, conversation_id, user_id) is None:
        raise ValueError("The selected Mentor conversation could not be found.")
    return connection.execute(
        """SELECT * FROM mentor_messages WHERE conversation_id=? AND user_id=?
        ORDER BY created_at, message_id LIMIT ?""",
        (conversation_id, user_id, max(1, min(int(limit), 100))),
    ).fetchall()


def add_message(connection, conversation_id, user_id, role, message, action_type=None):
    if get_conversation(connection, conversation_id, user_id) is None:
        raise ValueError("The selected Mentor conversation could not be found.")
    value = message.strip() if isinstance(message, str) else ""
    if not value:
        raise ValueError("Mentor messages cannot be empty.")
    if role not in {"user", "mentor"}:
        raise ValueError("Invalid Mentor message role.")
    duplicate = connection.execute(
        """SELECT message_id FROM mentor_messages
        WHERE conversation_id=? AND user_id=? AND role=? AND message=?""",
        (conversation_id, user_id, role, value),
    ).fetchone()
    if duplicate:
        return duplicate["message_id"]
    message_id = str(uuid4())
    now = _now()
    connection.execute(
        """INSERT INTO mentor_messages
        (message_id,conversation_id,user_id,role,message,action_type,created_at)
        VALUES (?,?,?,?,?,?,?)""",
        (message_id, conversation_id, user_id, role, value, action_type, now),
    )
    connection.execute(
        "UPDATE mentor_conversations SET updated_at=? WHERE conversation_id=? AND user_id=?",
        (now, conversation_id, user_id),
    )
    connection.commit()
    return message_id
