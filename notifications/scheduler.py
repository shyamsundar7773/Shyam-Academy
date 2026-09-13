from datetime import datetime, timezone

from notifications import repository
from notifications.providers import MockNotificationProvider
from notifications.service import in_quiet_hours, user_timezone


def process_due_notifications(connection, provider=None, now=None, batch_size=50, max_retries=3):
    provider = provider or MockNotificationProvider()
    now = now or datetime.now(timezone.utc)
    processed = []
    for item in repository.due_notifications(connection, now, batch_size):
        if int(item.get("delivery_attempts") or 0) >= max_retries:
            continue
        preferences = repository.get_preferences(connection, item["user_id"])
        if not preferences["notifications_enabled"]:
            repository.update_status(connection, item["notification_id"], "SUPPRESSED",
                                     error="Notifications disabled")
            processed.append((item["notification_id"], "SUPPRESSED"))
            continue
        local = now.astimezone(user_timezone(connection, item["user_id"]))
        if in_quiet_hours(local, preferences) and not (
            item["priority"] == "URGENT" and preferences["allow_urgent_quiet_hours"]
        ):
            repository.update_status(connection, item["notification_id"], "READY",
                                     error="Delayed by quiet hours")
            processed.append((item["notification_id"], "READY"))
            continue
        result = provider.deliver(item)
        if result.delivered:
            repository.update_status(connection, item["notification_id"], "DELIVERED",
                                     delivered_at=now.isoformat())
            processed.append((item["notification_id"], "DELIVERED"))
        else:
            attempts = int(item.get("delivery_attempts") or 0) + 1
            status = "FAILED" if attempts >= max_retries else "READY"
            connection.execute(
                "UPDATE notifications SET delivery_attempts=?, last_error=?, status=?, updated_at=? "
                "WHERE notification_id=?",
                (attempts, result.detail, status, now.isoformat(), item["notification_id"]),
            )
            connection.commit()
            processed.append((item["notification_id"], status))
    return processed
