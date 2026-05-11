from django.urls import path

from apps.quests.views import claim_open_quest
from apps.quests.views import enroll_scheduled_quest
from apps.quests.views import quest_create
from apps.quests.views import quest_delete
from apps.quests.views import quest_edit
from apps.quests.views import season_quest_delete
from apps.quests.views import season_quest_edit
from apps.quests.views import season_quest_create
from apps.quests.views import start_scheduled_quest
from apps.quests.views import transition_season_quest_status

urlpatterns = [
    path("quest-library/new/", quest_create, name="quest-create"),
    path("quest-library/<int:quest_id>/edit/", quest_edit, name="quest-edit"),
    path("quest-library/<int:quest_id>/delete/", quest_delete, name="quest-delete"),
    path("seasons/<slug:slug>/quests/new/", season_quest_create, name="season-quest-create"),
    path("quests/<int:quest_id>/edit/", season_quest_edit, name="season-quest-edit"),
    path("quests/<int:quest_id>/delete/", season_quest_delete, name="season-quest-delete"),
    path("quests/<int:quest_id>/start/", start_scheduled_quest, name="season-quest-start"),
    path("quests/<int:quest_id>/status/", transition_season_quest_status, name="season-quest-status"),
    path("quests/<int:quest_id>/claim/", claim_open_quest, name="season-quest-claim"),
    path("quests/<int:quest_id>/enroll/", enroll_scheduled_quest, name="season-quest-enroll"),
]
