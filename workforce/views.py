from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test, login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.urls import reverse_lazy, reverse
from django.utils.timezone import localtime, now
import pytz, requests, re, calendar, json, mimetypes, os
from accounts.models import CustomUser, TeamMembership
from guests.models import GuestEntry
from .models import ChatMessage, Event, AttendanceRecord, PersonalReminder, UserActivity, Team, ClockRecord
from django.contrib.auth.forms import SetPasswordForm
from django.core.paginator import Paginator
from django.db.models import Q, Count, QuerySet
from datetime import datetime, timedelta
from django.db.models.functions import ExtractMonth
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.models import Group
from accounts.utils import (
    user_in_groups,
    user_in_team,
    get_guest_queryset,
    get_combined_role,
    is_magnet_admin,
    is_project_level_role,
    is_project_admin,
    is_project_wide_admin,
    is_team_admin,
)
from .consumers import get_user_color, get_team_color
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from .utils import serialize_message, build_mention_helpers, expand_team_events, get_available_events_for_user, get_visible_attendance_records, get_visible_clock_records
from django.core.files.storage import default_storage
import urllib.parse
from django.conf import settings
from django.db.models import Prefetch


@login_required
def chat_room(request):
    """
    Central chatroom page. Query param `team_id` selects a room.
    If no team_id -> central room (everyone). Magnet remains special for guest actions.
    """
    user = request.user
    # Query all active teams with enriched members
    teams = list(
        Team.objects.filter(is_active=True)
        .prefetch_related(
            Prefetch("members", queryset=CustomUser.objects.prefetch_related("sent_chats"))
        )
        .order_by("name")
    )

    # ✅ Superuser: see all teams, no auto-membership creation
    if user.is_superuser:
        pass

    # ✅ Pastors/Admins: see all teams but don’t persist "Pastor,Admin" roles
    elif is_project_admin(user) and not user.is_superuser:
        pass  # they see all, but no membership auto-creation

    # ✅ Regular users: show only their assigned teams
    else:
        teams = [team for team in teams if user_in_team(user, team.name)]


    # selected team (team_id in GET), default = None meaning central
    team_id = request.GET.get("team_id")
    guest_id = request.GET.get("guest_id")

    # Always get magnet team (used below)
    magnet_team = Team.objects.filter(name__iexact="magnet").first()

    # If guest_id exists but no team_id, force Magnet chat
    if guest_id and not team_id and magnet_team:
        team_id = magnet_team.id

    selected_team = Team.objects.filter(id=team_id, is_active=True).first() if team_id else None

    # Assign team color + enriched users
    for team in teams:
        team.enriched_users = []

        for user in team.users.all().exclude(is_superuser=True):
            initials = "".join([p[0].upper() for p in (user.full_name or user.username).split()[:2]])
            image_url = user.image.url if getattr(user, "image", None) else None
            last_msg_obj = (
                user.sent_chats.filter(team=team).order_by("-created_at").first()
            )
            last_msg = last_msg_obj.message if last_msg_obj else "No messages yet"

            team.enriched_users.append({
                "id": user.id,
                "full_name": user.full_name,
                "username": user.username,
                "title": user.title,
                "phone_number": user.phone_number,
                "color": get_user_color(user.id),
                "initials": initials,
                "image": image_url,
                "last_message": last_msg,
            })

        # Sort team users: Project-level Pastor/Admin first, then alphabetically
        team.enriched_users.sort(
            key=lambda u: (
                not is_project_level_role(CustomUser.objects.get(id=u["id"])),
                u["full_name"].lower()
            )
        )

    # Prebuild mention helpers (map + regex)
    mention_map, mention_regex = build_mention_helpers()

    # choose messages:
    if selected_team:
        last_messages_qs = ChatMessage.objects.filter(team=selected_team)
    else:
        last_messages_qs = ChatMessage.objects.filter(team__isnull=True) | ChatMessage.objects.filter(team=selected_team)

    last_messages = last_messages_qs.select_related("sender", "guest_card", "parent__sender").order_by("-created_at")[:50]
    last_messages_payload = [serialize_message(m, mention_map, mention_regex) for m in reversed(last_messages)]

    # guests: only useful if Magnet is selected OR user is on Magnet team
    attached_guest = None
    if guest_id:
        attached_guest = GuestEntry.objects.filter(id=guest_id).first()

    # Get all non-superusers
    users = CustomUser.objects.filter(is_superuser=False).prefetch_related('assigned_guests')

    # Sort users globally with same Pastor/Admin priority
    users = sorted(
        users,
        key=lambda u: (
            not is_project_level_role(u),
            (u.full_name or u.username).lower()
        )
    )

    # Fetch guests the user is allowed to see
    guest_queryset = get_guest_queryset(request.user, selected_team)

    user_guests = [
        {
            "id": u.id,
            "name": u.full_name or u.username,
            "role": get_combined_role(u, selected_team),
            "team_name": selected_team.name if selected_team else "",
            "guests": [
                {
                    "id": g.id,
                    "name": g.full_name,
                    "custom_id": g.custom_id,
                    "image": g.picture.url if g.picture else None,
                    "title": g.title,
                    "date_of_visit": g.date_of_visit.strftime("%Y-%m-%d") if g.date_of_visit else "",
                    "assigned": True
                } for g in u.assigned_guests.all()
            ]
        } for u in users
    ]

    # Unassigned guests: visible to project-level privileged users OR Magnet team admins (MIC/Team Admin)
    unassigned_guests = []
    # Project-level privileged?
    if is_magnet_admin(request.user):
        unassigned_qs = GuestEntry.objects.filter(assigned_to__isnull=True)
        unassigned_guests = [
            {
                "id": g.id,
                "name": g.full_name,
                "custom_id": g.custom_id,
                "image": g.picture.url if g.picture else None,
                "title": g.title,
                "date_of_visit": g.date_of_visit.strftime("%Y-%m-%d") if g.date_of_visit else "",
                "assigned": False
            } for g in unassigned_qs
        ]

    context = {
        "teams": teams,
        "team.enriched_users": team.enriched_users,
        "selected_team": selected_team,
        "selected_team_id": selected_team.id if selected_team else None,
        "magnet_team": magnet_team,
        "magnet_team_id": magnet_team.id if magnet_team else None,
        "users": [
            {
                "id": u.id,
                "full_name": u.full_name,
                "username": u.username,
                "title": u.title,
                "initials": u.initials,
                "phone_number": u.phone_number,
                "image": u.image.url if u.image else None,
                "last_message": u.sent_chats.first().message if u.sent_chats.exists() else "No messages yet",
                "role": get_combined_role(u, selected_team),
                "color": get_user_color(u.id),
                "team_name": selected_team.name if selected_team else "",
                "guests": [
                    {
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
                    } for g in u.assigned_guests.all()
                ]
            } for u in users
        ],
        "users_json": json.dumps([  # keep JSON version of users
            {
                "id": u.id,
                "full_name": u.full_name,
                "username": u.username,
                "title": u.title,
                "initials": u.initials,
                "phone_number": u.phone_number,
                "image": u.image.url if u.image else None,
                "last_message": u.sent_chats.first().message if u.sent_chats.exists() else "No messages yet",
                "role": get_combined_role(u, selected_team),
                "color": get_user_color(u.id),
                "team_name": selected_team.name if selected_team else "",
                "guests": [
                    {
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
                    } for g in u.assigned_guests.all()
                ]
            } for u in users
        ], cls=DjangoJSONEncoder),
        "user_guests_json": json.dumps(user_guests, cls=DjangoJSONEncoder),
        "unassigned_guests_json": json.dumps(unassigned_guests, cls=DjangoJSONEncoder),
        "last_messages_json": json.dumps(last_messages_payload, cls=DjangoJSONEncoder),
        "current_user_id": request.user.id,
        "current_user_role": get_combined_role(request.user, selected_team),
        "attached_guest": {
            "id": attached_guest.id,
            "name": attached_guest.full_name,
            "custom_id": attached_guest.custom_id,
            "image": attached_guest.picture.url if attached_guest.picture else None,
            "title": attached_guest.title,
            "initials": attached_guest.initials,
            "date_of_visit": attached_guest.date_of_visit.strftime("%Y-%m-%d") if attached_guest.date_of_visit else "",
            "assigned": bool(attached_guest.assigned_to)
        } if attached_guest else None,
        "context_user_permissions": json.dumps({
            "is_project_admin": is_project_admin(request.user),
            "is_project_wide_admin": is_project_wide_admin(request.user),
            "is_team_admin": is_team_admin(request.user, selected_team),
            "is_magnet_admin": is_magnet_admin(request.user),
            "is_project_level_role": is_project_level_role(request.user),
            "user_in_groups": user_in_groups(request.user, "Pastor,Admin,Minister,GForce Member"),
            "user_in_team": user_in_team(request.user, selected_team)
        }, cls=DjangoJSONEncoder),
        "page_title": "ChatRoom",
    }
    return render(request, "workforce/chat_room.html", context)


