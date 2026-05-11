from django.test import Client
from django.test import TestCase
from django.urls import reverse

from apps.moderation.models import ModerationReport
from apps.quests.models import QuestAssignment
from apps.quests.models import Quest
from apps.quests.models import SeasonQuest
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.submissions.models import Submission


class ModerationFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.season = Season.objects.create(title="Season", slug="season-mod")
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
            title_override="Quest",
            points_max=5,
        )
        assignment = QuestAssignment.objects.create(
            season_quest=season_quest,
            participant=self.player,
            status=QuestAssignment.Status.SUBMITTED,
        )
        self.submission = Submission.objects.create(quest_assignment=assignment, text_response="content")

    def test_report_and_resolve_submission(self):
        player_session = self.client.session
        player_session[f"season_participant_{self.season.id}"] = self.player.id
        player_session.save()

        self.client.post(
            reverse("submission-report", kwargs={"submission_id": self.submission.id}),
            {"reason": ModerationReport.Reason.SPAM, "details": "bad content"},
        )

        report = ModerationReport.objects.get(target_id=str(self.submission.id))
        self.assertEqual(report.status, ModerationReport.Status.OPEN)

        host_session = self.client.session
        host_session[f"season_participant_{self.season.id}"] = self.host.id
        host_session.save()

        self.client.post(
            reverse("moderation-report-resolve", kwargs={"report_id": report.id}),
            {"status": ModerationReport.Status.ACTIONED, "details": "hidden"},
        )

        report.refresh_from_db()
        self.assertEqual(report.status, ModerationReport.Status.ACTIONED)
