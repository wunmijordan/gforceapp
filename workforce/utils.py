from django.contrib.auth.models import Group
import requests, mimetypes, os, re, urllib.parse, urllib
from bs4 import BeautifulSoup
from accounts.models import CustomUser
from guests.models import GuestEntry
from .consumers import get_user_color
from django.db.models.fields.files import FieldFile
from django.core.files.storage import default_storage
from django.utils import timezone
from .models import Event, AttendanceRecord, PersonalReminder, UserActivity, CHURCH_COORDS, ChatMessage
from django.db.models import Q
from django.conf import settings
from geopy.distance import distance
from django.core.exceptions import ValidationError


def get_link_preview(url):
    try:
        resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.find("meta", property="og:title") or soup.find("title")
        desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        image = soup.find("meta", property="og:image")

        return {
            "url": url,
            "title": title["content"] if title and title.has_attr("content") else (title.text if title else ""),
            "description": desc["content"] if desc and desc.has_attr("content") else "",
            "image": image["content"] if image and image.has_attr("content") else "",
        }
    except Exception:
        return {"url": url, "title": url, "description": "", "image": ""}


def build_mention_helpers():
    """Precompute mention_map + regex for mentions."""
    users = list(CustomUser.objects.all())
    mention_map = {}
    for u in users:
        display = f"@{ (u.title + ' ') if getattr(u, 'title', None) else '' }{ (u.full_name or u.username) }".strip()
        mention_map[display] = u
    regex = re.compile(r"(" + "|".join(map(re.escape, mention_map.keys())) + r")") if mention_map else None
    return mention_map, regex