@login_required
def load_more_messages(request):
    """AJAX endpoint to fetch older messages before a given timestamp, scoped by team."""
    before = request.GET.get("before")  # ISO timestamp string
    limit = int(request.GET.get("limit", 50))
    team_id = request.GET.get("team_id")

    qs = ChatMessage.objects.select_related("sender", "guest_card", "parent__sender")

    # 🔹 Filter by team (central or specific)
    if team_id:
        # fetch specific team
        qs = qs.filter(team_id=team_id)
    else:
        # central chat has team = NULL
        qs = qs.filter(team__isnull=True)

    # 🔹 Only older messages than `before`
    if before:
        before_dt = parse_datetime(before)
        if before_dt:
            qs = qs.filter(created_at__lt=before_dt)

    # 🔹 Prebuild mention helpers
    mention_map, mention_regex = build_mention_helpers()

    # 🔹 Fetch newest first, then reverse to chronological order
    messages = list(qs.order_by("-created_at")[:limit])
    messages.reverse()

    payload = [serialize_message(m, mention_map, mention_regex) for m in messages]

    return JsonResponse({"messages": payload})



@csrf_exempt
def upload_file(request):
    """Upload a file (Cloudinary or local) and return full metadata"""
    if request.method != "POST" or "file" not in request.FILES:
        return JsonResponse({"error": "Invalid request"}, status=400)

    f = request.FILES["file"]

    try:
        if not settings.DEBUG:
            # Cloudinary
            import cloudinary.uploader
            result = cloudinary.uploader.upload(
                f,
                folder="chat/files",
                resource_type="auto"
            )
            file_url = result["secure_url"]
            file_path = result["public_id"]
        else:
            # Local dev
            from django.core.files.storage import default_storage
            file_path = default_storage.save(f"chat/files/{f.name}", f)
            file_path = file_path.lstrip("/")
            if file_path.startswith("media/"):
                file_path = file_path[len("media/"):]
            file_url = f"/media/{file_path}"

        guessed_type, _ = mimetypes.guess_type(f.name)

        return JsonResponse({
            "url": file_url,        # always frontend-ready
            "path": file_path,      # store in DB
            "public_id": file_path, # Cloudinary id or local path
            "name": f.name,
            "size": f.size,
            "type": guessed_type or f.content_type or "application/octet-stream",
        })

    except Exception as e:
        import logging
        logging.exception("File upload failed")
        return JsonResponse({"error": str(e)}, status=500)




