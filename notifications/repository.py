import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from notifications.models import validate_notification_type, validate_priority, validate_status


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row(row):
    if row is None:
        return None
    value = dict(row)
    value["metadata"] = json.loads(value.pop("metadata_json") or "{}")
    value["notification_type"] = value["type"]
    return value


def create_notification(connection, user_id, notification_type, title, body,
                        scheduled_at, session_id=None, module_id=None,
                        priority="NORMAL", metadata=None, routine_occurrence_id=None):
    if not user_id or not isinstance(user_id, str):
        raise ValueError("A user identity is required.")
    validate_notification_type(notification_type)
    validate_priority(priority)
    if not title.strip() or not body.strip():
        raise ValueError("Notification title and body are required.")
    if not isinstance(scheduled_at, str) or "+" not in scheduled_at and "Z" not in scheduled_at:
        raise ValueError("Notification time must include a timezone.")
    existing = connection.execute(
        """SELECT notification_id FROM notifications
        WHERE user_id=? AND session_id IS ? AND type=? AND scheduled_at=?
        AND routine_occurrence_id IS ?
        AND status != 'CANCELLED'""",
        (user_id, session_id, notification_type, scheduled_at, routine_occurrence_id),
    ).fetchone()
    if existing:
        return existing["notification_id"]
    notification_id = str(uuid4())
    connection.execute(
        """INSERT INTO notifications
        (notification_id,user_id,type,title,body,session_id,module_id,scheduled_at,
         created_at,status,priority,metadata_json,routine_occurrence_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (notification_id, user_id, notification_type, title.strip(), body.strip(),
         session_id, module_id, scheduled_at, _now(), "SCHEDULED", priority,
         json.dumps(metadata or {}, separators=(",", ":")), routine_occurrence_id),
    )
    connection.commit()
    return notification_id


def get_notification(connection, notification_id, user_id):
    row = connection.execute(
        "SELECT * FROM notifications WHERE notification_id=? AND user_id=?",
        (notification_id, user_id),
    ).fetchone()
    return _row(row)


def list_notifications(connection, user_id, limit=50, unread_only=False):
    clause = "AND read_at IS NULL" if unread_only else ""
    rows = connection.execute(
        f"""SELECT * FROM notifications WHERE user_id=? {clause}
        ORDER BY scheduled_at DESC, created_at DESC LIMIT ?""",
        (user_id, max(1, min(int(limit), 200))),
    ).fetchall()
    return [_row(row) for row in rows]


def count_unread(connection, user_id):
    return connection.execute(
        "SELECT COUNT(*) AS count FROM notifications WHERE user_id=? AND read_at IS NULL "
        "AND status NOT IN ('CANCELLED','SUPPRESSED')", (user_id,)
    ).fetchone()["count"]


def due_notifications(connection, now, limit=50):
    return [_row(row) for row in connection.execute(
        """SELECT * FROM notifications WHERE scheduled_at<=?
        AND status IN ('SCHEDULED','READY','FAILED') AND cancelled_at IS NULL
        ORDER BY scheduled_at, created_at LIMIT ?""",
        (now.isoformat(), max(1, min(int(limit), 200))),
    ).fetchall()]


def update_status(connection, notification_id, status, delivered_at=None, error=None):
    validate_status(status)
    now = _now()
    connection.execute(
        """UPDATE notifications SET status=?, delivered_at=COALESCE(?,delivered_at),
        last_error=?, updated_at=? WHERE notification_id=?""",
        (status, delivered_at, error, now, notification_id),
    )
    connection.commit()


def mark_read(connection, notification_id, user_id):
    cursor = connection.execute(
        "UPDATE notifications SET read_at=?, status=CASE WHEN status='DELIVERED' "
        "THEN 'READ' ELSE status END, updated_at=? WHERE notification_id=? AND user_id=?",
        (_now(), _now(), notification_id, user_id),
    )
    connection.commit()
    if cursor.rowcount != 1:
        raise ValueError("Notification not found.")


def cancel_for_session(connection, user_id, session_id, reason="Session changed"):
    connection.execute(
        """UPDATE notifications SET status='CANCELLED', cancelled_at=?, updated_at=?,
        last_error=? WHERE user_id=? AND session_id=? AND status IN ('SCHEDULED','READY','FAILED')""",
        (_now(), _now(), reason, user_id, session_id),
    )
    connection.commit()


def cancel_for_routine(connection, user_id, routine_id, reason="Routine changed"):
    connection.execute(
        """UPDATE notifications SET status='CANCELLED',cancelled_at=?,updated_at=?,
        last_error=? WHERE user_id=? AND routine_occurrence_id IN
        (SELECT occurrence_id FROM routine_occurrences WHERE routine_id=?)
        AND status IN ('SCHEDULED','READY','FAILED')""",
        (_now(), _now(), reason, user_id, routine_id),
    )
    connection.commit()


def cancel_for_routine_occurrence(connection, user_id, occurrence_id, reason="Routine changed"):
    connection.execute(
        """UPDATE notifications SET status='CANCELLED',cancelled_at=?,updated_at=?,
        last_error=? WHERE user_id=? AND routine_occurrence_id=?
        AND status IN ('SCHEDULED','READY','FAILED')""",
        (_now(), _now(), reason, user_id, occurrence_id),
    )
    connection.commit()


def suppress_routine_missed(connection, user_id, occurrence_id):
    connection.execute(
        """UPDATE notifications SET status='SUPPRESSED',updated_at=?
        WHERE user_id=? AND routine_occurrence_id=? AND type='ROUTINE_MISSED'
        AND status IN ('SCHEDULED','READY','FAILED')""",
        (_now(), user_id, occurrence_id),
    )
    connection.commit()


def cancel_notification(connection, notification_id, user_id):
    cursor = connection.execute(
        """UPDATE notifications SET status='CANCELLED', cancelled_at=?, updated_at=?
        WHERE notification_id=? AND user_id=? AND status NOT IN ('DELIVERED','READ')""",
        (_now(), _now(), notification_id, user_id),
    )
    connection.commit()
    if cursor.rowcount != 1:
        raise ValueError("Notification not found or already delivered.")


def save_preferences(connection, user_id, values):
    allowed = {
        "notifications_enabled", "session_reminders", "session_start",
        "missed_session", "test_reminders", "interview_reminders",
        "mentor_recommendations", "desktop_enabled", "android_enabled",
        "quiet_start", "quiet_end", "reminder_offset_minutes", "timezone",
        "allow_urgent_quiet_hours",
    }
    unknown = set(values) - allowed
    if unknown:
        raise ValueError("Unknown notification preference.")
    current = get_preferences(connection, user_id)
    current.update(values)
    connection.execute(
        """INSERT INTO notification_preferences
        (user_id,notifications_enabled,session_reminders,session_start,missed_session,
         test_reminders,interview_reminders,mentor_recommendations,desktop_enabled,
         android_enabled,quiet_start,quiet_end,reminder_offset_minutes,timezone,
         allow_urgent_quiet_hours,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
        notifications_enabled=excluded.notifications_enabled,
        session_reminders=excluded.session_reminders, session_start=excluded.session_start,
        missed_session=excluded.missed_session, test_reminders=excluded.test_reminders,
        interview_reminders=excluded.interview_reminders,
        mentor_recommendations=excluded.mentor_recommendations,
        desktop_enabled=excluded.desktop_enabled, android_enabled=excluded.android_enabled,
        quiet_start=excluded.quiet_start, quiet_end=excluded.quiet_end,
        reminder_offset_minutes=excluded.reminder_offset_minutes,
        timezone=excluded.timezone, allow_urgent_quiet_hours=excluded.allow_urgent_quiet_hours,
        updated_at=excluded.updated_at""",
        (user_id, *[int(current[key]) if isinstance(current[key], bool) else current[key]
                    for key in ("notifications_enabled","session_reminders","session_start",
                                "missed_session","test_reminders","interview_reminders",
                                "mentor_recommendations","desktop_enabled","android_enabled",
                                "quiet_start","quiet_end","reminder_offset_minutes",
                                "timezone","allow_urgent_quiet_hours")], _now()),
    )
    connection.commit()


def get_preferences(connection, user_id):
    row = connection.execute(
        "SELECT * FROM notification_preferences WHERE user_id=?", (user_id,)
    ).fetchone()
    defaults = {
        "user_id": user_id, "notifications_enabled": True, "session_reminders": True,
        "session_start": True, "missed_session": True, "test_reminders": True,
        "interview_reminders": True, "mentor_recommendations": True,
        "desktop_enabled": True, "android_enabled": True, "quiet_start": "23:00",
        "quiet_end": "07:00", "reminder_offset_minutes": 5, "timezone": "Asia/Kolkata",
        "allow_urgent_quiet_hours": False,
    }
    if row:
        defaults.update(dict(row))
        for key in defaults:
            if key not in {"user_id", "quiet_start", "quiet_end", "timezone"}:
                if key != "reminder_offset_minutes":
                    defaults[key] = bool(defaults[key])
    return defaults


def register_device(connection, user_id, device_id, platform, push_token=None, app_version=""):
    if not user_id or not device_id or platform not in {"desktop", "android"}:
        raise ValueError("Valid user, device, and platform are required.")
    connection.execute(
        """INSERT INTO notification_devices
        (device_id,user_id,platform,push_token,app_version,created_at,last_seen_at,active)
        VALUES (?,?,?,?,?,?,?,1)
        ON CONFLICT(device_id,user_id) DO UPDATE SET platform=excluded.platform,
        push_token=excluded.push_token, app_version=excluded.app_version,
        last_seen_at=excluded.last_seen_at, active=1""",
        (device_id, user_id, platform, push_token, app_version, _now(), _now()),
    )
    connection.commit()


def unregister_device(connection, user_id, device_id):
    connection.execute(
        "UPDATE notification_devices SET active=0,last_seen_at=? WHERE user_id=? AND device_id=?",
        (_now(), user_id, device_id),
    )
    connection.commit()


def list_devices(connection, user_id):
    return connection.execute(
        "SELECT device_id,user_id,platform,app_version,created_at,last_seen_at,active "
        "FROM notification_devices WHERE user_id=? ORDER BY last_seen_at DESC", (user_id,)
    ).fetchall()