def serialize_message(m, mention_map=None, mention_regex=None):
    """Unified serializer for both WebSocket + Views."""
    # Mentions
    mentions_payload = []
    if mention_regex and m.message:
        found = set(mention_regex.findall(m.message))
        for token in found:
            u = mention_map.get(token)
            if u:
                mentions_payload.append({
                    "id": u.id,
                    "username": u.username,
                    "title": getattr(u, "title", ""),
                    "name": u.full_name or u.username,
                    "color": get_user_color(u.id),
                })

    # --- Guest
    guest_payload = None
    if m.guest_card:
        g = GuestEntry.objects.select_related("assigned_to").get(id=m.guest_card.id)
        guest_payload = {
            "id": g.id,
            "name": g.full_name,
            "custom_id": g.custom_id,
            "image": g.picture.url if g.picture else None,
            "title": g.title,
            "date_of_visit": g.date_of_visit.strftime("%Y-%m-%d") if g.date_of_visit else "",
            "assigned_user": {
                "id": g.assigned_to.id,
                "title": g.assigned_to.title,
                "full_name": g.assigned_to.full_name,
                "image": g.assigned_to.image.url if g.assigned_to.image else None,
            } if g.assigned_to else None
        }

    # --- Helper to resolve file URLs
    def build_file_payload(file_obj, message_id):
      """Return standardized file payload for chat messages (works for both dev and prod)."""
      if not file_obj:
          return None

      try:
          # --- Case 1: FileField or CloudinaryField ---
          if isinstance(file_obj, FieldFile):
              file_name = urllib.parse.unquote(os.path.basename(file_obj.name))
              file_url = getattr(file_obj, "url", None)

              # 🧩 Fix malformed or missing URL
              if not file_url:
                  file_url = f"/media/{file_obj.name.lstrip('/')}"
              elif file_url.startswith("/media/media/"):
                  file_url = file_url.replace("/media/media/", "/media/")
              elif not file_url.startswith("/media/") and settings.DEBUG:
                  # Ensure it always begins with single /media/ in dev
                  file_url = f"/media/{file_url.lstrip('/')}"

              # 🧠 Production: make sure we use absolute Cloudinary URL
              if not settings.DEBUG:
                  if not file_url.startswith("http"):
                      if "res.cloudinary.com" not in file_url:
                          file_url = f"https://res.cloudinary.com/{settings.CLOUDINARY_STORAGE['CLOUD_NAME']}/auto/upload/{file_obj.name.lstrip('/')}"

              file_size = getattr(file_obj, "size", None)
              guessed_type, _ = mimetypes.guess_type(file_name)
              file_type = getattr(file_obj.file, "content_type", None) or guessed_type or "application/octet-stream"

          # --- Case 2: Raw string or URL ---
          else:
              file_path = str(file_obj).lstrip("/")
              file_name = urllib.parse.unquote(os.path.basename(file_path)) or "file"

              # Decide which base to apply
              if file_path.startswith("http"):
                  file_url = file_path
              elif settings.DEBUG:
                  if file_path.startswith("media/"):
                      file_url = f"/{file_path}"
                  else:
                      file_url = f"/media/{file_path}"
              elif "res.cloudinary.com" in file_path:
                  file_url = file_path
              else:
                  file_url = f"https://res.cloudinary.com/{settings.CLOUDINARY_STORAGE['CLOUD_NAME']}/auto/upload/{file_path}"

              guessed_type, _ = mimetypes.guess_type(file_path)
              file_type = guessed_type or "application/octet-stream"
              file_size = None

          # ✅ Normalize double prefixes again (safety)
          if settings.DEBUG and file_url.startswith("/media/media/"):
              file_url = file_url.replace("/media/media/", "/media/")

          return {
              "id": message_id,
              "url": file_url,
              "name": file_name,
              "size": file_size,
              "type": file_type,
          }

      except Exception as e:
          import logging
          logging.warning("build_file_payload error: %s", e)
          return None

    # --- Parent (reply-to)
    parent_payload = None
    if m.parent:
        parent = m.parent
        parent_payload = {
            "id": parent.id,
            "sender_id": parent.sender.id,
            "sender_title": getattr(parent.sender, "title", ""),
            "sender_name": parent.sender.full_name or parent.sender.username,
            "sender_color": get_user_color(parent.sender.id),
            "message": parent.message[:50] if parent.message else "(Attachment)" if parent.file else "(No content)",
            "guest": {
                "id": parent.guest_card.id,
                "name": parent.guest_card.full_name,
                "title": parent.guest_card.title,
                "image": parent.guest_card.picture.url if parent.guest_card.picture else None,
                "date_of_visit": parent.guest_card.date_of_visit.strftime("%Y-%m-%d") if parent.guest_card.date_of_visit else "",
            } if parent.guest_card else None,
            "file": build_file_payload(parent.file, parent.id),
            "link_preview": {
                "url": parent.link_url,
                "title": parent.link_title,
                "description": parent.link_description,
                "image": parent.link_image,
            } if parent.link_url else None,
        }

    # --- File payload (main message)
    file_payload = build_file_payload(m.file, m.id)

    # --- Link preview
    link_payload = None
    if m.link_url:
        link_payload = {
            "url": m.link_url,
            "title": m.link_title,
            "description": m.link_description,
            "image": m.link_image,
        }

    # --- Pinned info
    pinned_by_payload = None
    if getattr(m, "pinned_by", None):
        pinned_by_payload = {
            "id": m.pinned_by.id,
            "name": m.pinned_by.full_name or m.pinned_by.username,
            "title": getattr(m.pinned_by, "title", ""),
        }

    # ✅ Final return
    return {
        "id": m.id,
        "message": m.message,
        "sender_id": m.sender.id,
        "sender_title": getattr(m.sender, "title", ""),
        "sender_name": m.sender.full_name or m.sender.username,
        "sender_image": m.sender.image.url if m.sender.image else None,
        "color": get_user_color(m.sender.id),
        "created_at": m.created_at.isoformat(),
        "guest": guest_payload,
        "reply_to_id": m.parent.id if m.parent else None,
        "parent": parent_payload,
        "file": file_payload,
        "link_preview": link_payload,
        "mentions": mentions_payload,
        "pinned": getattr(m, "pinned", False),
        "pinned_at": m.pinned_at.isoformat() if getattr(m, "pinned_at", None) else None,
        "pinned_by": pinned_by_payload,
    }




def generate_daily_attendance():
    today = timezone.localdate()
    weekday = today.strftime("%A").lower()
    created_count = 0

    # Only active users
    users = CustomUser.objects.filter(is_active=True)

    for user in users:
        # Get events this user is eligible for today (general + their teams)
        available_events = get_available_events_for_user(user)

        for event in available_events:
            _, created = AttendanceRecord.objects.get_or_create(
                user=user,
                event=event,
                date=today,
                defaults={"status": "absent"}
            )
            if created:
                created_count += 1

    return created_count




def validate_church_proximity(user_lat, user_lon, threshold_km=0.01):
    """Ensure user is within the threshold distance from church."""
    try:
        # Convert to floats
        lat = float(user_lat)
        lon = float(user_lon)
    except (TypeError, ValueError):
        raise ValidationError("Unable to determine your location. Please enable location access.")

    user_distance = distance(CHURCH_COORDS, (lat, lon)).km

    if user_distance > threshold_km:
        raise ValidationError(
            f"You appear to be {user_distance:.2f} km away from Church. "
            "Please select other options instead."
        )
    print(f"[DEBUG] User distance = {user_distance:.2f} km (Threshold = {threshold_km} km)")