@csrf_exempt
def fetch_link_preview(request):
    url = request.GET.get("url")
    if not url:
        return JsonResponse({"error": "Missing URL"}, status=400)

    try:
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        title_tag = soup.find("meta", property="og:title") or soup.find("title")
        desc_tag = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        image_tag = soup.find("meta", property="og:image")

        return JsonResponse({
            "url": url,
            "title": title_tag["content"] if title_tag and title_tag.has_attr("content") else (title_tag.string if title_tag else ""),
            "description": desc_tag["content"] if desc_tag and desc_tag.has_attr("content") else "",
            "image": image_tag["content"] if image_tag and image_tag.has_attr("content") else "",
        })
    except Exception as e:
        return JsonResponse({
            "url": url,
            "title": url,  # fallback
            "description": "",
            "image": "",
            "error": str(e)
        }, status=200)



from datetime import datetime, timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import Event, AttendanceRecord, UserActivity
from .utils import validate_church_proximity
from .broadcast import broadcast_attendance_summary


@login_required
@user_passes_test(lambda u: is_project_wide_admin(u))
def attendance_summary(request):
    """Admin/Team dashboard attendance & clock summary view."""
    user = request.user
    today = timezone.localdate()
    last_30_days = today - timedelta(days=30)

    records = get_visible_attendance_records(user, since_date=last_30_days)
    clock_records = get_visible_clock_records(user, since_date=last_30_days)

    # --- Merge Clock Data ---
    clock_map = {(c.user_id, c.event_id, c.date): c for c in clock_records}
    for r in records:
        clock = clock_map.get((r.user_id, r.event_id, r.date))
        r.clock_in_time = clock.clock_in.strftime("%H:%M") if clock and clock.clock_in else None
        r.clock_out_time = clock.clock_out.strftime("%H:%M") if clock and clock.clock_out else None

    # --- Handle AJAX ---
    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("format") == "json":
        data = [
            {
                "date": r.date.strftime("%Y-%m-%d"),
                "event": r.event.name if r.event else "—",
                "team": (r.event.team.name if r.event and r.event.team else r.team.name)
                        if (r.event or r.team) else "—",
                "user": f"{(r.user.title or '')} {r.user.get_full_name()}".strip(),
                "status": r.status,
                "remarks": r.remarks or "—",
                "clock_in": r.clock_in_time or "—",
                "clock_out": r.clock_out_time or "—",
            }
            for r in records
        ]
        return JsonResponse({"records": data})

    return render(request, "accounts/admin_dashboard.html", {"records": records})







