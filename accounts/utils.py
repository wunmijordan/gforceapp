# accounts/utils.py
from django.contrib.auth.models import Group
import requests, urllib
from django.conf import settings
from accounts.models import TeamMembership
from workforce.models import Team
import re


def normalize(s):
    """Normalize strings for flexible matching."""
    return re.sub(r"[\s\-\_]+", "", s or "").lower()


def user_in_groups(user, group_names):
    """
    Check if a user is superuser OR belongs to any of the provided groups.
    group_names: comma-separated string or list of group names
    """
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if isinstance(group_names, str):
        groups = [name.strip() for name in group_names.split(",")]
    else:
        groups = group_names

    return user.groups.filter(name__in=groups).exists()


def user_in_team(user, team_names):
    """
    Check if a user belongs to any of the provided teams (via TeamMembership).
    Accepts a Team instance, a single name, a comma-separated string, or a list.
    """
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    if is_project_admin(user):
        return True

    # Normalize input to list of team names
    if team_names is None:
        return False
    elif isinstance(team_names, Team):
        teams = [team_names.name]
    elif isinstance(team_names, str):
        teams = [name.strip() for name in team_names.split(",")]
    else:
        teams = team_names

    return user.team_memberships.filter(team__name__in=teams).exists()



# ===============================
# 🔰 NEW UNIFIED ROLE UTILITIES
# ===============================

def get_effective_role(user):
    """
    Returns the user's highest effective project-level role
    based on Group membership and team-level roles.
    """
    if not user.is_authenticated:
        return None

    if user.is_superuser:
        return "Superuser"

    group_names = list(user.groups.values_list("name", flat=True))

    if "Pastor" in group_names:
        return "Pastor"
    if "Admin" in group_names:
        return "Admin"
    if "Minister" in group_names:
        return "Minister"
    if "GForce Member" in group_names:
        return "GForce Member"

    return "Member"


def get_team_access_level(user, team):
    """
    Determines a user's access level within a given team.
    Returns one of:
    - "Team Admin"  (Minister-in-Charge / Team Admin)
    - "Team Lead"   (Head of Unit / Asst. / Subleader)
    - "Team Member" (Regular member)
    - None          (Not part of this team)
    """
    membership = TeamMembership.objects.filter(user=user, team=team).first()
    if not membership:
        return None

    role = (membership.team_role or "").strip().lower()

    if role in ["minister-in-charge", "team admin"]:
        return "Team Admin"
    if any(keyword in role for keyword in ["head", "asst", "subleader"]):
        return "Team Lead"
    if role == "member":
        return "Team Member"

    return "Team Member"


def is_privileged(user, team=None):
    """
    Checks if a user has elevated privileges globally or within a specific team.
    """
    role = get_effective_role(user)
    if role in ["Superuser", "Pastor", "Admin"]:
        return True

    if team:
        team_access = get_team_access_level(user, team)
        if team_access == "Team Admin":
            return True

    return False



def is_project_admin(user, role=None):
    """
    True for top-level project admins:
    - Superuser
    - Global 'Pastor' or 'Admin' (via group or title)
    Optionally restricts to specific role keyword(s), comma-separated.
    """
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    # Group-based or title-based
    group_match = user.groups.filter(name__in=["Pastor", "Admin"]).exists()
    title = (user.title or "").lower()

    if group_match or title in ["pastor", "admin"]:
        if role:
            # Split comma-separated roles and check if any match
            role_list = [r.strip() for r in role.split(",")]
            for r in role_list:
                if re.search(r.lower(), title, re.IGNORECASE):
                    return True
            return False
        return True

    return False


def is_team_admin(user, team=None, role=None):
    """
    Returns True if user is a team-level admin on any team (or a specific one if provided).
    Includes roles like:
      - Minister-in-Charge
      - Team Admin
      - Head of Unit
      - Asst. Head of Unit

    Optional:
      - team: a Team instance or name (str)
      - role: comma-separated string of role names
    """
    if not user.is_authenticated or user.is_superuser:
        return False

    memberships = TeamMembership.objects.filter(user=user)

    # Filter by team (object or name)
    if team:
        if isinstance(team, str):
            memberships = memberships.filter(team__name__iexact=team)
        else:
            memberships = memberships.filter(team=team)

    # Default admin role pattern
    if not role:
        pattern = (
            r"(minister[- ]?in[- ]?charge|team[ -]?admin|head[- ]?of[- ]?unit|asst\.?[- ]?head[- ]?of[- ]?unit)"
        )
        return memberships.filter(team_role__iregex=pattern).exists()

    # Normalize roles and check manually
    role_list = [normalize(r) for r in role.split(",")]
    for m in memberships:
        role_normalized = normalize(m.team_role)
        if any(rn in role_normalized for rn in role_list):
            return True

    return False



