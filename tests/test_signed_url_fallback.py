from django.test import Client
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from unittest.mock import patch

from apps.quests.models import QuestAssignment
from apps.quests.models import Quest
from apps.quests.models import SeasonQuest
from apps.seasons.models import Season
from apps.seasons.models import SeasonParticipant
from apps.submissions.models import Submission
from apps.submissions.models import SubmissionMedia
from apps.submissions.storage import signed_read_url


class SignedUrlFallbackTests(TestCase):
    @override_settings(AZURE_STORAGE_ACCOUNT_NAME="", AZURE_STORAGE_ACCOUNT_KEY="")
    def test_signed_read_url_returns_original_when_credentials_missing(self):
        blob_url = "https://example.blob.core.windows.net/media/season/a/file.jpg"
        self.assertEqual(signed_read_url(blob_url), blob_url)

    @override_settings(AZURE_STORAGE_ACCOUNT_NAME="acct", AZURE_STORAGE_ACCOUNT_KEY="key")
    def test_signed_read_url_returns_original_when_blob_url_path_is_invalid(self):
        invalid_blob_url = "https://example.blob.core.windows.net/"
        self.assertEqual(signed_read_url(invalid_blob_url), invalid_blob_url)

    @override_settings(AZURE_STORAGE_ACCOUNT_NAME="acct", AZURE_STORAGE_ACCOUNT_KEY="key")
    @patch("apps.submissions.storage.generate_blob_sas", side_effect=RuntimeError("boom"))
    def test_signed_read_url_returns_original_when_signing_raises(self, _mock_sas):
        blob_url = "https://example.blob.core.windows.net/media/season/a/file.jpg"
        self.assertEqual(signed_read_url(blob_url), blob_url)

    @override_settings(AZURE_STORAGE_ACCOUNT_NAME="", AZURE_STORAGE_ACCOUNT_KEY="")
    def test_scoring_queue_uses_original_media_url_when_signing_unavailable(self):
        client = Client()
        season = Season.objects.create(title="Signed URL Season", slug="signed-url-season")
        host = SeasonParticipant.objects.create(
            season=season,
            handle="host",
            role=SeasonParticipant.Role.HOST,
            is_guest=True,
        )
        player = SeasonParticipant.objects.create(
            season=season,
            handle="player",
            role=SeasonParticipant.Role.PLAYER,
            is_guest=True,
        )
        template = Quest.objects.create(title="Quest", description="Desc")
        season_quest = SeasonQuest.objects.create(
            season=season,
            quest=template,
            title_override="Quest",
            points_max=5,
        )
        assignment = QuestAssignment.objects.create(
            season_quest=season_quest,
            participant=player,
            status=QuestAssignment.Status.SUBMITTED,
        )
        submission = Submission.objects.create(quest_assignment=assignment, text_response="content")
        blob_url = "https://example.blob.core.windows.net/media/season/signed-url-season/assignment/1/image/file.jpg"
        SubmissionMedia.objects.create(
            submission=submission,
            blob_path_or_url=blob_url,
            media_type=SubmissionMedia.MediaType.IMAGE,
            mime_type="image/jpeg",
            file_size_bytes=1024,
            sort_order=0,
        )

        session = client.session
        session[f"season_participant_{season.id}"] = host.id
        session.save()

        response = client.get(reverse("season-scoring-queue", kwargs={"slug": season.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, blob_url)