@login_required
def mark_attendance(request):
    """Handles attendance marking — supports AJAX for no page reload."""
    today = timezone.localdate()
    now = timezone.localtime()
    weekday = today.strftime("%A").lower()

    # ✅ Use team-aware helper to get only events user can mark
    events = get_available_events_for_user(request.user)
    available_events = []

    for e in events:
        if e.event_type == "followup":
            available_events.append(e)
        elif e.day_of_week and e.day_of_week.lower() == weekday:
            available_events.append(e)
        elif e.event_type == "meeting" and weekday == "wednesday":
            available_events.append(e)

    # Only show “other” when there are real events
    actual_events_today = [e for e in available_events if e.event_type != "followup"]
    show_other_option = len(actual_events_today) > 0

    # Weekly guest activity check
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    guest_activity_types = ["followup", "message", "guest_view", "call", "report", "other"]

    user_guest_activity = UserActivity.objects.filter(
        user=request.user,
        activity_type__in=guest_activity_types,
        created_at__date__gte=week_start,
        created_at__date__lte=week_end,
    ).exists()

    # Whether user can mark now
    can_mark_now = any(
        e.time is None or now >= timezone.make_aware(datetime.combine(today, e.time))
        for e in actual_events_today
    )

    # --- Handle POST ---
    if request.method == "POST":
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

        event_id = request.POST.get("event_id", "").strip()
        remarks = request.POST.get("remarks", "").strip()
        status = request.POST.get("status", "present")
        user_lat = request.POST.get("latitude")
        user_lon = request.POST.get("longitude")
        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"

        # 🔹 Validate event_id before querying
        if not event_id:
            if is_ajax:
                return JsonResponse({"success": False, "error": "Missing event ID"}, status=400)
            messages.error(request, "Invalid or missing event ID.")
            return HttpResponseRedirect(next_url)

        if event_id == "other":
            custom_name = request.POST.get("custom_event") or "Custom Event"
            event, _ = Event.objects.get_or_create(
                name=custom_name, event_type="custom", date=today
            )
        else:
            try:
                event = Event.objects.get(id=int(event_id))
            except (Event.DoesNotExist, ValueError):
                if is_ajax:
                    return JsonResponse({"success": False, "error": "Event not found"}, status=404)
                messages.error(request, "Event not found.")
                return HttpResponseRedirect(next_url)

        # ✅ Enforce physical presence validation for physical events
        mode = (getattr(event, "attendance_mode", "") or "").lower()
        is_physical = mode == "physical"

        if status == "present" and is_physical:
            try:
                print(f"[DEBUG] Checking proximity for {request.user} at {user_lat},{user_lon}")
                validate_church_proximity(user_lat, user_lon)
            except ValidationError as e:
                print(f"[DEBUG] Validation failed: {e}")
                if is_ajax:
                    # JSON response → frontend toast, modal stays open
                    return JsonResponse({"success": False, "error": str(e)}, status=400)
                else:
                    # Fallback for non-AJAX form
                    messages.error(request, str(e))
                    return HttpResponseRedirect(next_url)

        # Determine lateness
        if status == "present" and event.time:
            event_dt = datetime.combine(today, event.time)
            if now > timezone.make_aware(event_dt + timedelta(minutes=15)):
                status = "late"

        # ✅ Check if attendance already marked today
        existing = AttendanceRecord.objects.filter(
            user=request.user,
            event=event,
            date=today
        ).first()

        if existing:
            if is_ajax:
                return JsonResponse({
                    "success": False,
                    "error": f"You have already marked attendance for {event.name} today."
                }, status=400)
            else:
                messages.warning(request, f"You have already marked attendance for {event.name} today.")
                return HttpResponseRedirect(next_url)

        # Save record
        AttendanceRecord.objects.create(
            user=request.user,
            event=event,
            date=today,
            status=status,
            remarks=remarks,
            team=event.team,
        )

        # 🔔 Notify live dashboard
        broadcast_attendance_summary()

        message_text = f"Attendance marked for {event.name} ({status})."
        if is_ajax:
            return JsonResponse({"success": True, "message": message_text})
        else:
            messages.success(request, message_text)
            return HttpResponseRedirect(next_url)

    context = {
        "events": available_events,
        "show_other_option": show_other_option,
        "skip_attendance": user_guest_activity,
        "can_mark_now": can_mark_now,
        "show_weekly_summary": today.weekday() == 5 and now.hour >= 20,
    }
    return render(request, "workforce/mark_attendance.html", context)



