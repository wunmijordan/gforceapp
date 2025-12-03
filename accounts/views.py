from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test, login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.urls import reverse_lazy, reverse
from django.utils.timezone import localtime, now
import pytz, requests, re, calendar, json, mimetypes, os
from django.contrib.auth import get_user_model
from guests.models import GuestEntry
from .models import CustomUser, TeamMembership
from django.contrib.auth.forms import SetPasswordForm
from django.core.paginator import Paginator
from django.db.models import Q, Count, Prefetch
from datetime import datetime, timedelta
from django.db.models.functions import ExtractMonth
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.models import Group
from .forms import CustomUserCreationForm, CustomUserChangeForm, GroupForm
from .utils import (
    user_in_groups,
    is_project_wide_admin,
    is_magnet_admin,
    is_team_admin,
    is_project_admin,
    is_project_level_role,
    user_in_team,
)
from workforce.consumers import get_user_color
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from django.core.files.storage import default_storage
import urllib.parse
from django.conf import settings
from workforce.utils import (
    get_calendar_items,
    get_available_events_for_user,
    get_available_teams_for_user,
    expand_team_events,
    get_visible_attendance_records,
    get_visible_clock_records,
)
from workforce.models import AttendanceRecord, Team, ClockRecord
from collections import defaultdict
from django.utils import timezone





User = get_user_model()

DAY_QUOTES = {
    'Monday': "Start strong — the harvest is plenty!",
    'Tuesday': "God doesn't call the qualified — He qualifies the called.",
    'Wednesday': "It's the hump of the week. You're not alone in this mission.", 
    'Thursday': "It's Midweek Recharge: Reload your Artillery.",
    'Friday': "The weekend is here — prepare for His people.",
    'Saturday': "Pray. Plan. Prepare for the Sunday harvest.",
    'Sunday': "Today is the Lord’s day — Souls are waiting!",
}


class CustomLoginForm(AuthenticationForm):
    pass


class CustomLoginView(LoginView):
    form_class = CustomLoginForm
    template_name = 'accounts/login.html'

    def form_valid(self, form):
        remember_me = self.request.POST.get('remember_me')
        if not remember_me:
            self.request.session.set_expiry(0)
        else:
            self.request.session.set_expiry(60 * 60 * 24 * 28)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('workforce:chat_room')


def post_login_redirect(request):
    tz = pytz.timezone('Africa/Lagos')
    now_in_wat = localtime(now(), timezone=tz)
    today_str = now_in_wat.strftime('%Y-%m-%d')
    day_name = now_in_wat.strftime('%A')
    time_str = now_in_wat.strftime('%I:%M %p')

    if request.session.get('welcome_shown') != today_str:
        request.session['welcome_shown'] = today_str
        request.session.modified = True
        quote = DAY_QUOTES.get(day_name, "Stay faithful — your work in the Kingdom is never in vain.")

        # Everyone with elevated roles goes to admin_dashboard
        if user_in_groups(request.user, "Pastor,Team Lead,Message Manager,Registrant,Admin"):
            dashboard_url = reverse('accounts:admin_dashboard')
            dashboard_label = "Proceed to Dashboard"
        else:
            dashboard_url = reverse('dashboard')
            dashboard_label = "Proceed to Dashboard"

        return render(request, 'accounts/welcome_modal.html', {
            'day_name': day_name,
            'time_str': time_str,
            'quote': quote,
            'dashboard_url': dashboard_url,
            'dashboard_label': dashboard_label,
        })

    # If welcome already shown
    if user_in_groups(request.user, "Pastor,Team Lead,Message Manager,Registrant,Admin"):
        return redirect('accounts:admin_dashboard')
    else:
        return redirect('dashboard')



User = get_user_model()




