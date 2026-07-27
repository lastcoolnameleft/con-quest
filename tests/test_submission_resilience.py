from unittest.mock import patch
import json

from django.core import signing
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
from apps.submissions.models import SubmissionMedia
from apps.submissions.storage import StorageConfigurationError
from apps.submissions.views import UPLOAD_TICKET_SALT


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
        self.assertContains(get_response, "Edit Submission")
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

    def test_submit_assignment_rejects_more_than_five_files(self):
        uploads = [
            SimpleUploadedFile(f"proof-{i}.jpg", b"image-bytes", content_type="image/jpeg")
            for i in range(6)
        ]

        response = self.client.post(
            reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
            {"text_response": "too many", "media_files": uploads, "submit_action": "submit"},
            content_type=MULTIPART_CONTENT,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You can add up to 5 media files per submission.")
        self.assertFalse(Submission.objects.filter(quest_assignment=self.assignment).exists())

    @patch("apps.submissions.views.create_direct_upload_target")
    def test_prepare_assignment_upload_targets_returns_signed_ticket(self, mock_target):
        mock_target.return_value = {
            "upload_url": "https://blob.example/upload?sas=1",
            "blob_url": "https://blob.example/container/season/test.jpg",
            "blob_name": "season/test.jpg",
            "expires_at": "2030-01-01T00:00:00+00:00",
        }

        response = self.client.post(
            reverse("assignment-upload-targets", kwargs={"assignment_id": self.assignment.id}),
            data=json.dumps(
                {
                    "files": [
                        {
                            "name": "proof.jpg",
                            "size": 1024,
                            "type": "image/jpeg",
                        }
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["uploads"]), 1)
        self.assertTrue(payload["uploads"][0]["ticket"])
        self.assertEqual(payload["uploads"][0]["upload_url"], "https://blob.example/upload?sas=1")

    def test_prepare_assignment_upload_targets_rejects_video_without_duration(self):
        response = self.client.post(
            reverse("assignment-upload-targets", kwargs={"assignment_id": self.assignment.id}),
            data=json.dumps(
                {
                    "files": [
                        {
                            "name": "proof.mp4",
                            "size": 1024,
                            "type": "video/mp4",
                        }
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("duration", " ".join(payload.get("errors", [])).lower())

    @patch("apps.submissions.views.fetch_blob_properties", return_value={"size": 2048, "content_type": "image/jpeg"})
    @patch("apps.submissions.views.upload_submission_media")
    def test_submit_assignment_uses_uploaded_manifest_without_server_upload(self, mock_upload_submission_media, _mock_blob_props):
        ticket = signing.dumps(
            {
                "assignment_id": self.assignment.id,
                "participant_id": self.player.id,
                "blob_url": "https://blob.example/container/season/file.jpg",
                "media_type": "image",
                "content_type": "image/jpeg",
                "file_size_bytes": 2048,
                "original_name": "file.jpg",
            },
            salt=UPLOAD_TICKET_SALT,
        )

        response = self.client.post(
            reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
            {
                "text_response": "manifest upload",
                "uploaded_media_manifest": json.dumps([{"ticket": ticket}]),
                "submit_action": "submit",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Submission received.")
        submission = Submission.objects.get(quest_assignment=self.assignment)
        self.assertEqual(submission.media_items.count(), 1)
        media = submission.media_items.first()
        self.assertEqual(media.blob_path_or_url, "https://blob.example/container/season/file.jpg")
        mock_upload_submission_media.assert_not_called()

    @patch("apps.submissions.views.fetch_blob_properties", return_value={"size": 2048, "content_type": "image/jpeg"})
    def test_submit_assignment_can_interleave_uploaded_manifest_with_existing_media(self, _mock_blob_props):
        submission = Submission.objects.create(
            quest_assignment=self.assignment,
            text_response="original",
            is_draft=False,
        )
        first = SubmissionMedia.objects.create(
            submission=submission,
            blob_path_or_url="https://blob.example/existing-one.jpg",
            media_type=SubmissionMedia.MediaType.IMAGE,
            mime_type="image/jpeg",
            file_size_bytes=1024,
            sort_order=0,
        )
        second = SubmissionMedia.objects.create(
            submission=submission,
            blob_path_or_url="https://blob.example/existing-two.jpg",
            media_type=SubmissionMedia.MediaType.IMAGE,
            mime_type="image/jpeg",
            file_size_bytes=2048,
            sort_order=1,
        )

        ticket = signing.dumps(
            {
                "assignment_id": self.assignment.id,
                "participant_id": self.player.id,
                "blob_url": "https://blob.example/container/season/new-file.jpg",
                "media_type": "image",
                "content_type": "image/jpeg",
                "file_size_bytes": 2048,
                "original_name": "new-file.jpg",
            },
            salt=UPLOAD_TICKET_SALT,
        )

        response = self.client.post(
            reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
            {
                "text_response": "updated",
                "submit_action": "submit",
                f"media_order_{first.id}": "2",
                f"media_order_{second.id}": "3",
                "uploaded_media_manifest": json.dumps([{"ticket": ticket, "sort_order": 1}]),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        ordered = list(submission.media_items.order_by("sort_order", "id"))
        self.assertEqual(len(ordered), 3)
        self.assertEqual(ordered[0].blob_path_or_url, "https://blob.example/container/season/new-file.jpg")
        self.assertEqual([ordered[1].id, ordered[2].id], [first.id, second.id])
        self.assertEqual([media.sort_order for media in ordered], [0, 1, 2])

    def test_submit_assignment_can_reorder_and_remove_existing_media(self):
        submission = Submission.objects.create(
            quest_assignment=self.assignment,
            text_response="original",
            is_draft=False,
        )
        media_one = SubmissionMedia.objects.create(
            submission=submission,
            blob_path_or_url="https://blob.example/one.jpg",
            media_type=SubmissionMedia.MediaType.IMAGE,
            mime_type="image/jpeg",
            file_size_bytes=1024,
            sort_order=0,
        )
        media_two = SubmissionMedia.objects.create(
            submission=submission,
            blob_path_or_url="https://blob.example/two.jpg",
            media_type=SubmissionMedia.MediaType.IMAGE,
            mime_type="image/jpeg",
            file_size_bytes=2048,
            sort_order=1,
        )
        media_three = SubmissionMedia.objects.create(
            submission=submission,
            blob_path_or_url="https://blob.example/three.jpg",
            media_type=SubmissionMedia.MediaType.IMAGE,
            mime_type="image/jpeg",
            file_size_bytes=4096,
            sort_order=2,
        )

        response = self.client.post(
            reverse("assignment-submit", kwargs={"assignment_id": self.assignment.id}),
            {
                "text_response": "updated",
                "submit_action": "submit",
                f"media_order_{media_one.id}": "2",
                f"media_order_{media_two.id}": "1",
                f"media_order_{media_three.id}": "3",
                "delete_media_ids": [str(media_two.id)],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        remaining = list(submission.media_items.order_by("sort_order", "id"))
        self.assertEqual([media.id for media in remaining], [media_one.id, media_three.id])
        self.assertEqual([media.sort_order for media in remaining], [0, 1])