from datetime import timedelta
from django.utils import timezone
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Event, AttendanceRecord
from django.db.models import Q






@login_required
def add_personal_reminder(request):
    if request.method == "POST":
        title = request.POST.get("title")
        description = request.POST.get("description")
        date = request.POST.get("date")
        time = request.POST.get("time") or None

        PersonalReminder.objects.create(
            user=request.user,
            title=title,
            description=description,
            date=date,
            time=time
        )
        messages.success(request, "Reminder added!")
        return redirect("accounts:admin-dashboard")

    return render(request, "workforce/add_reminder.html")


from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import EventForm

from django.template.loader import render_to_string
from django.http import JsonResponse

@login_required
def manage_events(request):
    if not is_project_wide_admin(request.user) or is_team_admin(request.user, "Minister-in-Charge"):
        return HttpResponseForbidden("You don't have permission to manage events.")

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            event.save()

            html = render_to_string("workforce/partials/event_item.html", {"event": event})
            return JsonResponse({"status": "success", "html": html})
        return JsonResponse({"status": "error", "errors": form.errors}, status=400)

    form = EventForm()
    events = Event.objects.filter(is_active=True).order_by("date")
    return render(
        request,
        "workforce/manage_events.html",
        {"form": form, "events": events, "page_title": "Programmes"},
    )



@login_required
def edit_event(request, pk):
    event = get_object_or_404(Event, pk=pk)

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            event = form.save(commit=False)

            # Handle postponed logic properly
            if event.postponed:
                # If postponed but date/time not set, keep as TBD
                if not event.date and not event.time:
                    event.date = None
                    event.end_date = None
                    event.time = None
                # Else: postponed *to* new date/time, so we keep those values
            else:
                # If not postponed anymore but was previously postponed, leave dates as they are
                pass

            # Handle existing image preservation
            if not request.FILES.get("event_image") and "existing_image" in request.POST:
                pass  # keep current

            event.save()

            html = render_to_string("workforce/partials/event_item.html", {"event": event})
            return JsonResponse({"status": "success", "html": html})

        return JsonResponse({"status": "error", "errors": form.errors}, status=400)

    return JsonResponse({"status": "invalid"}, status=405)




@login_required
def delete_event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    event.delete()
    return JsonResponse({"status": "deleted"})




