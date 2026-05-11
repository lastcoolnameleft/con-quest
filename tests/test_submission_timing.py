from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.quests.models import QuestAssignment
from apps.quests.models import Quest
from apps.quests.models import SeasonQuest
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.submissions.models import Submission


class SubmissionTimingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.season = Season.objects.create(title="Timing Season", slug="timing-season")
        self.player = SeasonParticipant.objects.create(
            season=self.season,
            handle="player",
            role=SeasonParticipant.Role.PLAYER,
            is_guest=True,
        )
        template = Quest.objects.create(title="Quest", description="Desc")
        self.scheduled_quest = SeasonQuest.objects.create(
            season=self.season,
            quest=template,
            title_override="Scheduled Quest",
            points_max=5,
            quest_mode=SeasonQuest.QuestMode.SCHEDULED,
            status=SeasonQuest.Status.ACTIVE,
            duration_seconds=90,
            rsvp_code="RSVP123",
        )
        self.assignment = QuestAssignment.objects.create(
            season_quest=self.scheduled_quest,
            participant=self.player,
            status=QuestAssignment.Status.PENDING,
        )

        session = self.client.session
        session[f"season_participant_{self.season.id}"] = self.player.id
        session.save()

    def test_rejects_submission_before_scheduled_start(self):
        now = timezone.now()
        self.scheduled_quest.started_at = now + timedelta(seconds=30)
        self.scheduled_quest.ends_at = now + timedelta(seconds=120)
        self.scheduled_quest.save(update_fields=["started_at", "ends_at", "updated_at"])

        with self.assertLogs("apps.submissions.views", level="INFO") as logs:
            with patch("apps.submissions.views.timezone.now", return_value=now):
                response = self.client.post(
                    reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
                    {"text_response": "hello"},
                )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Submission.objects.filter(quest_assignment=self.assignment).exists())
        self.assertTrue(any("Submission timing rejected" in line for line in logs.output))

    @patch("apps.submissions.views.broadcast_season_event")
    def test_allows_submission_exactly_at_end_time(self, _broadcast_mock):
        end_time = timezone.now()
        self.scheduled_quest.started_at = end_time - timedelta(seconds=90)
        self.scheduled_quest.ends_at = end_time
        self.scheduled_quest.save(update_fields=["started_at", "ends_at", "updated_at"])

        with patch("apps.submissions.views.timezone.now", return_value=end_time):
            response = self.client.post(
                reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
                {"text_response": "hello"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Submission.objects.filter(quest_assignment=self.assignment).exists())

    def test_rejects_submission_after_end_without_grace(self):
        end_time = timezone.now()
        now = end_time + timedelta(seconds=1)
        self.scheduled_quest.started_at = end_time - timedelta(seconds=90)
        self.scheduled_quest.ends_at = end_time
        self.scheduled_quest.allow_late_submissions = False
        self.scheduled_quest.save(update_fields=["started_at", "ends_at", "allow_late_submissions", "updated_at"])

        with self.assertLogs("apps.submissions.views", level="INFO") as logs:
            with patch("apps.submissions.views.timezone.now", return_value=now):
                response = self.client.post(
                    reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
                    {"text_response": "hello"},
                )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Submission.objects.filter(quest_assignment=self.assignment).exists())
        self.assertTrue(any("Submission timing rejected" in line for line in logs.output))

    @patch("apps.submissions.views.broadcast_season_event")
    def test_allows_submission_within_late_grace_window(self, _broadcast_mock):
        end_time = timezone.now()
        now = end_time + timedelta(seconds=5)
        self.scheduled_quest.started_at = end_time - timedelta(seconds=90)
        self.scheduled_quest.ends_at = end_time
        self.scheduled_quest.allow_late_submissions = True
        self.scheduled_quest.late_grace_seconds = 10
        self.scheduled_quest.save(
            update_fields=[
                "started_at",
                "ends_at",
                "allow_late_submissions",
                "late_grace_seconds",
                "updated_at",
            ]
        )

        with patch("apps.submissions.views.timezone.now", return_value=now):
            response = self.client.post(
                reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
                {"text_response": "hello"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Submission.objects.filter(quest_assignment=self.assignment).exists())
