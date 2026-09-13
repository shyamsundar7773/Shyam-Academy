from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryResult:
    delivered: bool
    provider: str
    detail: str = ""


class NotificationDeliveryProvider:
    name = "unconfigured"

    def register_device(self, user_id, device_id, platform, push_token=None, app_version=""):
        raise NotImplementedError

    def unregister_device(self, user_id, device_id):
        raise NotImplementedError

    def deliver(self, notification):
        raise NotImplementedError


class MockNotificationProvider(NotificationDeliveryProvider):
    name = "mock"

    def __init__(self, fail=False):
        self.fail = fail
        self.deliveries = []

    def register_device(self, user_id, device_id, platform, push_token=None, app_version=""):
        return {"status": "REGISTERED", "device_id": device_id, "platform": platform}

    def unregister_device(self, user_id, device_id):
        return {"status": "UNREGISTERED", "device_id": device_id}

    def deliver(self, notification):
        if self.fail:
            return DeliveryResult(False, self.name, "Mock delivery failure")
        identifier = notification.get("notification_id") if isinstance(notification, dict) else notification.notification_id
        self.deliveries.append(identifier)
        return DeliveryResult(True, self.name, "Delivered by mock provider")


class DesktopNotificationProvider(NotificationDeliveryProvider):
    name = "desktop"

    def register_device(self, *args, **kwargs):
        return {"status": "NOT_CONFIGURED"}

    def unregister_device(self, *args, **kwargs):
        return {"status": "NOT_CONFIGURED"}

    def deliver(self, notification):
        return DeliveryResult(False, self.name, "Native desktop delivery is not configured.")


class AndroidNotificationProvider(NotificationDeliveryProvider):
    name = "android"

    def register_device(self, *args, **kwargs):
        return {"status": "NOT_CONFIGURED"}

    def unregister_device(self, *args, **kwargs):
        return {"status": "NOT_CONFIGURED"}

    def deliver(self, notification):
        return DeliveryResult(False, self.name, "Android push delivery is not configured.")
