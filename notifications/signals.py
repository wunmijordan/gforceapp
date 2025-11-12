from django.db.models.signals import pre_save, post_save, post_delete
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import UserSettings, Notification, PushSubscription
from guests.models import Review, GuestEntry
from accounts.models import CustomUser, TeamMembership
from workforce.models import ChatMessage, Event
from django.urls import reverse
from notifications.middleware import get_current_user
from django.utils import timezone
from .utils import notify_users
from pywebpush import WebPushException
import re
from notifications.utils import (
    notify_users,
    guest_full_name,
    user_full_name,
    get_user_role,
)
from accounts.utils import (
    is_project_admin,
    is_magnet_admin,
    is_team_admin,
)
from django.db.models import Q
from datetime import date, datetime, time

User = get_user_model()


# -----------------------------
# Guest Signals
# -----------------------------
@receiver(pre_save, sender=GuestEntry)
def cache_old_assignment(sender, instance, **kwargs):
    """Store the current assigned_to before saving so we can detect reassignment."""
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._old_assigned_to = old.assigned_to
        except sender.DoesNotExist:
            instance._old_assigned_to = None
    else:
        instance._old_assigned_to = None


@receiver(post_save, sender=GuestEntry)
def notify_guest_creation_or_assignment(sender, instance, created, **kwargs):
    """Notify on guest creation, assignment, or reassignment."""
    ts = timezone.localtime().strftime("%b. %d, %Y - %H:%M")
    guest_name = guest_full_name(instance)
    custom_id = getattr(instance, "custom_id", "N/A")
    link = reverse("guest_list")
    registrant = get_current_user()
    creator_name = user_full_name(registrant)
    old_assigned = getattr(instance, "_old_assigned_to", None)
    new_assigned = instance.assigned_to

    # --- CASE 1: New guest ---
    if created:
        top_level_msg = (
            f"{guest_name} ({custom_id})\n"
            f"Registered by: {creator_name}, at {ts}.\n"
            f"New Guest Count: {GuestEntry.objects.count()}."
        )
        if new_assigned:
            top_level_msg += f"\nAssigned to: {user_full_name(new_assigned)}."

        superusers = User.objects.filter(is_superuser=True)

        # Get all staff with admin-level roles
        staff_ids = [
            u.id for u in User.objects.filter(is_active=True)
            if get_user_role(u) in ["Admin", "Magnet Admin"]
        ]
        staff_users = User.objects.filter(id__in=staff_ids).exclude(is_superuser=True).distinct()

        if new_assigned:
            top_level_recipients = list(
                superusers.exclude(id=new_assigned.id)
            ) + list(staff_users.exclude(id=new_assigned.id))
        else:
            top_level_recipients = list(superusers) + list(staff_users)

        notify_users(top_level_recipients, "Guest Created", top_level_msg, link, is_success=True)

        if new_assigned:
            assigned_msg = f"I have been assigned: {guest_name} ({custom_id}), at {ts}."
            notify_users([new_assigned], "Guest Assigned", assigned_msg, link, is_success=True)
        return

    # --- CASE 2: Guest reassignment ---
    if old_assigned != new_assigned:
        if new_assigned:
            assigned_msg = f"I have been reassigned: {guest_name} ({custom_id}), at {ts}."
            notify_users([new_assigned], "Guest Reassigned", assigned_msg, link, is_success=True)

        others_msg = (
            f"{guest_name} ({custom_id}) has been reassigned "
            f"to {user_full_name(new_assigned) if new_assigned else 'no one'}, at {ts}."
        )
        superusers = User.objects.filter(is_superuser=True)
        if new_assigned:
            superusers = superusers.exclude(id=new_assigned.id)

        staff_ids = [
            u.id for u in User.objects.filter(is_active=True)
            if get_user_role(u) in ["Admin", "Magnet Admin"]
        ]
        staff_users = User.objects.filter(id__in=staff_ids).exclude(is_superuser=True).distinct()
        if new_assigned:
            staff_users = staff_users.exclude(id=new_assigned.id)

        notify_users(list(superusers) + list(staff_users), "Guest Reassigned", others_msg, link, is_urgent=True)


