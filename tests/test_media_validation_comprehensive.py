"""Comprehensive media validation tests for SubmissionMedia.clean() and view-level validation."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.submissions.models import SubmissionMedia

from .conftest import (
    QuestAssignmentFactory,
    SeasonQuestFactory,
    SubmissionFactory,
    SubmissionMediaFactory,
)


# ===========================================================================
# SubmissionMedia.clean() — model-level validation
# ===========================================================================


@pytest.mark.django_db
class TestSubmissionMediaClean:
    """Test SubmissionMedia.clean() size and duration constraints."""

    def _make_media(self, **kwargs):
        return SubmissionMediaFactory.build(**kwargs)

    # --- Image size ---

    def test_image_under_30mb_passes(self):
        media = self._make_media(
            media_type=SubmissionMedia.MediaType.IMAGE,
            file_size_bytes=29 * 1024 * 1024,
        )
        media.clean()  # should not raise

    def test_image_exactly_30mb_passes(self):
        media = self._make_media(
            media_type=SubmissionMedia.MediaType.IMAGE,
            file_size_bytes=30 * 1024 * 1024,
        )
        media.clean()  # should not raise

    def test_image_over_30mb_fails(self):
        media = self._make_media(
            media_type=SubmissionMedia.MediaType.IMAGE,
            file_size_bytes=30 * 1024 * 1024 + 1,
        )
        with pytest.raises(ValidationError, match="30MB"):
            media.clean()

    # --- Video size ---

    def test_video_under_100mb_passes(self):
        media = self._make_media(
            media_type=SubmissionMedia.MediaType.VIDEO,
            file_size_bytes=50 * 1024 * 1024,
            duration_seconds=10,
        )
        media.clean()  # should not raise

    def test_video_exactly_100mb_passes(self):
        media = self._make_media(
            media_type=SubmissionMedia.MediaType.VIDEO,
            file_size_bytes=100 * 1024 * 1024,
            duration_seconds=10,
        )
        media.clean()  # should not raise

    def test_video_over_100mb_fails(self):
        media = self._make_media(
            media_type=SubmissionMedia.MediaType.VIDEO,
            file_size_bytes=100 * 1024 * 1024 + 1,
            duration_seconds=10,
        )
        with pytest.raises(ValidationError, match="100MB"):
            media.clean()

    # --- Video duration ---

    def test_video_under_15s_passes(self):
        media = self._make_media(
            media_type=SubmissionMedia.MediaType.VIDEO,
            file_size_bytes=1024,
            duration_seconds=14,
        )
        media.clean()  # should not raise

    def test_video_exactly_15s_passes(self):
        media = self._make_media(
            media_type=SubmissionMedia.MediaType.VIDEO,
            file_size_bytes=1024,
            duration_seconds=15,
        )
        media.clean()  # should not raise

    def test_video_over_15s_fails(self):
        media = self._make_media(
            media_type=SubmissionMedia.MediaType.VIDEO,
            file_size_bytes=1024,
            duration_seconds=16,
        )
        with pytest.raises(ValidationError, match="15 seconds"):
            media.clean()

    def test_video_no_duration_passes(self):
        """When duration_seconds is None, the duration check is skipped."""
        media = self._make_media(
            media_type=SubmissionMedia.MediaType.VIDEO,
            file_size_bytes=1024,
            duration_seconds=None,
        )
        media.clean()  # should not raise


# ===========================================================================
# View-level validation constants
# ===========================================================================


@pytest.mark.django_db
class TestViewLevelValidationConstants:
    """Verify the view-level constants match expectations."""

    def test_allowed_image_extensions(self):
        from apps.submissions.views import ALLOWED_IMAGE_EXTENSIONS
        assert ALLOWED_IMAGE_EXTENSIONS == {".jpg", ".jpeg", ".png", ".webp"}

    def test_allowed_video_extensions(self):
        from apps.submissions.views import ALLOWED_VIDEO_EXTENSIONS
        assert ALLOWED_VIDEO_EXTENSIONS == {".mp4", ".mov"}

    def test_allowed_image_mime_types(self):
        from apps.submissions.views import ALLOWED_IMAGE_MIME_TYPES
        assert ALLOWED_IMAGE_MIME_TYPES == {"image/jpeg", "image/png", "image/webp"}

    def test_allowed_video_mime_types(self):
        from apps.submissions.views import ALLOWED_VIDEO_MIME_TYPES
        assert ALLOWED_VIDEO_MIME_TYPES == {"video/mp4", "video/quicktime"}

    def test_max_image_size(self):
        from apps.submissions.views import MAX_IMAGE_SIZE_BYTES
        assert MAX_IMAGE_SIZE_BYTES == 30 * 1024 * 1024

    def test_max_video_size(self):
        from apps.submissions.views import MAX_VIDEO_SIZE_BYTES
        assert MAX_VIDEO_SIZE_BYTES == 100 * 1024 * 1024

    def test_max_video_duration(self):
        from apps.submissions.views import MAX_VIDEO_DURATION_SECONDS
        assert MAX_VIDEO_DURATION_SECONDS == 15


# ===========================================================================
# _validate_media_files function
# ===========================================================================


@pytest.mark.django_db
class TestValidateMediaFilesFunction:
    """Test the _validate_media_files helper from views."""

    def _make_fake_file(self, name, content_type, size):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(name, b"x" * min(size, 100), content_type=content_type)

    @pytest.fixture(autouse=True)
    def _patch_duration(self):
        with pytest.importorskip("unittest.mock").patch(
            "apps.submissions.views.detect_video_duration_seconds", return_value=5,
        ):
            yield

    def test_valid_jpeg(self):
        from apps.submissions.views import _validate_media_files
        f = self._make_fake_file("photo.jpg", "image/jpeg", 1024)
        f.size = 1024
        assert _validate_media_files([f]) == []

    def test_valid_png(self):
        from apps.submissions.views import _validate_media_files
        f = self._make_fake_file("photo.png", "image/png", 1024)
        f.size = 1024
        assert _validate_media_files([f]) == []

    def test_valid_webp(self):
        from apps.submissions.views import _validate_media_files
        f = self._make_fake_file("photo.webp", "image/webp", 1024)
        f.size = 1024
        assert _validate_media_files([f]) == []

    def test_valid_mp4(self):
        from apps.submissions.views import _validate_media_files
        f = self._make_fake_file("video.mp4", "video/mp4", 1024)
        f.size = 1024
        assert _validate_media_files([f]) == []

    def test_valid_mov(self):
        from apps.submissions.views import _validate_media_files
        f = self._make_fake_file("video.mov", "video/quicktime", 1024)
        f.size = 1024
        assert _validate_media_files([f]) == []

    def test_unsupported_extension_rejected(self):
        from apps.submissions.views import _validate_media_files
        f = self._make_fake_file("file.gif", "image/gif", 1024)
        f.size = 1024
        errors = _validate_media_files([f])
        assert len(errors) == 1
        assert "unsupported" in errors[0].lower()

    def test_image_mime_mismatch_rejected(self):
        from apps.submissions.views import _validate_media_files
        f = self._make_fake_file("photo.jpg", "video/mp4", 1024)
        f.size = 1024
        errors = _validate_media_files([f])
        assert len(errors) == 1
        assert "MIME" in errors[0]

    def test_image_over_30mb_rejected(self):
        from apps.submissions.views import _validate_media_files
        f = self._make_fake_file("big.jpg", "image/jpeg", 31 * 1024 * 1024)
        f.size = 31 * 1024 * 1024
        errors = _validate_media_files([f])
        assert len(errors) == 1
        assert "30MB" in errors[0]

    def test_video_over_100mb_rejected(self):
        from apps.submissions.views import _validate_media_files
        f = self._make_fake_file("big.mp4", "video/mp4", 101 * 1024 * 1024)
        f.size = 101 * 1024 * 1024
        errors = _validate_media_files([f])
        assert len(errors) == 1
        assert "100MB" in errors[0]

    def test_video_over_15s_rejected(self):
        from apps.submissions.views import _validate_media_files
        with pytest.importorskip("unittest.mock").patch(
            "apps.submissions.views.detect_video_duration_seconds", return_value=20,
        ):
            f = self._make_fake_file("long.mp4", "video/mp4", 1024)
            f.size = 1024
            errors = _validate_media_files([f])
            assert len(errors) == 1
            assert "15 second" in errors[0]
