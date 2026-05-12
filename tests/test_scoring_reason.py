from django.test import Client
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

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

    def test_scoring_requires_judge_note(self):
        response = self.client.post(
            reverse("submission-score", kwargs={"submission_id": self.submission.id}),
            {"score": 4, "judge_note": ""},
        )
        self.assertEqual(response.status_code, 302)

        self.submission.refresh_from_db()
        self.assertEqual(self.submission.score, 3)

    def test_scoring_queue_shows_judge_note_in_timeline(self):
        response = self.client.post(
            reverse("submission-score", kwargs={"submission_id": self.submission.id}),
            {"score": 4, "judge_note": "Corrected duplicate evidence"},
        )
        self.assertEqual(response.status_code, 302)

        queue_response = self.client.get(reverse("season-scoring-queue", kwargs={"slug": self.season.slug}))
        self.assertEqual(queue_response.status_code, 200)
        self.assertContains(queue_response, "Submission timeline")
        self.assertContains(queue_response, "Corrected duplicate evidence")

    def test_scoring_queue_shows_submission_timeline(self):
        response = self.client.post(
            reverse("submission-score", kwargs={"submission_id": self.submission.id}),
            {"score": 4, "judge_note": "Great detail"},
        )
        self.assertEqual(response.status_code, 302)

        queue_response = self.client.get(reverse("season-scoring-queue", kwargs={"slug": self.season.slug}))
        self.assertEqual(queue_response.status_code, 200)
        self.assertContains(queue_response, "Submission timeline")
        self.assertContains(queue_response, "Joined quest")
        self.assertContains(queue_response, "Submitted response")
        self.assertContains(queue_response, "Judge update")
        self.assertContains(queue_response, "Great detail")


class ScoringStaffAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.season = Season.objects.create(title="Staff Score Season", slug="staff-score-season")
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
            status=SeasonQuest.Status.ACTIVE,
        )
        assignment = QuestAssignment.objects.create(
            season_quest=season_quest,
            participant=self.player,
            status=QuestAssignment.Status.SUBMITTED,
        )
        self.submission = Submission.objects.create(
            quest_assignment=assignment,
            text_response="hello",
        )

        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(username="staff-score", password="pass", is_staff=True)
        self.client.force_login(self.staff_user)

    def test_staff_user_can_view_scoring_queue_without_session_participant(self):
        response = self.client.get(reverse("season-scoring-queue", kwargs={"slug": self.season.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scoring queue")
        self.assertContains(response, self.player.handle)

    def test_staff_user_can_score_without_session_participant(self):
        response = self.client.post(
            reverse("submission-score", kwargs={"submission_id": self.submission.id}),
            {"score": 4, "judge_note": "approved"},
        )

        self.assertEqual(response.status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.score, 4)
        self.assertIsNone(self.submission.scored_by_participant)
