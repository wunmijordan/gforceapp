from django.urls import path
from . import views

app_name = 'workforce'

urlpatterns = [
    path("", views.chat_room, name="chat_room"),
    path("chat/load/", views.load_more_messages, name="load_more_messages"),
    path("fetch_link_preview/", views.fetch_link_preview, name="fetch_link_preview"),
    path("upload_file/", views.upload_file, name="upload_file"),
    path("attendance/", views.mark_attendance, name="mark_attendance"),
    path("attendance/summary/", views.attendance_summary, name="attendance_summary"),
    #path("attendance/recent/", views.recent_event, name="recent_event"),
    #path("admin/attendance/", views.attendance_summary, name="attendance_summary"),
    path('manage-events/', views.manage_events, name='manage_events'),
    path("edit-event/<int:pk>/", views.edit_event, name="edit_event"),
    path("delete-event/<int:pk>/", views.delete_event, name="delete_event"),
    path('api/events/', views.api_events, name='api_events'),
    path('log-user-activity/', views.log_user_activity, name='log_user_activity'),
    path("get_active_events/", views.get_active_events, name="get_active_events"),
    #path('api/messages/<int:message_id>/edit/', views.edit_message, name='edit_message'),
    #path('api/messages/<int:message_id>/delete/', views.delete_message, name='delete_message'),
    #path('api/guests/<int:guest_id>/', views.guest_detail_api, name='guest_detail_api'),
    #path('api/fetch-history/', views.fetch_history, name='fetch_history'),
    #path("chat/send/", views.send_chat_message, name="send_chat_message"),
    #path("chat/fetch/", views.fetch_chat_messages, name="fetch_chat_messages"),
]