from datetime import timedelta, date
from django.utils import timezone
from .models import Event, PersonalReminder
from datetime import date, datetime, timedelta, time
from django.utils import timezone

from datetime import date, timedelta
from django.utils import timezone

def get_calendar_items(user):
    today = timezone.localdate()
    start_of_year = date(today.year, 1, 1)
    end_of_year = date(today.year, 12, 31)

    events = get_available_events_for_user(user)
    reminders = PersonalReminder.objects.filter(user=user, date__gte=today)

    calendar_items = []

    weekday_map = {
        'sunday': 6,
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
    }

    color_map = {
        "service": "#3b82f6",
        "meeting": "#10b981",
        "training": "#8b5cf6",
        "followup": "#e11d48",
        "reminder": "#f59e0b",
        "other": "#9ca3af",
    }

    def build_datetime(d, t):
        if not t:
            return d.isoformat()
        return datetime.combine(d, t).isoformat()

    for e in events:
        event_type = (e.event_type or "other").lower()
        color = color_map.get(event_type, "#4dabf7")

        base_event = {
            "title": e.name,
            "type": e.event_type,
            "mode": getattr(e, "mode", ""),
            "color": color,
            "description": getattr(e, "description", ""),
            "time": e.time.strftime("%H:%M") if e.time else None,
            "duration_days": getattr(e, "duration_days", 1),
            "team": getattr(e.team, "name", None),
            "team_color": getattr(e.team, "color_class", "bg-gray-800") if getattr(e, "team", None) else None,
        }

        if e.date and e.duration_days > 1:
            start = build_datetime(e.date, e.time)
            end = build_datetime(e.date + timedelta(days=e.duration_days - 1), e.time)
            calendar_items.append({**base_event, "start": start, "end": end})

        elif e.date:
            calendar_items.append({**base_event, "start": build_datetime(e.date, e.time)})

        elif e.is_recurring_weekly and e.day_of_week:
            current = start_of_year
            weekday = weekday_map.get(e.day_of_week.lower())
            while current <= end_of_year:
                if current.weekday() == weekday:
                    calendar_items.append({
                        **base_event,
                        "start": build_datetime(current, e.time),
                    })
                current += timedelta(days=1)

    # Reminders
    for r in reminders:
        calendar_items.append({
            "title": r.title,
            "start": build_datetime(r.date, getattr(r, "time", None)),
            "type": "reminder",
            "mode": "personal",
            "color": color_map["reminder"],
            "description": getattr(r, "note", ""),
            "team": None,
            "team_color_class": None,
        })

    return calendar_items


from django.db.models import Q




def get_available_events_for_user(user):
    today = timezone.localdate()
    start_of_year = date(today.year, 1, 1)
    end_of_year = date(today.year, 12, 31)

    # Filter events for user's teams or global ones
    events = Event.objects.filter(
        is_active=True
    ).filter(
        Q(team__isnull=True) | Q(team__memberships__user=user)
    ).filter(
        Q(date__isnull=False, date__lte=end_of_year) |
        Q(is_recurring_weekly=True)
    )

    available_events = []
    for e in events:
        # Include normal dated events within the year
        if e.date and start_of_year <= e.date <= end_of_year:
            available_events.append(e)

        # Include recurring weekly events (e.g. every Monday)
        elif e.is_recurring_weekly and e.day_of_week:
            available_events.append(e)

    return available_events


