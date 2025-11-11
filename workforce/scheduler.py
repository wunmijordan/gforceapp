import pytz
import threading
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone
from django.utils.timezone import make_aware
from .models import Event
from .broadcast import broadcast_event


# Initialize scheduler
scheduler = BackgroundScheduler(timezone=timezone.get_current_timezone())


def get_next_occurrence(day_of_week, event_time):
    """Return next datetime occurrence for a given weekday/time."""
    today = timezone.localdate()
    now = timezone.localtime()
    weekday_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
    }

    target = weekday_map[day_of_week.lower()]
    days_ahead = (target - today.weekday() + 7) % 7
    # If it's today but the time already passed, move to next week
    if days_ahead == 0 and event_time and datetime.combine(today, event_time).time() <= now.time():
        days_ahead = 7

    next_date = today + timedelta(days=days_ahead)
    next_dt = datetime.combine(next_date, event_time or datetime.min.time())
    return timezone.make_aware(next_dt)


def schedule_event_notifications():
    """
    Schedule broadcast_event() for all active upcoming events.
    Handles both fixed-date and weekly recurring events.
    """
    print("🟡 [Scheduler] schedule_event_notifications() called")

    try:
        # Clear previous jobs to avoid duplicates
        scheduler.remove_all_jobs()

        events = Event.objects.filter(is_active=True)
        print(f"🟢 [Scheduler] Found {events.count()} events to schedule")

        now = timezone.now()

        for event in events:
            # --- Regular dated events ---
            if event.date:
                event_dt = make_aware(datetime.combine(event.date, event.time))
                if event_dt <= now:
                    print(f"⏩ [Scheduler] Skipping past event: {event.name} ({event_dt})")
                    continue

                run_time = event_dt - timedelta(seconds=45)
                if run_time < now:
                    run_time = now + timedelta(seconds=5)

                job_id = f"attendance_event_{event.id}"
                print(f"⏰ [Scheduler] Scheduling dated '{event.name}' at {run_time}")
                scheduler.add_job(
                    broadcast_event,
                    "date",
                    run_date=run_time,
                    args=[event],
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=30,
                )

            # --- Weekly recurring events ---
            elif getattr(event, "is_recurring_weekly", False) and event.day_of_week:
                next_occurrence = get_next_occurrence(event.day_of_week, event.time)
                if next_occurrence <= now:
                    print(f"⏩ [Scheduler] No future time for {event.name}")
                    continue

                run_time = next_occurrence - timedelta(seconds=45)
                job_id = f"weekly_event_{event.id}"
                print(f"🔁 [Scheduler] Scheduling weekly '{event.name}' for {run_time}")

                scheduler.add_job(
                    broadcast_event,
                    "date",
                    run_date=run_time,
                    args=[event],
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=30,
                )

    except Exception as e:
        print(f"❌ [Scheduler] Error scheduling events: {e}")


def start():
    """Start scheduler safely in a background thread."""
    print("🚀 [Scheduler] start() called")

    if getattr(scheduler, "_started", False):
        print("⚠️ [Scheduler] Already running")
        return

    def run_scheduler():
        try:
            scheduler.start()
            scheduler._started = True
            print("✅ [Scheduler] Started successfully")

            # Schedule events after short delay (so DB definitely ready)
            threading.Timer(2.0, schedule_event_notifications).start()
            print("✅ [Scheduler] Running with timezone:", scheduler.timezone)

            # 🔁 Auto-refresh every day at 00:10 to catch new weekly recurrences
            scheduler.add_job(
                schedule_event_notifications,
                "cron",
                hour=0,
                minute=10,
                id="daily_refresh",
                replace_existing=True
            )

        except Exception as e:
            print(f"❌ [Scheduler] Failed to start: {e}")

    threading.Thread(target=run_scheduler, daemon=True).start()