from datetime import date, datetime, timedelta, time
from django.utils import timezone
from django.http import JsonResponse


from datetime import date, timedelta
from django.http import JsonResponse

from datetime import date, datetime, timedelta
from django.http import JsonResponse
from django.utils import timezone
from workforce.models import Event
from workforce.utils import get_available_events_for_user



def api_events(request):
    """
    Unified API endpoint:
      - FullCalendar (with start/end params)
      - Team Modal (with team_id)
    """
    user = request.user
    team_id = request.GET.get("team_id")
    start = request.GET.get("start")
    end = request.GET.get("end")

    events = get_available_events_for_user(user)
    today = timezone.localdate()

    # 🟦 CASE 1 — Modal events by team_id
    if team_id is not None:
        data = expand_team_events(user, team_id)
        return JsonResponse({"events": data})

    # 🟩 CASE 2 — FullCalendar events (default path)
    weekday_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    }

    color_map = {
        "service": "#3b82f6",
        "meeting": "#10b981",
        "training": "#8b5cf6",
        "reminder": "#f59e0b",
        "event": "#e11d48",
        "other": "#9ca3af",
    }

    today = date.today()
    start_of_year = date(today.year, 1, 1)
    end_of_year = date(today.year, 12, 31)

    data = []

    def build_datetime(d, t):
        if not t:
            return d.isoformat()
        return datetime.combine(d, t).isoformat()

    for e in events:
        event_type = (e.event_type or "other").lower()
        color = color_map.get(event_type, "#4dabf7")

        base_event = {
            "title": e.name,
            "color": color,
            "extendedProps": {
                "type": e.event_type,
                "mode": getattr(e, "attendance_mode", ""),
                "location": getattr(e, "location", ""),
                "description": getattr(e, "description", ""),
                "time": e.time.strftime("%H:%M") if e.time else None,
                "team": getattr(e.team, "name", None),
                "team_color": getattr(e.team, "color_class", "bg-gray-800")
                if getattr(e, "team", None)
                else None,
            },
        }

        # Handle fixed-date events
        if e.date:
            start_date = e.date
            end_date = e.end_date or (
                start_date + timedelta(days=getattr(e, "duration_days", 1) - 1)
            )
            base_event["start"] = build_datetime(start_date, e.time)
            base_event["end"] = build_datetime(end_date, e.time)
            data.append(base_event)

        # Handle recurring events
        elif e.is_recurring_weekly and e.day_of_week:
            weekday = weekday_map.get(e.day_of_week.lower())
            if weekday is not None:
                current = start_of_year
                while current <= end_of_year:
                    if current.weekday() == weekday:
                        recurring = base_event.copy()
                        recurring["start"] = build_datetime(current, e.time)
                        data.append(recurring)
                    current += timedelta(days=1)

    return JsonResponse(data, safe=False)






from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import json
from .models import UserActivity

@csrf_exempt
@login_required
def log_user_activity(request):
    """Silent logging endpoint for guest/follow-up interactions."""
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
            activity_type = data.get("activity_type", "other")
            guest_id = data.get("guest_id")
            description = data.get("description", "")

            UserActivity.objects.create(
                user=request.user,
                activity_type=activity_type,
                guest_id=guest_id,
                description=description,
                created_at=timezone.now(),
            )

            return JsonResponse({"status": "success"}, status=201)
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
    return JsonResponse({"status": "invalid_request"}, status=405)


from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Event

@login_required
def get_active_events(request):
    """
    Returns active events — both one-time (with date) and recurring (without date).
    """
    events = get_available_events_for_user(request.user)
    data = []

    for e in events:
        # Handle one-time events
        if e.date:
            date_str = e.date.strftime("%Y-%m-%d")
            time_str = e.time.strftime("%H:%M") if e.time else None
            label = e.name
        else:
            # Recurring events (like weekly services)
            date_str = None
            time_str = e.time.strftime("%H:%M") if e.time else None
            label = f"{e.name} (Recurring)"

        data.append({
            "id": e.id,
            "name": label,
            "date": date_str,
            "time": time_str,
            "event_type": e.event_type,
            "is_recurring": not bool(e.date),
        })

    return JsonResponse(data, safe=False)