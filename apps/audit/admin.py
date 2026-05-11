from django.contrib import admin

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "season", "actor_participant", "action_type", "target_type", "target_id", "created_at")
    list_filter = ("action_type", "target_type")
    search_fields = ("season__slug", "actor_participant__handle", "target_id")
