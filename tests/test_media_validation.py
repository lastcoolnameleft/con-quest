from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.submissions.views import _validate_media_files


class MediaValidationTests(TestCase):
    def test_rejects_unsupported_extension(self):
        unknown = SimpleUploadedFile("malware.exe", b"payload", content_type="application/octet-stream")
        errors = _validate_media_files([unknown])
        self.assertEqual(len(errors), 1)
        self.assertIn("unsupported file type", errors[0])

    @patch("apps.submissions.views.detect_video_duration_seconds", return_value=20)
    def test_rejects_video_over_duration_limit(self, _mock_duration):
        video = SimpleUploadedFile("clip.mp4", b"video-bytes", content_type="video/mp4")
        errors = _validate_media_files([video])
        self.assertEqual(len(errors), 1)
        self.assertIn("15 second duration limit", errors[0])
