from django.contrib import admin

from apps.quests.models import QuestAssignment
from apps.quests.models import Quest
from apps.quests.models import SeasonQuest


@admin.register(Quest)
class QuestAdmin(admin.ModelAdmin):
    list_display = ("title", "default_duration_seconds", "default_points_max", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title",)


@admin.register(SeasonQuest)
class SeasonQuestAdmin(admin.ModelAdmin):
    list_display = ("resolved_title", "season", "quest_mode", "status", "assignment_policy")
    list_filter = ("quest_mode", "status", "assignment_policy")
    search_fields = ("title_override", "season__slug", "quest__title")


@admin.register(QuestAssignment)
class QuestAssignmentAdmin(admin.ModelAdmin):
    list_display = ("season_quest", "participant", "status", "assignment_source", "assigned_at")
    list_filter = ("status", "assignment_source")
    search_fields = ("participant__handle", "season_quest__season__slug")