@login_required
@user_passes_test(lambda u: is_project_wide_admin(u))
def admin_dashboard(request):
    """
    Optimized Admin/Superuser dashboard with full backward compatibility.
    - Single-query aggregations
    - Prefetch related objects
    - All old context variables preserved
    """
    user = request.user
    today = timezone.localdate()
    current_year = today.year
    last_30_days = today - timedelta(days=30)

    # ---------------------- Base queryset ----------------------
    if user.is_superuser:
        queryset = GuestEntry.objects.all()
        users = CustomUser.objects.all().order_by("full_name")
    elif is_project_admin(user) or is_magnet_admin(user):
        queryset = GuestEntry.objects.all()
        users = CustomUser.objects.filter(is_superuser=False).order_by("full_name")
    elif is_team_admin(user):
        queryset = GuestEntry.objects.none()
        users = None
    else:
        queryset = GuestEntry.objects.none()
        users = None

    # ---------------------- Available years ----------------------
    available_years = queryset.dates('date_of_visit', 'year')
    available_years = [d.year for d in available_years]

    # ---------------------- Yearly guest summary ----------------------
    year = request.GET.get('year', current_year)
    try:
        year = int(year)
    except (TypeError, ValueError):
        year = current_year

    guests_this_year = queryset.filter(date_of_visit__year=year)

    month_counts_qs = guests_this_year.annotate(
        month=ExtractMonth('date_of_visit')
    ).values('month').annotate(count=Count('id')).order_by('month')

    month_counts = {m: 0 for m in range(1, 13)}
    for entry in month_counts_qs:
        month_counts[entry['month']] = entry['count']

    max_count = max(month_counts.values(), default=0)
    min_count = min(month_counts.values(), default=0)
    avg_count = sum(month_counts.values()) // 12 if month_counts else 0
    max_month = next((calendar.month_name[m] for m, c in month_counts.items() if c == max_count), "N/A")
    min_month = next((calendar.month_name[m] for m, c in month_counts.items() if c == min_count), "N/A")

    percent = lambda c: round((c / max_count) * 100, 1) if max_count else 0

    summary_data = {
        'max_month': max_month,
        'max_count': max_count,
        'max_percent': percent(max_count),
        'min_month': min_month,
        'min_count': min_count,
        'min_percent': percent(min_count),
        'avg_count': avg_count,
        'avg_percent': percent(avg_count),
        'total_count': guests_this_year.count(),
    }

    # ---------------------- Aggregated counts ----------------------
    service_data = queryset.values('service_attended').annotate(count=Count('id')).order_by('-count')
    service_labels = [s['service_attended'] or "Not Specified" for s in service_data]
    service_counts = [s['count'] for s in service_data]

    channel_data = queryset.values('channel_of_visit').annotate(count=Count('id')).order_by('-count')
    total_channels = sum(c['count'] for c in channel_data)
    channel_progress = [
        {'label': c['channel_of_visit'] or "Unknown",
         'count': c['count'],
         'percent': round((c['count'] / total_channels) * 100, 2) if total_channels else 0}
        for c in channel_data
    ]

    # Purpose breakdown
    purposes = ["Home Church", "Occasional Visit", "One-Time Visit", "Special Programme"]
    total_purposes = queryset.count()
    purpose_stats = {}
    # Individual counts for backward compatibility
    for p in purposes:
        count = queryset.filter(purpose_of_visit__iexact=p).count()
        percentage = round((count / total_purposes) * 100, 1) if total_purposes else 0
        purpose_stats[p] = {'count': count, 'percentage': percentage}
    home_church_count = purpose_stats["Home Church"]["count"]
    home_church_percentage = purpose_stats["Home Church"]["percentage"]
    occasional_visit_count = purpose_stats["Occasional Visit"]["count"]
    occasional_visit_percentage = purpose_stats["Occasional Visit"]["percentage"]
    one_time_visit_count = purpose_stats["One-Time Visit"]["count"]
    one_time_visit_percentage = purpose_stats["One-Time Visit"]["percentage"]
    special_programme_count = purpose_stats["Special Programme"]["count"]
    special_programme_percentage = purpose_stats["Special Programme"]["percentage"]

    # Most attended service
    if service_data:
        most_attended_service = service_data[0]['service_attended'] or "Not Specified"
        most_attended_count = service_data[0]['count']
        total_services = sum(s['count'] for s in service_data)
        attendance_rate = round((most_attended_count / total_services) * 100, 1) if total_services else 0
    else:
        most_attended_service, most_attended_count, attendance_rate = "No Data", 0, 0

    # Status counts
    status_data = queryset.values('status').annotate(count=Count('id'))
    status_labels = [s['status'] or "Unknown" for s in status_data]
    status_counts = [s['count'] for s in status_data]

    planted_count = queryset.filter(status="Planted").count()
    planted_elsewhere_count = queryset.filter(status="Planted Elsewhere").count()
    relocated_count = queryset.filter(status="Relocated").count()
    work_in_progress_count = queryset.filter(status="Work in Progress").count()

    # ---------------------- Monthly increase ----------------------
    first_day_this_month = today.replace(day=1)
    last_month_end = first_day_this_month - timedelta(days=1)
    first_day_last_month = last_month_end.replace(day=1)

    current_month_count = queryset.filter(date_of_visit__gte=first_day_this_month, date_of_visit__lte=today).count()
    last_month_count = queryset.filter(date_of_visit__gte=first_day_last_month, date_of_visit__lte=last_month_end).count()

    increase_rate = round(((current_month_count - last_month_count) / last_month_count) * 100, 1) if last_month_count else (100 if current_month_count else 0)
    percent_change = increase_rate

    # ---------------------- User-specific metrics ----------------------
    user_total_guest_entries = queryset.filter(assigned_to=user).count()
    user_current_month_count = queryset.filter(assigned_to=user, date_of_visit__gte=first_day_this_month, date_of_visit__lte=today).count()
    user_last_month_count = queryset.filter(assigned_to=user, date_of_visit__gte=first_day_last_month, date_of_visit__lte=last_month_end).count()

    if user_last_month_count == 0:
        user_diff_percent = 100 if user_current_month_count else 0
        user_diff_positive = True
    else:
        diff = ((user_current_month_count - user_last_month_count) / user_last_month_count) * 100
        user_diff_percent = round(abs(diff), 1)
        user_diff_positive = diff >= 0

    # Planted guests growth
    user_planted_total = queryset.filter(assigned_to=user, status="Planted").count()
    planted_growth_rate = round((user_planted_total / user_total_guest_entries) * 100, 1) if user_total_guest_entries else 0

    user_planted_current_month = queryset.filter(assigned_to=user, status="Planted", date_of_visit__gte=first_day_this_month, date_of_visit__lte=today).count()
    user_planted_last_month = queryset.filter(assigned_to=user, status="Planted", date_of_visit__gte=first_day_last_month, date_of_visit__lte=last_month_end).count()
    planted_growth_change = round(((user_planted_current_month - user_planted_last_month) / user_planted_last_month) * 100, 1) if user_planted_last_month else (100 if user_planted_current_month else 0)

    # ---------------------- Teams & Users ----------------------
    user_teams = Team.objects.filter(memberships__user=user).prefetch_related('memberships__user').distinct()
    if user.is_superuser:
        other_users = CustomUser.objects.exclude(id=request.user.id)
    else:
        other_users = CustomUser.objects.filter(
            team_memberships__team__in=user_teams
        ).exclude(id=user.id).distinct()
    other_users = [u for u in other_users if not is_project_admin(u)]
    for u in other_users:
        u.color = get_user_color(u.id)

    team_member_pairs = [(team, [u for u in other_users if u.team_memberships.filter(team=team).exists()]) for team in user_teams]

    # ---------------------- Calendar & attendance ----------------------
    calendar_items = get_calendar_items(user)
    records = get_visible_attendance_records(user, since_date=last_30_days)
    clock_records = get_visible_clock_records(user, since_date=last_30_days)

    clock_map = {(c.user_id, c.event_id, c.date): c for c in clock_records}
    for r in records:
        clock = clock_map.get((r.user_id, r.event_id, r.date))
        r.clock_in_time = timezone.localtime(clock.clock_in).strftime("%H:%M") if clock and clock.clock_in else None
        r.clock_out_time = timezone.localtime(clock.clock_out).strftime("%H:%M") if clock and clock.clock_out else None

    total_clock_in = clock_records.filter(clock_in__isnull=False).count()
    total_clock_out = clock_records.filter(clock_out__isnull=False).count()
    today_record = clock_records.filter(date=today).first()

    # ---------------------- Events ----------------------
    events = []
    base_events = get_available_events_for_user(user)
    for team in [None] + list(Team.objects.all()):
        events.extend(expand_team_events(user, getattr(team, 'id', None)))
    upcoming_events = sorted([e for e in events if e['date'] >= today], key=lambda e: (e['date'], e.get('time', "")))

    user_team_ids = [t.id for t in user_teams]
    user_is_global = user.is_superuser or user.groups.filter(name__in=["Pastor", "Admin"]).exists()
    start_of_sunday = today - timedelta(days=(today.isoweekday() % 7))
    end_of_week = start_of_sunday + timedelta(days=6)
    weekly_events = [e for e in upcoming_events if start_of_sunday <= e["date"] <= end_of_week and (user_is_global or e.get("team_id") in user_team_ids)]
    for e in weekly_events:
        e["datetime_iso"] = f"{e['date']}T{e.get('time', '00:00:00')}"
    next_events = weekly_events

    # ---------------------- Context user permissions ----------------------
    selected_team = None
    selected_team_id = request.GET.get('team')
    if selected_team_id:
        try:
            selected_team = Team.objects.get(id=int(selected_team_id))
        except (Team.DoesNotExist, ValueError, TypeError):
            selected_team = None

    context_user_permissions = json.dumps({
        'is_project_admin': is_project_admin(user),
        'is_project_wide_admin': is_project_wide_admin(user),
        'is_team_admin': is_team_admin(user, selected_team),
        'is_magnet_admin': is_magnet_admin(user),
        'is_project_level_role': is_project_level_role(user),
        'user_in_groups': user_in_groups(user, "Pastor,Admin,Minister,GForce Member"),
        'user_in_team': user_in_team(user, selected_team)
    }, cls=DjangoJSONEncoder)

    # ---------------------- Context ----------------------
    context = {
        'show_filters': False,
        'available_years': available_years,
        'current_year': current_year,
        'summary_data': summary_data,
        'service_labels': service_labels,
        'service_counts': service_counts,
        'status_labels': status_labels,
        'status_counts': status_counts,
        'channel_progress': channel_progress,
        'planted_count': planted_count,
        'planted_elsewhere_count': planted_elsewhere_count,
        'relocated_count': relocated_count,
        'work_in_progress_count': work_in_progress_count,
        'total_guests': queryset.count(),
        'increase_rate': increase_rate,
        'percent_change': percent_change,
        'user_total_guest_entries': user_total_guest_entries,
        'user_guest_entry_diff_percent': user_diff_percent,
        'user_guest_entry_diff_positive': user_diff_positive,
        'user_planted_total': user_planted_total,
        'planted_growth_rate': planted_growth_rate,
        'planted_growth_change': planted_growth_change,
        'most_attended_service': most_attended_service,
        'most_attended_count': most_attended_count,
        'attendance_rate': attendance_rate,
        'home_church_count': home_church_count,
        'home_church_percentage': home_church_percentage,
        'occasional_visit_count': occasional_visit_count,
        'occasional_visit_percentage': occasional_visit_percentage,
        'one_time_visit_count': one_time_visit_count,
        'one_time_visit_percentage': one_time_visit_percentage,
        'special_programme_count': special_programme_count,
        'special_programme_percentage': special_programme_percentage,
        'purpose_stats': purpose_stats,
        'users': users,
        'other_users': other_users,
        'user_teams': user_teams,
        'team_member_pairs': team_member_pairs,
        'calendar_items': calendar_items,
        'records': records,
        'clock_records': clock_records,
        'total_clock_in': total_clock_in,
        'total_clock_out': total_clock_out,
        'today_clock_in': getattr(today_record, 'clock_in', None),
        'today_clock_out': getattr(today_record, 'clock_out', None),
        'available_events': upcoming_events,
        'available_teams': get_available_teams_for_user(user),
        'next_events_for_week': next_events,
        'context_user_permissions': context_user_permissions,
        'page_title': "Admin Dashboard",
    }

    return render(request, "accounts/admin_dashboard.html", context)










