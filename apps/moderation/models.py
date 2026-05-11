from django.db import models

from apps.seasons.models import SeasonParticipant


class ModerationReport(models.Model):
    class Reason(models.TextChoices):
        SPAM = "spam", "Spam"
        HARASSMENT = "harassment", "Harassment"
        EXPLICIT = "explicit", "Explicit"
        CHEATING = "cheating", "Cheating"
        COPYRIGHT = "copyright", "Copyright"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        DISMISSED = "dismissed", "Dismissed"
        ACTIONED = "actioned", "Actioned"

    reporter_participant = models.ForeignKey(
        SeasonParticipant,
        on_delete=models.CASCADE,
        related_name="reports_made",
    )
    target_type = models.CharField(max_length=50)
    target_id = models.CharField(max_length=50)
    reason = models.CharField(max_length=16, choices=Reason.choices)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Report {self.id} ({self.reason})"
