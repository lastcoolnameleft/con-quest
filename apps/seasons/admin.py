from django.contrib import admin

from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "status", "join_code", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "slug", "join_code")


@admin.register(SeasonParticipant)
class SeasonParticipantAdmin(admin.ModelAdmin):
    list_display = ("season", "handle", "role", "is_guest", "account", "joined_at")
    list_filter = ("role", "is_guest")
    search_fields = ("handle", "season__slug", "account__username")