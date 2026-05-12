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
from apps.submissions.storage import StorageConfigurationError


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
            {"text_response": "hello", "media_files": upload, "submit_action": "submit"},
            content_type=MULTIPART_CONTENT,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload failed unexpectedly. Please try again.")
        self.assertFalse(Submission.objects.filter(quest_assignment=self.assignment).exists())

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, QuestAssignment.Status.PENDING)

    @patch(
        "apps.submissions.views.upload_submission_media",
        side_effect=StorageConfigurationError("Azure Blob storage credentials are not configured."),
    )
    def test_submit_assignment_masks_storage_configuration_error(self, _mock_upload):
        upload = SimpleUploadedFile("photo.jpg", b"image-bytes", content_type="image/jpeg")

        response = self.client.post(
            reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
            {"text_response": "hello", "media_files": upload, "submit_action": "submit"},
            content_type=MULTIPART_CONTENT,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "There was an error uploading the media.")
        self.assertNotContains(response, "Azure Blob storage credentials are not configured.")
        self.assertFalse(Submission.objects.filter(quest_assignment=self.assignment).exists())

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, QuestAssignment.Status.PENDING)

    def test_existing_submission_can_be_viewed_and_edited(self):
        submission = Submission.objects.create(
            quest_assignment=self.assignment,
            text_response="original text",
            is_draft=False,
        )
        self.assignment.status = QuestAssignment.Status.SUBMITTED
        self.assignment.save(update_fields=["status"])

        get_response = self.client.get(reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}))
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, "View submission")
        self.assertContains(get_response, "Save Draft")
        self.assertContains(get_response, "Submit for scoring")
        self.assertContains(get_response, "original text")

        post_response = self.client.post(
            reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
            {"text_response": "edited text", "submit_action": "submit"},
            follow=True,
        )

        self.assertEqual(post_response.status_code, 200)
        self.assertContains(post_response, "Submission updated and submitted for scoring.")
        submission.refresh_from_db()
        self.assertEqual(submission.text_response, "edited text")

    def test_scored_submission_is_view_only(self):
        submission = Submission.objects.create(
            quest_assignment=self.assignment,
            text_response="locked text",
            score=5,
        )
        self.assignment.status = QuestAssignment.Status.SCORED
        self.assignment.save(update_fields=["status"])

        get_response = self.client.get(reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}))
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, "view-only")
        self.assertNotContains(get_response, "Update submission")

        post_response = self.client.post(
            reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
            {"text_response": "attempted edit", "submit_action": "submit"},
            follow=True,
        )

        self.assertEqual(post_response.status_code, 200)
        self.assertContains(post_response, "can no longer be edited")
        submission.refresh_from_db()
        self.assertEqual(submission.text_response, "locked text")

    def test_save_draft_then_submit_for_scoring(self):
        draft_response = self.client.post(
            reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
            {"text_response": "draft text", "submit_action": "draft"},
            follow=True,
        )

        self.assertEqual(draft_response.status_code, 200)
        self.assertContains(draft_response, "Draft saved.")
        submission = Submission.objects.get(quest_assignment=self.assignment)
        self.assertTrue(submission.is_draft)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, QuestAssignment.Status.PENDING)

        submit_response = self.client.post(
            reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
            {"text_response": "final text", "submit_action": "submit"},
            follow=True,
        )

        self.assertEqual(submit_response.status_code, 200)
        self.assertContains(submit_response, "submitted for scoring")
        submission.refresh_from_db()
        self.assertFalse(submission.is_draft)
        self.assertEqual(submission.text_response, "final text")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, QuestAssignment.Status.SUBMITTED)
