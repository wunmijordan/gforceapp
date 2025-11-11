from django.contrib import admin
from .models import Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "member_count", "is_active", "created_at")
    search_fields = ("name", "description")
    list_filter = ("is_active",)
    filter_horizontal = ("members",)  # enables nice dual-list selector for users
    readonly_fields = ("created_at", "updated_at")