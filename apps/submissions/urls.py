from django.urls import path

from apps.submissions.views import scoring_queue
from apps.submissions.views import score_submission
from apps.submissions.views import submit_assignment
from apps.submissions.views import submit_open_quest

urlpatterns = [
    path("quests/<int:quest_id>/submit/", submit_open_quest, name="season-quest-submit"),
    path("assignments/<int:assignment_id>/submit/", submit_assignment, name="assignment-submit"),
    path("seasons/<slug:slug>/scoring/", scoring_queue, name="season-scoring-queue"),
    path("submissions/<int:submission_id>/score/", score_submission, name="submission-score"),
]
