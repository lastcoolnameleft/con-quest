from django.contrib import admin

from apps.submissions.models import Submission
from apps.submissions.models import SubmissionMedia


class SubmissionMediaInline(admin.TabularInline):
    model = SubmissionMedia
    extra = 0


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "quest_assignment", "score", "submitted_at", "scored_at")
    list_filter = ("score",)
    search_fields = ("quest_assignment__participant__handle", "quest_assignment__season_quest__season__slug")
    inlines = [SubmissionMediaInline]


@admin.register(SubmissionMedia)
class SubmissionMediaAdmin(admin.ModelAdmin):
    list_display = ("id", "submission", "media_type", "file_size_bytes", "duration_seconds", "uploaded_at")
    list_filter = ("media_type",)
    search_fields = ("submission__quest_assignment__participant__handle",)
