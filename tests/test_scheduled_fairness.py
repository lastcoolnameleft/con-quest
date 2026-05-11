from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.quests.models import Quest
from apps.quests.models import SeasonQuest
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant


class ScheduledFairnessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.season = Season.objects.create(title="Fairness Season", slug="fairness-season")
        self.host = SeasonParticipant.objects.create(
            season=self.season,
            handle="host",
            role=SeasonParticipant.Role.HOST,
            is_guest=True,
        )
        template = Quest.objects.create(title="Quest", description="Desc")
        self.scheduled_quest = SeasonQuest.objects.create(
            season=self.season,
            quest=template,
            title_override="Scheduled Quest",
            points_max=5,
            quest_mode=SeasonQuest.QuestMode.SCHEDULED,
            status=SeasonQuest.Status.PENDING,
            duration_seconds=90,
            rsvp_code="RSVP123",
        )

        session = self.client.session
        session[f"season_participant_{self.season.id}"] = self.host.id
        session.save()

    @patch("apps.quests.views.broadcast_season_event")
    def test_start_sets_canonical_window_and_broadcasts(self, broadcast_mock):
        started_before = timezone.now()
        response = self.client.post(reverse("season-quest-start", kwargs={"quest_id": self.scheduled_quest.id}))

        self.assertEqual(response.status_code, 302)
        self.assertIn("X-RateLimit-Limit", response)

        self.scheduled_quest.refresh_from_db()
        self.assertEqual(self.scheduled_quest.status, SeasonQuest.Status.ACTIVE)
        self.assertIsNotNone(self.scheduled_quest.started_at)
        self.assertIsNotNone(self.scheduled_quest.ends_at)

        # Fairness buffer should place canonical start slightly ahead of request time.
        self.assertGreaterEqual(self.scheduled_quest.started_at, started_before + timedelta(seconds=1))
        self.assertEqual(
            int((self.scheduled_quest.ends_at - self.scheduled_quest.started_at).total_seconds()),
            self.scheduled_quest.duration_seconds,
        )

        broadcast_mock.assert_called_once()
        payload = broadcast_mock.call_args.kwargs["payload"]
        self.assertEqual(payload["event"], "quest_started")
        self.assertEqual(payload["season_quest_id"], self.scheduled_quest.id)

        state_response = self.client.get(reverse("season-state", kwargs={"slug": self.season.slug}))
        self.assertEqual(state_response.status_code, 200)
        state_payload = state_response.json()
        quest_row = next(row for row in state_payload["quests"] if row["id"] == self.scheduled_quest.id)
        self.assertEqual(quest_row["status"], SeasonQuest.Status.ACTIVE)
        self.assertEqual(quest_row["started_at"], self.scheduled_quest.started_at.isoformat())
        self.assertEqual(quest_row["ends_at"], self.scheduled_quest.ends_at.isoformat())

    @patch("apps.quests.views.broadcast_season_event")
    def test_start_does_not_reset_timing_when_already_live(self, broadcast_mock):
        first_started_at = timezone.now() + timedelta(seconds=2)
        first_ends_at = first_started_at + timedelta(seconds=self.scheduled_quest.duration_seconds)
        self.scheduled_quest.status = SeasonQuest.Status.ACTIVE
        self.scheduled_quest.started_at = first_started_at
        self.scheduled_quest.ends_at = first_ends_at
        self.scheduled_quest.save(update_fields=["status", "started_at", "ends_at", "updated_at"])

        response = self.client.post(reverse("season-quest-start", kwargs={"quest_id": self.scheduled_quest.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn("X-RateLimit-Limit", response)

        self.scheduled_quest.refresh_from_db()
        self.assertEqual(self.scheduled_quest.started_at, first_started_at)
        self.assertEqual(self.scheduled_quest.ends_at, first_ends_at)
        broadcast_mock.assert_not_called()