@receiver(post_delete, sender=GuestEntry)
def notify_guest_deletion(sender, instance, **kwargs):
    deleter = get_current_user()
    ts = timezone.localtime().strftime("%b. %d, %Y - %H:%M")
    guest_name = guest_full_name(instance)
    deleter_name = user_full_name(deleter)
    custom_id = getattr(instance, "custom_id", "N/A")
    guest_count = GuestEntry.objects.count()

    superusers = User.objects.filter(is_superuser=True)
    staff_ids = [
        u.id for u in User.objects.filter(is_active=True)
        if get_user_role(u) in ["Admin", "Magnet Admin"]
    ]
    staff_users = User.objects.filter(id__in=staff_ids).exclude(is_superuser=True).distinct()

    description = (
        f"{guest_name} ({custom_id})\n"
        f"Deleted by: {deleter_name}, at {ts}.\n"
        f"New Guests Count: {guest_count}"
    )
    link = reverse("guest_list")

    notify_users(superusers, "Guest Deleted", description, link, is_urgent=True)
    notify_users(staff_users, "Guest Deleted", description, link, is_urgent=True)


# -----------------------------
# Review Signals
# -----------------------------
@receiver(post_save, sender=Review)
def notify_review_submission(sender, instance, created, **kwargs):
    if not created:
        return

    reviewer = instance.reviewer
    guest = instance.guest
    ts = timezone.localtime().strftime("%b. %d, %Y - %H:%M")
    guest_name = guest_full_name(guest)
    reviewer_name = user_full_name(reviewer)
    link = reverse("guest_list")

    superusers = User.objects.filter(is_superuser=True).exclude(id=reviewer.id)
    staff_ids = [
        u.id for u in User.objects.filter(is_active=True)
        if get_user_role(u) in ["Admin", "Magnet Admin"] and u.id != reviewer.id
    ]
    staff_users = User.objects.filter(id__in=staff_ids).exclude(is_superuser=True).distinct()

    guest_owner = []
    if guest.assigned_to and guest.assigned_to != reviewer:
        guest_owner = [guest.assigned_to]

    parent_reviewer = None
    if instance.parent and instance.parent.reviewer != reviewer:
        parent_reviewer = instance.parent.reviewer
        if parent_reviewer in superusers:
            superusers = superusers.exclude(id=parent_reviewer.id)
        if parent_reviewer in staff_users:
            staff_users = staff_users.exclude(id=parent_reviewer.id)
        if parent_reviewer in guest_owner:
            guest_owner = []

    recipients = list({u.id: u for u in list(superusers) + list(staff_users) + guest_owner}.values())

    if recipients:
        notify_users(
            recipients,
            "Review Submitted",
            f"{reviewer_name} submitted a review for {guest_name}, at {ts}.",
            link,
            is_success=True
        )

    if parent_reviewer:
        parent_msg = f"{reviewer_name} replied to your review for {guest_name}, at {ts}."
        notify_users([parent_reviewer], "Review Reply", parent_msg, link, is_success=True)


# -----------------------------
# User Signals
# -----------------------------
@receiver(post_save, sender=User)
def notify_user_creation(sender, instance, created, **kwargs):
    if not created:
        return
    ts = timezone.localtime().strftime("%b. %d, %Y - %H:%M")
    superusers = User.objects.filter(is_superuser=True)
    staff_ids = [
        u.id for u in User.objects.filter(is_active=True)
        if get_user_role(u) in ["Admin", "Team Admin"]
    ]
    staff_users = User.objects.filter(id__in=staff_ids).exclude(is_superuser=True).distinct()

    description = f"New user created: {user_full_name(instance)}, at {ts}."
    link = reverse("accounts:user_list")
    notify_users(superusers, "User Created", description, link, is_success=True)
    notify_users(staff_users, "User Created", description, link, is_success=True)


@receiver(post_delete, sender=User)
def notify_user_deletion(sender, instance, **kwargs):
    ts = timezone.localtime().strftime("%b. %d, %Y - %H:%M")
    superusers = User.objects.filter(is_superuser=True)
    staff_ids = [
        u.id for u in User.objects.filter(is_active=True)
        if get_user_role(u) in ["Admin", "Team Admin"]
    ]
    staff_users = User.objects.filter(id__in=staff_ids).exclude(is_superuser=True).distinct()

    description = f"User deleted: {user_full_name(instance)}, at {ts}."
    link = reverse("accounts:user_list")
    notify_users(superusers, "User Deleted", description, link, is_urgent=True)
    notify_users(staff_users, "User Deleted", description, link, is_urgent=True)


