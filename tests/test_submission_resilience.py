from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.client import MULTIPART_CONTENT
from django.test import Client
from django.test import TestCase
from django.urls import reverse

from apps.quests.models import QuestAssignment
from apps.quests.models import Quest
from apps.quests.models import SeasonQuest
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.submissions.models import Submission


class SubmissionResilienceTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.season = Season.objects.create(title="Submit Season", slug="submit-season")
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
        self.assignment = QuestAssignment.objects.create(
            season_quest=season_quest,
            participant=self.player,
            status=QuestAssignment.Status.PENDING,
        )

        session = self.client.session
        session[f"season_participant_{self.season.id}"] = self.player.id
        session.save()

    @patch("apps.submissions.views.upload_submission_media", side_effect=RuntimeError("storage transient failure"))
    def test_submit_assignment_rolls_back_on_unexpected_upload_error(self, _mock_upload):
        upload = SimpleUploadedFile("photo.jpg", b"image-bytes", content_type="image/jpeg")

        response = self.client.post(
            reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
            {"text_response": "hello", "media_files": upload},
            content_type=MULTIPART_CONTENT,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload failed unexpectedly. Please try again.")
        self.assertFalse(Submission.objects.filter(quest_assignment=self.assignment).exists())

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, QuestAssignment.Status.PENDING)
