# magnet/views.py

from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from workforce.models import Team
from guests.models import GuestEntry
from accounts.models import CustomUser

@login_required
def magnet_chat_room(request):
    """
    Redirects or renders the chatroom view scoped to the Magnet team.
    Essentially a convenience wrapper around workforce.views.chat_room.
    """
    magnet_team = Team.objects.filter(name__iexact="Magnet").first()
    if not magnet_team:
        # If the team doesn’t exist yet, create it automatically
        magnet_team = Team.objects.create(name="Magnet", description="Guest Management Team")

    # 🧠 You can either redirect to the shared chat view, pre-selecting the Magnet team:
    return redirect(f"/workforce/chat/?team_id={magnet_team.id}")

    # OR if you prefer a distinct URL path (e.g., /magnet/chat/)
    # and want to reuse the same template with extra guest data:
    # from workforce.views import chat_room
    # return chat_room(request)