@receiver(user_logged_in)
def notify_user_login(sender, request, user, **kwargs):
    ts = timezone.localtime().strftime("%b. %d, %Y - %H:%M")
    user_name = user_full_name(user)
    description_self = f"I just logged in, at {ts}."
    description_others = f"{user_name} logged in, at {ts}."
    link = reverse("accounts:user_list")

    if user.is_superuser:
        notify_users([user], "User Login", description_self, link, is_urgent=True)
    elif is_project_admin(user) or is_team_admin(user, "Minister-in-Charge,Team Admin"):
        notify_users([user], "User Login", description_self, link, is_urgent=True)
        staff_ids = [
            u.id for u in User.objects.filter(is_active=True)
            if get_user_role(u) in ["Admin", "Team Admin"]
        ]
        others = User.objects.filter(id__in=staff_ids).exclude(id=user.id)
        superusers = User.objects.filter(is_superuser=True)
        notify_users(list(others) + list(superusers), "User Login", description_others, link, is_urgent=True)
    else:
        staff_ids = [
            u.id for u in User.objects.filter(is_active=True)
            if get_user_role(u) in ["Admin", "Team Admin"]
        ]
        recipients = User.objects.filter(
            Q(id__in=staff_ids) | Q(is_superuser=True)
        ).distinct()
        notify_users(recipients, "User Login", description_others, link, is_urgent=True)




def escape_regex(string):
    if not string:
        return ""
    return re.escape(string)

def detect_mentions_from_text(text, sender=None):
    """
    Detects mentions in a message, considering @Title FullName.
    Only returns users who are in the same team(s) as the sender.
    
    Args:
        text (str): Message content.
        sender (User, optional): Sender user to determine team scope.

    Returns:
        QuerySet[User]: Users mentioned in the message within sender's teams.
    """
    if not text:
        return User.objects.none()

    # Determine allowed users based on sender's teams
    if sender:
        sender_team_ids = TeamMembership.objects.filter(user=sender).values_list("team_id", flat=True)
        allowed_users = User.objects.filter(team_memberships__team_id__in=sender_team_ids).distinct()
    else:
        allowed_users = User.objects.all()

    mentioned_users = []
    for u in allowed_users:
        full_name = escape_regex(u.full_name or u.username)
        title = escape_regex(u.title) if u.title else ""
        if title:
            pattern = rf"@(?:{title}\s+)?{full_name}"
        else:
            pattern = rf"@{full_name}"
        if re.search(pattern, text, re.IGNORECASE):
            mentioned_users.append(u)

    return User.objects.filter(id__in=[u.id for u in mentioned_users])


@receiver(pre_save, sender=ChatMessage)
def cache_old_pin(sender, instance, **kwargs):
    """
    Cache the old pinned status and pinner for comparison.
    """
    if instance.pk:
        old = sender.objects.filter(pk=instance.pk).first()
        instance._old_pinned = old.pinned if old else False
        instance._old_pinned_by = old.pinned_by if old else None
    else:
        instance._old_pinned = False
        instance._old_pinned_by = None

