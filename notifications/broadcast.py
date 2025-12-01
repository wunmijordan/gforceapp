from .utils import notify_users
from .models import Notification
from django.contrib.auth import get_user_model

User = get_user_model()

def broadcast_notification(notification: Notification):
    """
    Pushes a notification to the user's WebSocket & Web Push.
    Can be scheduled independently from programme events.
    """
    notify_users(
        [notification.user],
        notification.title,
        notification.description,
        notification.link or "#",
        is_urgent=notification.is_urgent,
        is_success=notification.is_success,
    )
