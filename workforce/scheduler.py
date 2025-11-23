# workforce/scheduler.py
import threading
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone
from django.utils.timezone import make_aware

from .models import Event
from .broadcast import broadcast_event


# --------------------------------------------------------------------
# GLOBAL SCHEDULER (but not started until start() is called)
# --------------------------------------------------------------------
scheduler = BackgroundScheduler(timezone=timezone.get_current_timezone())


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
weekday_map = {
    "monday": 0, "tuesday": 1, "wednesday": 2,
    "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
}


def get_next_occurrence(day_of_week, event_time):
    """Return next localized datetime for a weekly recurring event."""
    today = timezone.localdate()
    now = timezone.localtime()

    target_weekday = weekday_map[day_of_week.lower()]
    delta = (target_weekday - today.weekday() + 7) % 7

    # If event is today but time passed → go to next week
    if delta == 0:
        event_dt_today = datetime.combine(today, event_time)
        event_dt_today = make_aware(event_dt_today)
        if event_dt_today <= now:
            delta = 7

    next_date = today + timedelta(days=delta)
    next_dt = datetime.combine(next_date, event_time)
    return make_aware(next_dt)


# --------------------------------------------------------------------
# Schedule all events (called on startup + daily refresh)
# --------------------------------------------------------------------
def schedule_event_notifications():
    print("🟡 [Scheduler] schedule_event_notifications() called")

    try:
        scheduler.remove_all_jobs()
        events = Event.objects.filter(is_active=True)

        print(f"🟢 [Scheduler] Scheduling {events.count()} events")

        now = timezone.now()

        for event in events:

            # -----------------------------
            # FIXED DATETIME EVENTS
            # -----------------------------
            if event.date:
                full_dt = make_aware(datetime.combine(event.date, event.time))

                if full_dt <= now:
                    print(f"⏩ Past fixed event skipped: {event.name}")
                    continue

                run_time = full_dt - timedelta(seconds=45)
                if run_time < now:
                    run_time = now + timedelta(seconds=5)

                scheduler.add_job(
                    broadcast_event,
                    trigger="date",
                    run_date=run_time,
                    args=[event],
                    id=f"event_fixed_{event.id}",
                    replace_existing=True,
                    misfire_grace_time=30,
                )

                print(f"⏰ Scheduled: {event.name} → {run_time}")
                continue

            # -----------------------------
            # WEEKLY EVENTS
            # -----------------------------
            if getattr(event, "is_recurring_weekly", False) and event.day_of_week:
                next_dt = get_next_occurrence(event.day_of_week, event.time)

                if next_dt <= now:
                    print(f"⏩ No future weekly occurrence for {event.name}")
                    continue

                run_time = next_dt - timedelta(seconds=45)

                scheduler.add_job(
                    broadcast_event,
                    trigger="date",
                    run_date=run_time,
                    args=[event],
                    id=f"event_weekly_{event.id}",
                    replace_existing=True,
                    misfire_grace_time=30,
                )

                print(f"🔁 Weekly scheduled: {event.name} → {run_time}")

    except Exception as e:
        print(f"❌ [Scheduler] Error scheduling: {e}")


# --------------------------------------------------------------------
# Start scheduler (safe, idempotent, threadsafe)
# --------------------------------------------------------------------
def start():
    """Start APScheduler in a safe background thread."""
    print("🚀 [Scheduler] start() called")

    if getattr(scheduler, "_started", False):
        print("⚠️ [Scheduler] Already running, skipping start()")
        return

    def _run():
        try:
            scheduler.start()
            scheduler._started = True

            print("✅ [Scheduler] Started")
            print(f"🕒 Timezone: {scheduler.timezone}")

            # Schedule once at startup (DB is ready now)
            threading.Timer(2.0, schedule_event_notifications).start()

            # Daily job refresh at 00:10
            scheduler.add_job(
                schedule_event_notifications,
                trigger="cron",
                hour=0,
                minute=10,
                id="daily_reschedule",
                replace_existing=True,
            )

            print("🔁 [Scheduler] Auto-reschedule set for 00:10 daily")

        except Exception as e:
            print(f"❌ [Scheduler] Failed to start: {e}")

    threading.Thread(target=_run, daemon=True).start()
