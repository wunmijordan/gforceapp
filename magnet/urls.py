from django.urls import path
from . import views

urlpatterns = [
    path("chat/", views.magnet_chat_room, name="magnet_chat_room"),
]
