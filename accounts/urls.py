from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Admin Dashboard
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),

    # User Management
    path('users/', views.user_list, name='user_list'),
    path('users/manage/', views.manage_user, name='create_user'),
    path('users/<int:user_id>/manage/', views.manage_user, name='edit_user'),
    path("manage-groups/", views.manage_groups, name="manage_groups"),
    path("groups/delete/<int:group_id>/", views.delete_group, name="delete_group"),
    #path("ajax/get-team-roles/", views.get_team_roles, name="get_team_roles"),
    path("ajax/load-teams/", views.load_teams, name="ajax_load_teams"),
    path("ajax/load-roles/", views.load_roles, name="ajax_load_roles"),
    path("attendance/summary/", views.attendance_summary, name="attendance_summary"),
    path("attendance/clock/", views.clock_action, name="clock_action"),
]
