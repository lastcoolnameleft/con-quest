from django.urls import path

from apps.submissions.views import scoring_queue
from apps.submissions.views import score_submission
from apps.submissions.views import submit_assignment

urlpatterns = [
    path("assignments/<int:assignment_id>/submit/", submit_assignment, name="assignment-submit"),
    path("seasons/<slug:slug>/scoring/", scoring_queue, name="season-scoring-queue"),
    path("submissions/<int:submission_id>/score/", score_submission, name="submission-score"),
]