@receiver(post_save, sender=ChatMessage)
def create_chat_notification(sender, instance, created, **kwargs):
    sender_user = instance.sender
    just_pinned = instance.pinned and (getattr(instance, "_old_pinned", False) == False)
    ts = timezone.localtime(instance.pinned_at if just_pinned else instance.created_at).strftime("%b. %d, %Y - %H:%M")
    link = reverse("workforce:chat_room")

    # Identify which team the message belongs to (None means central/global chat)
    team = getattr(instance, "team", None)
    team_name = team.name if team else "GForce"

    # Message preview
    message_preview = "(No content)"
    if instance.message:
        message_preview = instance.message[:50]
    elif instance.file:
        message_preview = "(Attachment)"
    elif instance.guest_card:
        message_preview = f"(Guest: {instance.guest_card.full_name})"

    notified_users = set()

    # -----------------------------------
    # 1️⃣ Handle pinned messages
    # -----------------------------------
    if just_pinned and instance.pinned_by:
        mentioned_users = detect_mentions_from_text(instance.message, sender=sender_user)

        # Notify pinner
        notify_users(
            [instance.pinned_by],
            f"📌 Pinned Message ({team_name})",
            f"I pinned a message, at {ts}",
            link,
            is_success=True,
        )
        notified_users.add(instance.pinned_by.id)

        # Notify mentioned users
        for u in mentioned_users:
            notify_users(
                [u],
                f"📌 Pinned Message ({team_name})",
                f"{user_full_name(instance.pinned_by)} pinned a message I was mentioned in, at {ts}",
                link,
                is_success=True,
            )
            notified_users.add(u.id)

        # Notify admins (team & project)
        team_ids = [team.id] if team else []
        admins = User.objects.filter(team_memberships__team_id__in=team_ids).distinct() if team_ids else User.objects.none()
        admins = [
            u for u in admins
            if (get_user_role(u) in ["Team Admin", "Admin"]) or u.is_superuser
        ]
        admins = [u for u in admins if u.id not in notified_users]

        for admin in admins:
            notify_users(
                [admin],
                f"📌 Pinned Message ({team_name})",
                f"{user_full_name(instance.pinned_by)} pinned a message in your team, at {ts}",
                link,
                is_success=True,
            )
            notified_users.add(admin.id)

        # Notify other team members
        if team_ids:
            other_users = User.objects.filter(
                team_memberships__team_id__in=team_ids
            ).exclude(id__in=notified_users).distinct()
        else:
            other_users = User.objects.exclude(id__in=notified_users).distinct()  # central room case

        for u in other_users:
            notify_users(
                [u],
                f"📌 Pinned Message ({team_name})",
                f"{user_full_name(instance.pinned_by)} pinned a message, at {ts}",
                link,
                is_success=True,
            )
            notified_users.add(u.id)

    # -----------------------------------
    # 2️⃣ Mentions (only if text has '@')
    # -----------------------------------
    if instance.message and "@" in instance.message and not just_pinned:
        mentioned_users = detect_mentions_from_text(instance.message, sender=sender_user)

        # Mentioned users
        for user in mentioned_users:
            notify_users(
                [user],
                f"Mentioned ({team_name})",
                f"{user_full_name(sender_user)} mentioned me in a message, at {ts}",
                link,
                is_success=True,
            )
            notified_users.add(user.id)

        # Sender feedback
        mentioned_names_list = [user_full_name(u) for u in mentioned_users]
        if sender_user in mentioned_users:
            mentioned_names_list.remove(user_full_name(sender_user))
            mentioned_names_list = ["myself"] + mentioned_names_list

        if mentioned_names_list:
            notify_users(
                [sender_user],
                f"Mentioned ({team_name})",
                f"I mentioned {', '.join(mentioned_names_list)} in a message, at {ts}",
                link,
                is_success=True,
            )
            notified_users.add(sender_user.id)

        # Notify admins (team/project)
        team_ids = [team.id] if team else []
        admins = User.objects.filter(team_memberships__team_id__in=team_ids).distinct() if team_ids else User.objects.none()
        admins = [
            u for u in admins
            if (get_user_role(u) in ["Team Admin", "Admin"]) or u.is_superuser
        ]
        admins = [u for u in admins if u.id not in notified_users]

        for admin in admins:
            mentioned_summary = ", ".join([user_full_name(u) for u in mentioned_users]) or "someone"
            notify_users(
                [admin],
                f"Mentioned ({team_name})",
                f"{user_full_name(sender_user)} mentioned {mentioned_summary} in your team chat, at {ts}",
                link,
                is_success=True,
            )
            notified_users.add(admin.id)

    # -----------------------------------
    # 3️⃣ Regular messages (non-mention)
    # -----------------------------------
    if (not instance.message or "@" not in instance.message) and not just_pinned:
        if team:
            recipients = User.objects.filter(
                team_memberships__team=team
            ).exclude(id__in=notified_users).distinct()
        else:
            # Central room → everyone
            recipients = User.objects.exclude(id__in=notified_users).distinct()

        if recipients.exists():
            notify_users(
                recipients,
                f"ChatRoom ({team_name})",
                f"{user_full_name(sender_user)}:\n{message_preview}\n{ts}",
                link,
                is_success=True,
            )






