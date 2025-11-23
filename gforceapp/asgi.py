"""
ASGI config for gforceapp project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

# gforceapp/asgi.py
import os

# MUST come first
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gforceapp.settings")

from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter

import notifications.routing
import workforce.routing


# ---------- Core Django/Channels ASGI Application ----------
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            notifications.routing.websocket_urlpatterns +
            workforce.routing.websocket_urlpatterns
        )
    ),
})


# ---------- Safe APScheduler Startup (RUN_MAIN Only) ----------
def is_main_process():
    """
    Django autoreloader runs two processes:
      - Parent = watches files
      - Child  = runs the app (RUN_MAIN=true)
    Scheduler must ONLY run in the child.
    """
    return os.environ.get("RUN_MAIN") == "true"


if is_main_process():
    try:
        from workforce.apps import start_scheduler
        start_scheduler()
        print("✅ APScheduler started from ASGI (main process).")
    except Exception as e:
        print(f"❌ Failed to start APScheduler: {e}")








