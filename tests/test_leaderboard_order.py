from django.test import Client
from django.test import TestCase
from django.urls import reverse

from apps.quests.models import QuestAssignment
from apps.quests.models import Quest
from apps.quests.models import SeasonQuest
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.submissions.models import Submission


class LeaderboardOrderTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.season = Season.objects.create(title="Leaderboard Season", slug="leaderboard-season")
        self.template = Quest.objects.create(title="Quest", description="Desc")
        self.season_quest = SeasonQuest.objects.create(
            season=self.season,
            quest=self.template,
            title_override="Quest",
            points_max=5,
        )

    def _add_scored_submission(self, *, handle: str, score: int | None):
        participant = SeasonParticipant.objects.create(
            season=self.season,
            handle=handle,
            role=SeasonParticipant.Role.PLAYER,
            is_guest=True,
        )
        assignment = QuestAssignment.objects.create(
            season_quest=self.season_quest,
            participant=participant,
            status=QuestAssignment.Status.SCORED if score is not None else QuestAssignment.Status.SUBMITTED,
        )
        Submission.objects.create(
            quest_assignment=assignment,
            text_response="content",
            score=score,
        )

    def test_leaderboard_orders_by_score_then_handle(self):
        self._add_scored_submission(handle="bob", score=5)
        self._add_scored_submission(handle="alice", score=5)
        self._add_scored_submission(handle="charlie", score=2)

        response = self.client.get(reverse("season-leaderboard", kwargs={"slug": self.season.slug}))
        self.assertEqual(response.status_code, 200)

        rows = response.context["leaderboard"]
        handles = [row["handle"] for row in rows]
        self.assertEqual(handles, ["alice", "bob", "charlie"])

    def test_leaderboard_defaults_missing_scores_to_zero(self):
        self._add_scored_submission(handle="alpha", score=None)

        response = self.client.get(reverse("season-leaderboard", kwargs={"slug": self.season.slug}))
        self.assertEqual(response.status_code, 200)

        rows = response.context["leaderboard"]
        self.assertEqual(rows[0]["total_score"], 0)
        self.assertEqual(rows[0]["rank"], 1)