@receiver(post_save, sender=Event)
def notify_team_on_event_create(sender, instance, created, **kwargs):
    """
    Sends team-aware notifications when a new Event is created.
    - Notifies only relevant team members if the event has a team.
    - Notifies everyone (except admins) for church-wide events (team=None).
    - Superusers and project admins are notified separately.
    - Creator gets a confirmation message.
    """
    if not created:
        return

    event = instance
    creator = event.created_by
    # --- Determine timestamp string ---
    if event.is_recurring_weekly:
        ts = f"Every {event.get_day_of_week_display()}"  # e.g., "Every Sunday"
    elif event.date:
        event_datetime = datetime.combine(event.date, event.time or time.min) \
            if isinstance(event.date, date) and not isinstance(event.date, datetime) else event.date

        if timezone.is_naive(event_datetime):
            event_datetime = timezone.make_aware(event_datetime, timezone.get_current_timezone())

        ts = timezone.localtime(event_datetime).strftime("%b. %d, %Y — %H:%M")
    else:
        ts = "TBD"
    team = getattr(event, "team", None)
    team_name = team.name if team else "GForce"

    # Notification title + message body
    title = f"📅 New Event Created: {event.name}"
    message_lines = [
        f"Event Type: {event.event_type}",
        f"Date: {ts}",
        f"Mode: {event.attendance_mode}",
    ]
    if event.team:
        message_lines.append(f"Team: {event.team.name}")
    message_lines.append(f"Created by: {user_full_name(creator) if creator else 'Unknown'}")
    message_body = "\n".join(message_lines)

    notified_ids = set()

    # Helper to get proper link per user
    def get_link(user):
        if getattr(user, "is_project_wide_admin", False):
            return reverse("accounts:admin_dashboard")
        return reverse("dashboard")

    # -----------------------------
    # 1️⃣ Notify members of the assigned team
    # -----------------------------
    if event.team:
        team_memberships = TeamMembership.objects.filter(team=event.team).select_related("user")
        team_users = [
            m.user for m in team_memberships
            if m.user.is_active
            and not m.user.is_superuser
            and not is_project_admin(m.user)
        ]
        for user in team_users:
            notify_users(
                [user],
                f"{team_name} Event",
                f"{user_full_name(creator)} created a new event: \n{event.name} ({event.attendance_mode} {event.event_type}) — {ts}",
                get_link(user),
                is_success=True
            )
            notified_ids.add(user.id)

    # -----------------------------
    # 2️⃣ Handle church-wide events (no specific team)
    # -----------------------------
    else:
        general_users = User.objects.filter(is_active=True)
        general_users = [
            u for u in general_users
            if not u.is_superuser and not is_project_admin(u)
        ]
        for user in general_users:
            notify_users(
                [user],
                f"{team_name} Event",
                f"{user_full_name(creator)} created a new event: \n{event.name} ({event.attendance_mode} {event.event_type}) — {ts}",
                get_link(user),
                is_success=True
            )
            notified_ids.add(user.id)

    # -----------------------------
    # 3️⃣ Notify top-level users (Superusers + Project Admins)
    # -----------------------------
    top_level_users = User.objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(groups__name__in=["Pastor", "Admin"])
    ).distinct()
    top_level_users = [u for u in top_level_users if u.id not in notified_ids]
    for user in top_level_users:
        notify_users(
            [user],
            f"{team_name} Event",
            f"{user_full_name(creator)} created a new event: {event.name} ({event.attendance_mode} {event.event_type}) — {ts}",
            get_link(user),
            is_success=True
        )
        notified_ids.add(user.id)

    # -----------------------------
    # 4️⃣ Notify creator (confirmation)
    # -----------------------------
    if creator and creator.id not in notified_ids:
        notify_users(
            [creator],
            f"{team_name} Event",
            f"I created a new event: {event.name} ({event.attendance_mode} {event.event_type}) on {ts}.",
            get_link(creator),
            is_success=True
        )
        notified_ids.add(creator.id)




@receiver(post_save, sender=User)
def create_user_settings(sender, instance, created, **kwargs):
    if created:
        UserSettings.objects.create(user=instance)


"""
@receiver(post_save, sender=Notification)
def push_on_notification(sender, instance, created, **kwargs):
    if created:
        subscriptions = PushSubscription.objects.filter(user=instance.user)
        for sub in subscriptions:
            try:
                send_push(
                    sub.subscription_data,
                    title=instance.title,
                    body=instance.description,
                    url=instance.link or "/"
                )
            except WebPushException as e:
                if "410" in str(e) or "404" in str(e):
                    # subscription expired → remove it
                    sub.delete()
                else:
                    print("Push failed:", repr(e))
"""

