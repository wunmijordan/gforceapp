# accounts/templatetags/team_extras.py
import re
from django import template

register = template.Library()

@register.filter
def roles_for_team(raw, team_id):
    """
    Given raw team_role string (possibly messy like "Member,11:Head of Unit,7:Member")
    and the integer team_id for this membership row, return a list of role names
    that belong to this team. Defensive and idempotent.
    """
    if raw is None:
        return []

    text = str(raw).strip()
    if not text:
        return []

    parts = [p.strip() for p in re.split(r'\s*,\s*', text) if p.strip()]
    matches_for_team = []
    fallback_parts = []

    for part in parts:
        # If it's of the form "<id>:<role>"
        if ':' in part:
            left, right = part.split(':', 1)
            left = left.strip()
            right = right.strip()
            # If left is numeric and matches this team id -> pick right
            if left.isdigit():
                try:
                    if int(left) == int(team_id):
                        matches_for_team.append(right)
                        # keep scanning to collect possible duplicates but prefer exact matches
                        continue
                except Exception:
                    pass
            # If left is not numeric treat as role text ("TeamName:Role") -> include right as fallback
            fallback_parts.append(right)
        else:
            # Pure role fragment like "Member" or "Head of Unit" -> keep as fallback
            # But ignore pure numeric fragments like "3" or "11"
            if not re.fullmatch(r'\d+', part):
                fallback_parts.append(part)

    # Prefer explicit matches for this team id
    if matches_for_team:
        return matches_for_team

    # Otherwise, use fallback parts (could be one or multiple)
    if fallback_parts:
        return fallback_parts

    # As last resort, return cleaned original if it's not just digits
    if not re.fullmatch(r'[\d\s,:]+', text):
        # try removing any leading numeric prefixes and colons
        cleaned = re.sub(r'\b\d+:', '', text).strip(' ,')
        if cleaned:
            return [cleaned]

    return []
