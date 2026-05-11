from django.urls import path

from apps.moderation.views import moderation_queue
from apps.moderation.views import report_submission
from apps.moderation.views import resolve_report

urlpatterns = [
    path("submissions/<int:submission_id>/report/", report_submission, name="submission-report"),
    path("seasons/<slug:slug>/moderation/", moderation_queue, name="season-moderation-queue"),
    path("reports/<int:report_id>/resolve/", resolve_report, name="moderation-report-resolve"),
]
