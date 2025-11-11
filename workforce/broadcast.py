# broadcast.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import AttendanceRecord

broadcasted_events = set()

def broadcast_event(event):
    """Broadcast event start trigger once per event id."""
    if event.id in broadcasted_events:
        return
    broadcasted_events.add(event.id)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "attendance",
        {
            "type": "send_event",
            "data": {
                "id": event.id,
                "name": event.name,
                "date": str(event.date),
                "time": str(event.time),
                "team": event.team.name if event.team else None,
                "team_id": event.team.id if event.team else None,
            },
        },
    )

# broadcast.py
from datetime import timedelta
from asgiref.sync import async_to_sync
from django.utils import timezone
from channels.layers import get_channel_layer
from accounts.models import CustomUser
from .models import AttendanceRecord, ClockRecord


def broadcast_attendance_summary():
    """Broadcast both admin table summary and per-user dashboard summary."""
    channel_layer = get_channel_layer()

    today = timezone.localdate()
    last_30_days = today - timedelta(days=30)

    # === 1️⃣ Admin table records (with clock merge) ===
    records = (
        AttendanceRecord.objects
        .select_related("event", "event__team", "user", "team")
        .filter(date__gte=last_30_days, user__is_superuser=False)
        .exclude(user__groups__name__in=["Pastor", "Admin"])
        .order_by("-date")[:30]
    )

    clock_records = ClockRecord.objects.filter(date__gte=last_30_days)
    clock_map = {(c.user_id, c.event_id, c.date): c for c in clock_records}

    serialized_records = []
    for r in records:
        clock = clock_map.get((r.user_id, r.event_id, r.date))
        clock_in = clock.clock_in.strftime("%H:%M") if clock and clock.clock_in else None
        clock_out = clock.clock_out.strftime("%H:%M") if clock and clock.clock_out else None

        serialized_records.append({
            "date": r.date.strftime("%Y-%m-%d"),
            "event": {
                "name": r.event.name if r.event else "—",
                "id": r.event.id if r.event else None,
                "team": {
                    "name": r.event.team.name if r.event and r.event.team else (
                        r.team.name if r.team else None
                    ),
                    "id": r.event.team.id if r.event and r.event.team else (
                        r.team.id if r.team else None
                    ),
                },
            },
            "user": {
                "id": r.user.id,
                "title": r.user.title or "",
                "full_name": r.user.get_full_name(),
            },
            "status": r.status,
            "remarks": r.remarks or "—",
            "clock_in_time": clock_in or "—",
            "clock_out_time": clock_out or "—",
        })

    # 🔹 Broadcast admin table summary
    async_to_sync(channel_layer.group_send)(
        "attendance",
        {
            "type": "send_summary",
            "data": {"records": serialized_records},
        },
    )

    # === 2️⃣ Per-user dashboard summaries ===
    for user in CustomUser.objects.filter(is_active=True):
        if user.is_superuser:
            continue

        user_records = AttendanceRecord.objects.filter(user=user, date__gte=last_30_days)
        present = user_records.filter(status="present").count()
        excused = user_records.filter(status="excused").count()
        absent = user_records.filter(status="absent").count()

        today_clock = ClockRecord.objects.filter(user=user, date=today).first()
        clocked_in = today_clock.is_clocked_in if today_clock else False

        total_clock_in = ClockRecord.objects.filter(user=user, clock_in__isnull=False).count()
        total_clock_out = ClockRecord.objects.filter(user=user, clock_out__isnull=False).count()

        summary_data = {
            "type": "dashboard_summary",
            "data": {
                "user_id": user.id,
                "summary": {
                    "present": present,
                    "excused": excused,
                    "absent": absent,
                },
                "today": {
                    "clocked_in": clocked_in,
                    "clock_in": (
                        today_clock.clock_in.strftime("%H:%M")
                        if today_clock and today_clock.clock_in
                        else None
                    ),
                    "clock_out": (
                        today_clock.clock_out.strftime("%H:%M")
                        if today_clock and today_clock.clock_out
                        else None
                    ),
                },
                "totals": {
                    "clock_in": total_clock_in,
                    "clock_out": total_clock_out,
                },
            },
        }

        # 🔹 Send only to that user’s attendance channel
        async_to_sync(channel_layer.group_send)(
            f"attendance_user_{user.id}",
            summary_data
        )