from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.core.paginator import Paginator
from django.contrib.auth.forms import SetPasswordForm

from .models import CustomUser



from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import render, redirect
from .models import CustomUser

@login_required
def user_list(request):
    """
    Display users for admin dashboard with search and pagination.
    Superusers see all users. Admin group sees non-superusers only.
    """
    search_query = request.GET.get('q', '')


    # Determine accessible users
    if request.user.is_superuser:
        users = CustomUser.objects.all()
    # 2️⃣ Project admins (Pastor/Admin) see all users
    elif is_project_admin(request.user):
        users = CustomUser.objects.filter(is_superuser=False)

    # 3️⃣ Team admins (e.g. MIC, Head of Unit) see users from *their own team(s) only*
    elif is_team_admin(request.user):
        # Teams where the user is a MIC or Team Admin
        admin_teams = Team.objects.filter(
            memberships__user=request.user,
            memberships__team_role__in=["Minister-in-Charge", "Team Admin"]
        )

        # All users in those teams
        users_in_teams = CustomUser.objects.filter(
            team_memberships__team__in=admin_teams
        ).distinct()

        # Exclude project-level admins
        users = users_in_teams.exclude(
            Q(is_superuser=True) |
            Q(groups__name__in=["Pastor", "Admin"]) |
            Q(title__iexact="Pastor") |
            Q(title__iexact="Admin")
        ).distinct()
    else:
        messages.error(request, "You do not have permission to view users.")
        return redirect('accounts:admin_dashboard')

    # Apply search filter
    if search_query:
        users = users.filter(
            Q(full_name__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(team_memberships__team__name__icontains=search_query)
        ).distinct()

    # Pagination
    view_type = request.GET.get('view', 'cards')
    per_page = 50 if view_type == 'list' else 45
    paginator = Paginator(users, per_page)  # <-- paginate filtered users
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'accounts/user_list.html', {
        'users': page_obj.object_list,
        'page_obj': page_obj,
        'view_type': view_type,
        'search_query': search_query,
        'page_title': 'Team'
    })



