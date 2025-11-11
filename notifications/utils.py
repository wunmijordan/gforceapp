from django.contrib.auth import get_user_model
from notifications.models import Notification
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from guests.models import GuestEntry
from django.utils import timezone
from pywebpush import webpush, WebPushException
import json, re
from django.conf import settings
from accounts.utils import (
    is_project_admin,
    is_magnet_admin,
    is_team_admin,
    is_project_wide_admin,
)
from accounts.models import TeamMembership



User = get_user_model()


def guest_full_name(guest):
    """Return guest's full name with title if available."""
    if not guest:
        return "Unknown Guest"
    title = getattr(guest, "title", "")
    name = getattr(guest, "full_name", "Unnamed Guest")
    return f"{title} {name}".strip()


def user_full_name(user):
    """
    Return user's full name with title if available.
    Always prioritizes CustomUser.full_name before Django's get_full_name.
    """
    if not user:
        return "Unknown User"

    title = getattr(user, "title", "") or ""
    name = None

    # 🔑 Always prefer custom `full_name`
    if getattr(user, "full_name", None):
        name = user.full_name.strip()
    # Fallback: Django's AbstractUser get_full_name()
    elif hasattr(user, "get_full_name") and user.get_full_name().strip():
        name = user.get_full_name().strip()
    # Otherwise fallback to username
    elif getattr(user, "username", None):
        name = user.username
    else:
        name = "Unnamed User"

    return f"{title} {name}".strip() if title else name



def push_realtime_notification(notification):
    """
    Send a real-time notification to the user's WebSocket group.
    """
    channel_layer = get_channel_layer()
    group_name = f"user_{notification.user.id}"
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "send_notification",  # must match consumer method
            "content": {
                "id": notification.id,
                "title": notification.title,
                "description": notification.description,
                "link": notification.link or "#",
                "is_urgent": notification.is_urgent,
                "is_success": notification.is_success,
            },
        },
    )


def notify_users(users, title, description, link="#", is_urgent=False, is_success=False):
    """
    Create in-app notifications for a set of users and push both WebSocket
    and Web Push notifications (system notifications).
    """
    for user in users:
        # 1️⃣ Create DB notification
        notif = Notification.objects.create(
            user=user,
            title=title,
            description=description,
            link=link,
            is_urgent=is_urgent,
            is_success=is_success,
        )

        # 2️⃣ Push via WebSocket
        push_realtime_notification(notif)

        # 3️⃣ Push via Web Push
        for sub in user.push_subscriptions.all():
            try:
                webpush(
                    subscription_info=sub.subscription_data,
                    data=json.dumps({
                        "title": title,
                        "body": description,
                        "url": link,
                        "sound": getattr(user.settings, "notification_sound", "chime1"),
                        "vibration": getattr(user.settings, "vibration_enabled", True),
                    }),
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": "mailto:magnet@gatewaynation.org"},
                )
            except WebPushException as e:
                # Remove expired subscriptions
                if "410" in str(e) or "404" in str(e):
                    sub.delete()
                else:
                    print(f"Web Push failed for {user}: {repr(e)}")


def get_user_role(user):
    """
    Returns a descriptive role string for notifications and dashboards.
    Prioritizes highest-level roles first:
      - Superuser
      - Project-level Admins (Pastor, Admin)
      - Magnet Admins (Minister-in-Charge, Team Admin - Magnet)
      - Team Admins (Minister-in-Charge, Team Admin, Head of Unit, Asst. Head of Unit)
      - Regular Team Members
    """

    if not user or not user.is_authenticated:
        return "Unknown"

    # 1️⃣ Superuser always top-level
    if user.is_superuser:
        return "Superuser"

    # 2️⃣ Project-level admins (Pastor, Admin)
    if is_project_admin(user):
        return "Admin"

    # 3️⃣ Magnet-specific admins (oversees guest operations)
    if is_magnet_admin(user, role="Minister-in-Charge,Team Admin"):
        return "Magnet Admin"

    # 4️⃣ Team-level admins across any team
    if is_team_admin(user):
        # Determine which teams and roles
        memberships = TeamMembership.objects.filter(user=user)
        admin_roles = []

        for m in memberships:
            # Default pattern if role not restricted
            pattern = (
                r"(minister[- ]?in[- ]?charge|team[ -]?admin|head[- ]?of[- ]?unit|asst\.?[- ]?head[- ]?of[- ]?unit)"
            )
            if re.search(pattern, (m.team_role or ""), re.IGNORECASE):
                admin_roles.append(m.team.name if m.team else "")

        team_list = ", ".join(sorted(set(admin_roles))) if admin_roles else ""
        return f"Team Admin ({team_list})" if team_list else "Team Admin"

    # 5️⃣ Default fallback
    return "GForce Member"


