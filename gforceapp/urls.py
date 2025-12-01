"""
URL configuration for gforceapp project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import post_login_redirect
from django.views.generic import TemplateView
from gforceapp import views
from django.views.generic import RedirectView
from django.views.static import serve
from django.http import JsonResponse
def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path('admin/', admin.site.urls),

    # Core app routes
    path('', include('workforce.urls', namespace='workforce')),
    path('guests/', include('guests.urls')),  # Only include once
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/', include('accounts.urls')),
    path("notifications/", include("notifications.urls", namespace="notifications")),
    path('messaging/', include('messaging.urls')),
    path('magnet/', include('magnet.urls')),
    
    # Post-login redirection
    path('post-login/', post_login_redirect, name='post_login_redirect'),
    path("sw.js", lambda request: serve(request, "sw.js", document_root=settings.BASE_DIR)),

    path("health/", health),
]

# Debug + media
if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += [
        path('__debug__/', include('debug_toolbar.urls')),
    ]