from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib import messages
from .models import CustomUser, TeamMembership
from .forms import CustomUserCreationForm, CustomUserChangeForm
from workforce.models import Team
from .utils import user_in_groups  # if you already have this helper


@login_required
def manage_user(request, user_id=None):
    """
    Combined create/edit view for users.
    Includes preloadedTeamRoles for frontend JS handling.
    """
    is_edit = user_id is not None
    user_obj = get_object_or_404(CustomUser, pk=user_id) if is_edit else None

    # Permission checks
    if not is_magnet_admin(request.user):
        messages.error(request, "You do not have permission to manage users.")
        return redirect("accounts:user_list")

    if is_edit and not request.user.is_superuser and user_obj.is_superuser:
        messages.error(request, "You cannot edit a superuser.")
        return redirect("accounts:user_list")

    # Choose form type
    FormClass = CustomUserChangeForm if is_edit else CustomUserCreationForm
    form_kwargs = {
        "data": request.POST or None,
        "files": request.FILES or None,
        "instance": user_obj,
        "current_user": request.user,
    }

    # Only pass edit_mode to the change form
    if is_edit and FormClass is CustomUserChangeForm:
        form_kwargs["edit_mode"] = True

    form = FormClass(**form_kwargs)

    password_form = SetPasswordForm(user_obj) if is_edit else None

    # ---- Handle POST actions ----
    if request.method == "POST":
        # Delete
        if "delete_user" in request.POST and is_edit:
            if user_obj.is_superuser:
                messages.error(request, "Cannot delete a superuser.")
            else:
                user_obj.delete()
                messages.success(request, f"User {user_obj.full_name} deleted successfully.")
            return redirect("accounts:user_list")

        # Deactivate / Reactivate
        elif "deactivate_user" in request.POST and is_edit:
            if user_obj.is_superuser:
                messages.error(request, "Cannot deactivate a superuser.")
            else:
                user_obj.is_active = not user_obj.is_active
                user_obj.save()
                status = "activated" if user_obj.is_active else "deactivated"
                messages.success(request, f"User {user_obj.full_name} {status} successfully.")
            return redirect("accounts:user_list")

        # Change password
        elif "change_password" in request.POST and is_edit:
            password_form = SetPasswordForm(user_obj, request.POST)
            if password_form.is_valid():
                password_form.save()
                messages.success(request, f"Password updated for {user_obj.full_name}.")
                return redirect("accounts:user_list")
            else:
                messages.error(request, "Please correct the password errors.")

        # Create or update user
        else:
            # Superuser creation restriction
            if not request.user.is_superuser:
                form.instance.is_superuser = False

            if form.is_valid():
                saved_user = form.save()
                action = "updated" if is_edit else "created"
                messages.success(request, f"User {saved_user.full_name} {action} successfully!")

                if "save_return" in request.POST:
                    return redirect("accounts:user_list")
                elif "save_add_another" in request.POST:
                    return redirect("accounts:create_user")
            else:
                messages.error(request, "Please correct the errors below.")

    # ---- Preload Team Roles for JS ----
    teams = Team.objects.all()
    team_roles = [
        {
            "id": team.id,
            "name": team.name,
            "color_class": team.color_class,
            "color_hex": team.color_hex,
        }
        for team in Team.objects.all()
    ]
    memberships = (
        list(
            TeamMembership.objects.filter(user=user_obj).values(
                "team_id", "team__name", "team_role"
            )
        )
        if is_edit
        else []
    )

    preloadedTeamRoles = {
        "teams": team_roles,
        "userMemberships": memberships,
    }

    return render(
        request,
        "accounts/user_form.html",
        {
            "form": form,
            "edit_mode": is_edit,
            "user_obj": user_obj,
            "password_form": password_form,
            "preloadedTeamRoles": preloadedTeamRoles,
            "page_title": "Team",
        },
    )