def is_magnet_admin(user, role=None):
    """
    True if user has admin privileges over the Magnet team:
      - Superuser
      - Project-level Admin/Pastor
      - Minister-in-Charge or Team Admin (Magnet)
    Optional: restrict to a specific Magnet role keyword(s), comma-separated.
    """
    if not user.is_authenticated:
        return False

    # Superusers and project-level admins always qualify
    if is_project_admin(user):
        return True

    magnet_team = Team.objects.filter(name__iexact="magnet").first()
    if not magnet_team:
        return False

    # Check Magnet-specific roles
    return is_team_admin(user, team=magnet_team, role=role)



def is_project_wide_admin(user, role=None):
    """
    Combines project-level and team-level admins across all teams.
    Used to allow cross-team dashboard access.
    Optional: restrict to specific role keyword.
    """
    if not user.is_authenticated:
        return False

    return is_project_admin(user, role) or is_team_admin(user, role=role)


def is_project_level_role(user, role=None):
    """
    Returns True only for Pastor or Admin project-level roles (via groups or title).
    Optionally restricts to specific keyword(s), comma-separated.
    """
    if user.is_superuser:
        return False

    from accounts.utils import get_combined_role, user_in_groups  # avoid circular import

    role_str = (get_combined_role(user) or "").lower()
    title = (user.title or "").lower()

    if user_in_groups(user, "Pastor,Admin") or title in ["pastor", "admin"]:
        if role:
            role_list = [r.strip() for r in role.split(",")]
            for r in role_list:
                if re.search(r.lower(), f"{title} {role_str}", re.IGNORECASE):
                    return True
            return False

        # Exclude departmental subroles like "Youth Pastor"
        if any(x in role_str for x in ["youth", "welfare", "media", "protocol", "music", "choir"]):
            return False
        return True

    return False






# ===============================
# 🧲 MAGNET GUEST ACCESS LOGIC
# ===============================
from django.db import models
from guests.models import GuestEntry  # adjust import path if needed
from accounts.models import TeamMembership
from workforce.models import Team


def get_guest_queryset(user, team=None):
    """
    Returns the appropriate Guest queryset for the given user,
    optionally filtered by team, based on project + team roles.
    """

    if not user.is_authenticated:
        return GuestEntry.objects.none()

    # ----------------------------------------------------------
    # 🏆 1. Superuser → full unrestricted access
    # ----------------------------------------------------------
    if user.is_superuser:
        qs = GuestEntry.objects.all()
        if team:
            qs = qs.filter(assigned_to__team_memberships__team=team)
        return qs.distinct()

    # ----------------------------------------------------------
    # 🥇 2. Project-level Admin or Pastor → wide, but not superuser-level
    # ----------------------------------------------------------
    if user.groups.filter(name__in=["Pastor", "Admin"]).exists():
        qs = GuestEntry.objects.all()

        # If filtering by team, narrow scope
        if team:
            qs = qs.filter(assigned_to__team_memberships__team=team)

        # Optionally (if you store guest.created_by or assigned_to), 
        # exclude guests linked to superusers
        qs = qs.exclude(assigned_to__is_superuser=True)

        return qs.distinct()

    # ----------------------------------------------------------
    # 🧩 3. Ministers — differentiate MIC vs. ordinary ministers
    # ----------------------------------------------------------
    if user.groups.filter(name="Minister").exists():
        memberships = TeamMembership.objects.filter(user=user).select_related("team")

        # All teams this minister belongs to
        team_ids = list(memberships.values_list("team_id", flat=True))

        # MIC roles (Minister-in-Charge)
        mic_team_ids = list(
            memberships.filter(
                team_role__iregex=r"minister[- ]?in[- ]?charge"
            ).values_list("team_id", flat=True)
        )

        # Base queryset: guests assigned to any of the minister’s teams
        qs = GuestEntry.objects.filter(
            assigned_to__team_memberships__team_id__in=team_ids
        )

        # MIC privilege (extra): see all guests in their MIC teams
        if mic_team_ids:
            mic_qs = GuestEntry.objects.filter(
                assigned_to__team_memberships__team_id__in=mic_team_ids
            )
            qs = qs | mic_qs

        if team:
            qs = qs.filter(assigned_to__team_memberships__team=team)

        return qs.distinct()

    # ----------------------------------------------------------
    # 🔹 4. GForce Members — handle Magnet admins vs. regulars
    # ----------------------------------------------------------
    if user.groups.filter(name="GForce Member").exists():
        memberships = TeamMembership.objects.filter(user=user).select_related("team")

        # Identify team-level Magnet admins (MIC or Team Admin)
        magnet_team_ids = list(
            memberships.filter(
                team__name__iexact="magnet",
                team_role__iregex=r"(minister[- ]?in[- ]?charge|team[ -]?admin)"
            ).values_list("team_id", flat=True)
        )

        if magnet_team_ids:
            # Full access to all guests in the Magnet team(s)
            qs = GuestEntry.objects.filter(
                assigned_to__team_memberships__team__name__iexact="magnet"
            )
        else:
            # Regular GForce members → only their own assigned guests
            qs = GuestEntry.objects.filter(assigned_to=user)

        if team:
            qs = qs.filter(assigned_to__team_memberships__team=team)

        return qs.distinct()

    # ----------------------------------------------------------
    # 🔹 5. Regular members → only their assigned guests
    # ----------------------------------------------------------
    if hasattr(user, "assigned_guests"):
        qs = user.assigned_guests.all()
        if team:
            qs = qs.filter(assigned_to__team_memberships__team=team)
        return qs.distinct()

    # ----------------------------------------------------------
    # 🔹 6. Default fallback
    # ----------------------------------------------------------
    return GuestEntry.objects.none()





