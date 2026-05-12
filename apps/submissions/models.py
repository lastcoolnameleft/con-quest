from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.quests.models import QuestAssignment
from apps.seasons.models import SeasonParticipant


class Submission(models.Model):
    quest_assignment = models.OneToOneField(QuestAssignment, on_delete=models.CASCADE, related_name="submission")
    text_response = models.TextField(blank=True)
    is_draft = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_late = models.BooleanField(default=False)
    score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    judge_note = models.TextField(blank=True)
    scored_at = models.DateTimeField(null=True, blank=True)
    scored_by_participant = models.ForeignKey(
        SeasonParticipant,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scored_submissions",
    )

    def __str__(self) -> str:
        return f"Submission for assignment {self.quest_assignment_id}"


class SubmissionMedia(models.Model):
    class MediaType(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="media_items")
    blob_path_or_url = models.CharField(max_length=1000)
    media_type = models.CharField(max_length=12, choices=MediaType.choices)
    mime_type = models.CharField(max_length=100)
    file_size_bytes = models.PositiveBigIntegerField()
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    exif_data = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["submission", "sort_order"], name="submission_media_order_unique")
        ]

    def clean(self) -> None:
        max_image_size = 30 * 1024 * 1024
        max_video_size = 100 * 1024 * 1024

        if self.media_type == self.MediaType.IMAGE and self.file_size_bytes > max_image_size:
            raise ValidationError("Images must be 30MB or less.")
        if self.media_type == self.MediaType.VIDEO:
            if self.file_size_bytes > max_video_size:
                raise ValidationError("Videos must be 100MB or less.")
            if self.duration_seconds and self.duration_seconds > 15:
                raise ValidationError("Videos must be 15 seconds or shorter.")

    def __str__(self) -> str:
        return f"{self.media_type} for submission {self.submission_id}"