@login_required
def manage_groups(request):
    groups = Group.objects.all().order_by("name")
    form = GroupForm(request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            group = form.save()
            messages.success(request, f"Group '{group.name}' created successfully.")
            return redirect("accounts:manage_groups")
        else:
            messages.error(request, "Error creating group. Please try again.")

    return render(request, "accounts/manage_groups.html", {
        "groups": groups,
        "form": form,
    })


@login_required
def delete_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    # Prevent deletion of important groups
    if group.name in ["Admin", "Pastor", "Minister", "GForce Member"]:
        messages.error(request, f"Cannot delete the '{group.name}' group.")
        return redirect("accounts:manage_groups")

    # Prevent deletion if users are assigned to the group
    if group.user_set.exists():
        messages.error(request, f"Cannot delete '{group.name}' because users are assigned to it.")
        return redirect("accounts:manage_groups")

    group.delete()
    messages.success(request, f"Group '{group.name}' deleted successfully.")
    return redirect("accounts:manage_groups")





# accounts/views.py
from django.http import JsonResponse
from workforce.models import Team


def load_teams(request):
    group_name = request.GET.get('group')
    teams = Team.objects.filter(is_active=True).values('id', 'name')
    return JsonResponse(list(teams), safe=False)


def load_roles(request):
    group_name = request.GET.get('group')
    all_roles = [
        "Minister-in-Charge", "Head of Unit", "Asst. Head of Unit",
        "Team Admin", "Subleader", "Member"
    ]
    if group_name in ["Admin", "GForce Member"]:
        all_roles.remove("Minister-in-Charge")
    return JsonResponse(all_roles, safe=False)




@login_required
def attendance_summary(request):
    user = request.user
    target_user = user
    user_id = request.GET.get("user_id")

    today = timezone.localdate()
    last_30_days = today - timedelta(days=30)

    # 🧠 Project admin system summary (no user selected)
    if is_project_admin(user) and not user_id:
        total_users = CustomUser.objects.filter(is_active=True, is_superuser=False).count() or 1

        # Aggregate attendance over last 30 days
        records = AttendanceRecord.objects.filter(
            user__is_superuser=False,
            date__gte=last_30_days
        )

        present = records.filter(status="present").count()
        excused = records.filter(status="excused").count()
        absent = records.filter(status="absent").count()

        # Convert to percentages
        def pct(value):
            return round((value / total_users) * 100, 1)

        present_pct = pct(present)
        excused_pct = pct(excused)
        absent_pct = pct(absent)

        # Clock summaries (total)
        total_clock_in = ClockRecord.objects.filter(clock_in__isnull=False, user__is_superuser=False).count()
        total_clock_out = ClockRecord.objects.filter(clock_out__isnull=False, user__is_superuser=False).count()

        clock_in_pct = pct(total_clock_in)
        clock_out_pct = pct(total_clock_out)

        return JsonResponse({
            "summary": {
                "present": f"{present_pct}%",
                "excused": f"{excused_pct}%",
                "absent": f"{absent_pct}%",
            },
            "today": {
                "clocked_in": False,
                "clock_in": None,
                "clock_out": None,
            },
            "totals": {
                "clock_in": f"{clock_in_pct}%",
                "clock_out": f"{clock_out_pct}%",
            },
        })

    # 🧍 Regular or user-specific summary
    if user_id and is_project_admin(user):
        target_user = get_object_or_404(CustomUser, id=user_id)

    # Attendance counts (last 30 days)
    records = AttendanceRecord.objects.filter(user=target_user, date__gte=last_30_days)
    present = records.filter(status="present").count()
    excused = records.filter(status="excused").count()
    absent = records.filter(status="absent").count()

    # Today's clock record
    today_clock = ClockRecord.objects.filter(user=target_user, date=today).first()
    clocked_in = today_clock.is_clocked_in if today_clock else False

    # Total clock summaries (lifetime)
    total_clock_in = ClockRecord.objects.filter(user=target_user, clock_in__isnull=False).count()
    total_clock_out = ClockRecord.objects.filter(user=target_user, clock_out__isnull=False).count()

    return JsonResponse({
        "summary": {
            "present": present,
            "excused": excused,
            "absent": absent,
        },
        "today": {
            "clocked_in": clocked_in,
            "attendance_marked": today_clock is not None,
            "clock_in": today_clock.clock_in.strftime("%H:%M") if today_clock and today_clock.clock_in else None,
            "clock_out": today_clock.clock_out.strftime("%H:%M") if today_clock and today_clock.clock_out else None,
        },
        "totals": {
            "clock_in": total_clock_in,
            "clock_out": total_clock_out,
        },
    })





from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from workforce.models import ClockRecord, Event

CHURCH_LAT, CHURCH_LON = 6.641732871081892, 3.3706539797031843
THRESHOLD_KM = 0.01  # ~10 meters


def haversine_distance(lat1, lon1, lat2, lon2):
    import math
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(d_lon / 2) ** 2)
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


