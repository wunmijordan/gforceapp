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








