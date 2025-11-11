from django import template
from accounts.utils import (
    user_in_groups,
    user_in_team,
    get_team_queryset,
    get_guest_queryset,
    is_project_admin as is_project_admin_util,
    is_team_admin as is_team_admin_util,
    is_magnet_admin as is_magnet_admin_util,
    is_project_wide_admin as is_project_wide_admin_util,
    is_project_level_role as is_project_level_role_util,
)

register = template.Library()

# =========================
# 🔹 Group and Team Filters
# =========================

@register.filter
def has_group(user, group_names):
    """Check if user belongs to one or more groups."""
    return user_in_groups(user, group_names)


@register.filter
def in_team(user, team_names):
    """Check if user belongs to one or more teams."""
    return user_in_team(user, team_names)


# =========================
# 🔹 Access Query Tags
# =========================

@register.simple_tag
def get_accessible_teams(user):
    """
    Returns queryset of teams accessible to the user.
    Usage:
        {% get_accessible_teams request.user as teams %}
        {% for team in teams %}
            {{ team.name }}
        {% endfor %}
    """
    return get_team_queryset(user)


@register.simple_tag
def get_accessible_guests(user, team=None):
    """
    Returns queryset of guests accessible to the user (optionally by team).
    Usage:
        {% get_accessible_guests request.user as guests %}
        {% get_accessible_guests request.user team as guests %}
    """
    return get_guest_queryset(user, team)



@register.filter
def is_project_wide_admin(user, role=None):
    """True if user is any kind of admin with project-wide access (optionally narrowed by role)."""
    return is_project_wide_admin_util(user, role=role)


@register.filter
def is_team_admin(user, arg=None):
    """
    Checks if user is a team-specific admin.
    Usage:
      {{ user|is_team_admin }}                       # any team admin
      {{ user|is_team_admin:"Minister-in-Charge" }}  # any team, specific role(s)
      {{ user|is_team_admin:team }}                  # specific team object
      {{ user|is_team_admin:"Magnet:Team Admin" }}   # team name + role(s)
    """
    team = None
    role = None

    if hasattr(arg, "id"):  # Team instance
        team = arg
    elif isinstance(arg, str):
        if ":" in arg:
            team_name, role_str = arg.split(":", 1)
            team = team_name.strip()
            role = role_str.strip()
        else:
            role = arg.strip()

    return is_team_admin_util(user, team=team, role=role)


@register.filter
def is_magnet_admin(user, role=None):
    """True if user belongs to the Magnet Admin team (optionally narrowed by role)."""
    return is_magnet_admin_util(user, role=role)


@register.filter
def is_project_admin(user, role=None):
    """True if user is a general project admin (non-superuser)."""
    return is_project_admin_util(user, role=role)


@register.filter
def is_project_level_role(user, role=None):
    """True if user holds any project-level role (optionally narrowed by keyword)."""
    return is_project_level_role_util(user, role=role)
