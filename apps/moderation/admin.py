from django.contrib import admin

from apps.moderation.models import ModerationReport


@admin.register(ModerationReport)
class ModerationReportAdmin(admin.ModelAdmin):
    list_display = ("id", "reporter_participant", "target_type", "target_id", "reason", "status", "created_at")
    list_filter = ("reason", "status")
    search_fields = ("reporter_participant__handle", "target_id")
