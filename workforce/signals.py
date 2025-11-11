from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone
from .models import Event, AttendanceRecord
from datetime import datetime

@receiver(user_logged_in)
def auto_generate_attendance(sender, request, user, **kwargs):
    """
    When a user logs in, ensure attendance records exist for today's events.
    Includes follow-up and team/service meetings.
    """
    today = timezone.localdate()
    events_today = Event.objects.filter(is_active=True)

    for event in events_today:
        # If event has a specific day, check if today matches it
        if event.day_of_week and event.day_of_week.lower() != today.strftime("%A").lower():
            continue  # skip events not for today

        # Create or update record for this user and event
        AttendanceRecord.objects.get_or_create(
            user=user,
            event=event,
            date=today,
            defaults={"status": "absent", "remarks": ""}
        )


from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Event
from .scheduler import schedule_event_notifications

@receiver(post_save, sender=Event)
def reschedule_on_event_save(sender, instance, **kwargs):
    print(f"🔁 [Signal] Event saved: {instance.name} — refreshing scheduler")
    schedule_event_notifications()