# ===============================
# 🧩 TEAM ACCESS LOGIC
# ===============================

def get_team_queryset(user):
    """
    Returns a queryset of Teams the user can access,
    based on project-level and team-level roles.
    """

    if not user.is_authenticated:
        return Team.objects.none()

    # 🏆 Superuser, Pastor, Admin => all teams
    if user.is_superuser or user.groups.filter(name__in=["Pastor", "Admin"]).exists():
        return Team.objects.all()

    # 🔹 Ministers => teams they belong to (or lead)
    if user.groups.filter(name="Minister").exists():
        team_ids = TeamMembership.objects.filter(user=user).values_list("team_id", flat=True)
        return Team.objects.filter(id__in=team_ids).distinct()

    # 🔹 GForce Members => only Magnet teams they belong to
    if user.groups.filter(name="GForce Member").exists():
        memberships = TeamMembership.objects.filter(user=user).select_related("team")

        # Include Magnet teams where they’re team admin or regular member
        admin_team_ids = memberships.filter(
            team_role__iregex=r"(minister[- ]?in[- ]?charge|team[ -]?admin)",
            team__is_magnet=True
        ).values_list("team_id", flat=True)

        magnet_team_ids = memberships.filter(team__is_magnet=True).values_list("team_id", flat=True)

        all_team_ids = set(admin_team_ids) | set(magnet_team_ids)
        return Team.objects.filter(id__in=all_team_ids).distinct()

    # 🔹 Regular Members => no team access (unless explicitly assigned)
    return Team.objects.none()



def get_combined_role(user, team=None):
    """
    Determines the user's effective role.
    - Superuser / Pastor / Admin → project-level role
    - Minister / GForce Member / others → team-level roles
    - Adds explicit team name context, e.g. 'Team Admin (Magnet)'
    """

    if not user.is_authenticated:
        return "Guest"

    # 🔹 Global roles first (project-level)
    if user.is_superuser:
        return "Superuser"
    if user.groups.filter(name="Pastor").exists():
        return "Pastor"
    if user.groups.filter(name="Admin").exists():
        return "Admin"

    # 🔹 Team-level logic
    memberships = TeamMembership.objects.filter(user=user).select_related("team")

    if team:
        memberships = memberships.filter(team=team)

    team_roles = []
    for m in memberships:
        role = m.team_role or "Member"
        team_name = m.team.name if m.team else None
        if team_name:
            role = f"{role} ({team_name})"
        team_roles.append(role)

    # 🔹 Group-based fallback labels
    if not team_roles:
        if user.groups.filter(name="Minister").exists():
            return "Minister"
        if user.groups.filter(name="GForce Member").exists():
            return "GForce Member"
        return "Member"

    return ", ".join(sorted(set(team_roles)))