def expand_team_events(user, team_id):

    today = timezone.localdate()
    events = get_available_events_for_user(user)

    # 🟦 Filter by team
    if team_id == "null" or team_id is None:
        filtered_events = [e for e in events if e.team is None]
    else:
        try:
            team_id_int = int(team_id)
            filtered_events = [e for e in events if getattr(e.team, "id", None) == team_id_int]
        except (ValueError, TypeError):
            filtered_events = []

    weekday_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    }

    first_day = today.replace(day=1)
    next_month = (first_day + timedelta(days=32)).replace(day=1)
    last_day = next_month - timedelta(days=1)

    data = []

    for e in filtered_events:
        # --- Recurring weekly events ---
        if e.is_recurring_weekly and e.day_of_week:
            weekday = weekday_map.get(e.day_of_week.lower())
            if weekday is not None:
                current = first_day
                while current <= last_day:
                    if current.weekday() == weekday:
                        diff_days = (current - today).days
                        if diff_days < 0:
                            tag = "Past"
                        elif diff_days == 0:
                            tag = "Today"
                        elif diff_days <= 7:
                            tag = "Next Week"
                        elif diff_days <= 14:
                            tag = "In Two Weeks"
                        else:
                            tag = "Upcoming"

                        data.append({
                            "id": e.id,
                            "name": e.name,
                            "team_name": getattr(e.team, "name", "GForce") if e.team else "GForce",
                            "event_type": e.event_type,
                            "attendance_mode": e.attendance_mode,
                            "time": e.time.isoformat() if e.time else None,
                            "date": current,
                            "event_image": e.event_image.url if e.event_image else None,
                            "team_id": getattr(e.team, "id", None),
                            "team_color_class": getattr(e.team, "color_class", "bg-warning-800"),
                            "team_color_hex": getattr(e.team, "color_hex", "#f59f00"),
                            "is_recurring_weekly": True,
                            "is_active": e.is_active,
                            "registrable": bool(e.registration_link),
                            "registration_link": e.registration_link,
                            "postponed": e.postponed,
                            "tag": tag,
                        })
                    current += timedelta(days=1)

        # --- Regular dated events ---
        elif e.date:
            diff_days = (e.date - today).days
            if diff_days < 0:
                tag = "Past"
            elif diff_days == 0:
                tag = "Today"
            elif diff_days <= 7:
                tag = "Next Week"
            elif diff_days <= 14:
                tag = "In Two Weeks"
            else:
                tag = "Upcoming"

            data.append({
                "id": e.id,
                "name": e.name,
                "team_name": getattr(e.team, "name", "GForce") if e.team else "GForce",
                "event_type": e.event_type,
                "attendance_mode": e.attendance_mode,
                "time": e.time.isoformat() if e.time else None,
                "date": e.date,
                "event_image": e.event_image.url if e.event_image else None,
                "team_id": getattr(e.team, "id", None),
                "team_color_class": getattr(e.team, "color_class", "bg-warning-800"),
                "team_color_hex": getattr(e.team, "color_hex", "#f59f00"),
                "is_recurring_weekly": e.is_recurring_weekly,
                "is_active": e.is_active,
                "registrable": bool(e.registration_link),
                "registration_link": e.registration_link,
                "postponed": e.postponed,
                "tag": tag,
            })

    # Only keep future (and today) entries
    return data


from workforce.models import AttendanceRecord, ClockRecord, Team
from accounts.models import CustomUser
from accounts.utils import is_project_admin, is_team_admin


def get_visible_attendance_records(user, since_date=None):
    """
    Returns attendance records the user is allowed to see based on role and team membership.
    """
    base_qs = AttendanceRecord.objects.select_related(
        "event", "user", "team", "event__team"
    ).order_by("-date")

    if since_date:
        base_qs = base_qs.filter(date__gte=since_date)

    # --- Access Logic ---
    if user.is_superuser:
        return base_qs

    elif is_project_admin(user):
        return base_qs.exclude(user__is_superuser=True)

    elif is_team_admin(user):
        admin_teams = Team.objects.filter(
            memberships__user=user,
            memberships__team_role__in=["Minister-in-Charge", "Team Admin"]
        )
        team_ids = admin_teams.values_list("id", flat=True)

        # Show all attendance records tied to either:
        # - Events from these teams, OR
        # - Direct team references
        records = base_qs.filter(
            Q(event__team_id__in=team_ids) | Q(team_id__in=team_ids)
        ).exclude(
            user__is_superuser=True
        ).exclude(
            user__groups__name__in=["Pastor", "Admin"]
        )

        return records.distinct()

    # Default: no access
    return AttendanceRecord.objects.none()


def get_visible_clock_records(user, since_date=None):
    """
    Returns clock records the user is allowed to see based on role and team membership.
    """
    base_qs = ClockRecord.objects.select_related("event", "user", "team").order_by("-date")

    if since_date:
        base_qs = base_qs.filter(date__gte=since_date)

    # --- Access Logic ---
    if user.is_superuser:
        return base_qs

    elif is_project_admin(user):
        return base_qs.exclude(user__is_superuser=True)

    elif is_team_admin(user):
        admin_teams = Team.objects.filter(
            memberships__user=user,
            memberships__team_role__in=["Minister-in-Charge", "Team Admin"]
        )
        team_ids = admin_teams.values_list("id", flat=True)

        team_users = CustomUser.objects.filter(
            team_memberships__team_id__in=team_ids
        ).exclude(
            is_superuser=True
        ).exclude(
            groups__name__in=["Pastor", "Admin"]
        ).distinct()

        records = base_qs.filter(
            Q(user__in=team_users) | Q(team_id__in=team_ids) | Q(event__team_id__in=team_ids)
        )

        return records.distinct()

    # Default: no access
    return ClockRecord.objects.none()
