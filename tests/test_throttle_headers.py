from django.test import Client
from django.test import TestCase
from django.urls import reverse
from django.core.cache import cache
from unittest.mock import patch

from apps.moderation.models import ModerationReport
from apps.quests.models import QuestAssignment
from apps.quests.models import Quest
from apps.quests.models import SeasonQuest
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.submissions.models import Submission


class ThrottleHeaderTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.season = Season.objects.create(title="Throttle Season", slug="throttle-season")
        self.host = SeasonParticipant.objects.create(
            season=self.season,
            handle="host",
            role=SeasonParticipant.Role.HOST,
            is_guest=True,
        )
        self.player = SeasonParticipant.objects.create(
            season=self.season,
            handle="player",
            role=SeasonParticipant.Role.PLAYER,
            is_guest=True,
        )

        template = Quest.objects.create(title="Quest", description="Desc")
        self.open_quest = SeasonQuest.objects.create(
            season=self.season,
            quest=template,
            title_override="Open Quest",
            points_max=5,
            quest_mode=SeasonQuest.QuestMode.OPEN,
        )
        self.scheduled_quest = SeasonQuest.objects.create(
            season=self.season,
            quest=template,
            title_override="Scheduled Quest",
            points_max=5,
            quest_mode=SeasonQuest.QuestMode.SCHEDULED,
            rsvp_code="RSVP123",
        )

        self.assignment = QuestAssignment.objects.create(
            season_quest=self.open_quest,
            participant=self.player,
            status=QuestAssignment.Status.SUBMITTED,
        )
        self.submission = Submission.objects.create(
            quest_assignment=self.assignment,
            text_response="hello",
        )

        self.report = ModerationReport.objects.create(
            reporter_participant=self.player,
            target_type="Submission",
            target_id=str(self.submission.id),
            reason=ModerationReport.Reason.OTHER,
            details="needs review",
        )

    def _set_participant_session(self, participant: SeasonParticipant) -> None:
        session = self.client.session
        session[f"season_participant_{self.season.id}"] = participant.id
        session.save()

    def _assert_throttle_headers(self, response):
        self.assertIn("X-RateLimit-Limit", response)
        self.assertIn("X-RateLimit-Remaining", response)
        self.assertIn("X-RateLimit-Window", response)

    @patch("apps.quests.views.broadcast_season_event")
    def test_start_scheduled_quest_returns_headers_and_retry_after_when_limited(self, _broadcast_mock):
        self._set_participant_session(self.host)
        url = reverse("season-quest-start", kwargs={"quest_id": self.scheduled_quest.id})

        first = self.client.post(url)
        self.assertEqual(first.status_code, 302)
        self._assert_throttle_headers(first)

        limited = None
        for _ in range(20):
            limited = self.client.post(url)

        self.assertIsNotNone(limited)
        self.assertEqual(limited.status_code, 302)
        self._assert_throttle_headers(limited)
        self.assertIn("Retry-After", limited)

    def test_claim_open_quest_returns_headers_and_retry_after_when_limited(self):
        self._set_participant_session(self.player)
        url = reverse("season-quest-claim", kwargs={"quest_id": self.open_quest.id})

        first = self.client.post(url)
        self.assertEqual(first.status_code, 302)
        self._assert_throttle_headers(first)

        limited = None
        for _ in range(20):
            limited = self.client.post(url)

        self.assertIsNotNone(limited)
        self.assertEqual(limited.status_code, 302)
        self._assert_throttle_headers(limited)
        self.assertIn("Retry-After", limited)

    def test_enroll_scheduled_quest_returns_headers_and_retry_after_when_limited(self):
        self._set_participant_session(self.player)
        url = reverse("season-quest-enroll", kwargs={"quest_id": self.scheduled_quest.id})

        first = self.client.post(url, {"rsvp_code": "RSVP123"})
        self.assertEqual(first.status_code, 302)
        self._assert_throttle_headers(first)

        limited = None
        for _ in range(20):
            limited = self.client.post(url, {"rsvp_code": "RSVP123"})

        self.assertIsNotNone(limited)
        self.assertEqual(limited.status_code, 302)
        self._assert_throttle_headers(limited)
        self.assertIn("Retry-After", limited)

    @patch("apps.submissions.views.broadcast_season_event")
    def test_score_submission_returns_headers_and_retry_after_when_limited(self, _broadcast_mock):
        self._set_participant_session(self.host)
        url = reverse("submission-score", kwargs={"submission_id": self.submission.id})

        first = self.client.post(url, {"score": 4, "judge_note": "good", "reason": ""})
        self.assertEqual(first.status_code, 302)
        self._assert_throttle_headers(first)

        limited = None
        for _ in range(30):
            limited = self.client.post(url, {"score": 4, "judge_note": "good", "reason": ""})

        self.assertIsNotNone(limited)
        self.assertEqual(limited.status_code, 302)
        self._assert_throttle_headers(limited)
        self.assertIn("Retry-After", limited)

    def test_resolve_report_returns_headers_and_retry_after_when_limited(self):
        self._set_participant_session(self.host)
        url = reverse("moderation-report-resolve", kwargs={"report_id": self.report.id})

        first = self.client.post(
            url,
            {"status": ModerationReport.Status.ACTIONED, "details": "resolved"},
        )
        self.assertEqual(first.status_code, 302)
        self._assert_throttle_headers(first)

        limited = None
        for _ in range(20):
            limited = self.client.post(
                url,
                {"status": ModerationReport.Status.ACTIONED, "details": "resolved"},
            )

        self.assertIsNotNone(limited)
        self.assertEqual(limited.status_code, 302)
        self._assert_throttle_headers(limited)
        self.assertIn("Retry-After", limited)

    def test_enroll_uses_season_code_when_quest_override_blank(self):
        cache.clear()
        self._set_participant_session(self.player)
        self.scheduled_quest.rsvp_code = ""
        self.scheduled_quest.save(update_fields=["rsvp_code"])

        url = reverse("season-quest-enroll", kwargs={"quest_id": self.scheduled_quest.id})
        response = self.client.post(url, {"rsvp_code": self.season.join_code})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            QuestAssignment.objects.filter(season_quest=self.scheduled_quest, participant=self.player).exists()
        )

    def test_enroll_uses_quest_override_when_present(self):
        cache.clear()
        self._set_participant_session(self.player)
        self.season.join_code = "SEASON111"
        self.season.save(update_fields=["join_code"])
        self.scheduled_quest.rsvp_code = "QUEST999"
        self.scheduled_quest.save(update_fields=["rsvp_code"])

        url = reverse("season-quest-enroll", kwargs={"quest_id": self.scheduled_quest.id})
        wrong = self.client.post(url, {"rsvp_code": self.season.join_code})
        self.assertEqual(wrong.status_code, 302)
        self.assertFalse(
            QuestAssignment.objects.filter(season_quest=self.scheduled_quest, participant=self.player).exists()
        )

        correct = self.client.post(url, {"rsvp_code": "QUEST999"})
        self.assertEqual(correct.status_code, 302)
        self.assertTrue(
            QuestAssignment.objects.filter(season_quest=self.scheduled_quest, participant=self.player).exists()
        )