@login_required
def clock_action(request):
    """Handles only clock-out — clock-in now happens during attendance marking."""
    user = request.user
    today = timezone.localdate()
    event_id = request.POST.get("event_id")
    latitude = request.POST.get("latitude")
    longitude = request.POST.get("longitude")
    action = request.POST.get("action")

    if not action or action not in ["clock_in", "clock_out"]:
        return JsonResponse({"success": False, "error": "Invalid or missing action."}, status=400)

    event = Event.objects.filter(id=event_id).first()
    if not event:
        return JsonResponse({"success": False, "error": "Event not found."}, status=404)

    clock, _ = ClockRecord.objects.get_or_create(user=user, date=today, event=event)

    # Handle clock-out validation (with GPS)
    if action == "clock_out":
        if event and event.attendance_mode.lower() == "physical":
            try:
                distance_km = haversine_distance(float(latitude), float(longitude), CHURCH_LAT, CHURCH_LON)
                if distance_km > THRESHOLD_KM:
                    return JsonResponse({"success": False, "error": "You are outside the allowed range for clock-out."})
            except Exception:
                return JsonResponse({"success": False, "error": "Unable to verify your location."})

        # Prevent duplicate clock-out
        if clock.clock_out:
            return JsonResponse({"success": False, "error": "You have already clocked out today."})
        clock.mark_clock_out()

    elif action == "clock_in":
        # Prevent duplicate clock-in
        if clock.clock_in:
            return JsonResponse({"success": False, "error": "You have already clocked in today."})
        clock.mark_clock_in()

    return JsonResponse({
        "success": True,
        "action": action,
        "clock_in": clock.clock_in.strftime("%H:%M") if clock.clock_in else None,
        "clock_out": clock.clock_out.strftime("%H:%M") if clock.clock_out else None,
    })

def attendance_check(request):
    user = request.user
    event_id = request.GET.get("event_id")

    clock = ClockRecord.objects.filter(user=user, event_id=event_id).first()

    return JsonResponse({
        "clock_in": bool(clock and clock.clock_in),
        "clock_out": bool(clock and clock.clock_out),
    })







