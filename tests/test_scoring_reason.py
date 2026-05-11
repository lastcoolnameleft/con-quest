from django.test import Client
from django.test import TestCase
from django.urls import reverse

from apps.quests.models import QuestAssignment
from apps.quests.models import Quest
from apps.quests.models import SeasonQuest
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.submissions.models import Submission


class ScoringReasonTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.season = Season.objects.create(title="Season", slug="season")
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
        season_quest = SeasonQuest.objects.create(
            season=self.season,
            quest=template,
            title_override="Quest 1",
            points_max=5,
        )
        assignment = QuestAssignment.objects.create(
            season_quest=season_quest,
            participant=self.player,
            status=QuestAssignment.Status.SUBMITTED,
        )
        self.submission = Submission.objects.create(
            quest_assignment=assignment,
            text_response="hello",
            score=3,
        )

        session = self.client.session
        session[f"season_participant_{self.season.id}"] = self.host.id
        session.save()

    def test_editing_existing_score_requires_reason(self):
        response = self.client.post(
            reverse("submission-score", kwargs={"submission_id": self.submission.id}),
            {"score": 4, "judge_note": "updated", "reason": ""},
        )
        self.assertEqual(response.status_code, 302)

        self.submission.refresh_from_db()
        self.assertEqual(self.submission.score, 3)
