from django.db import models

from apps.seasons.models import Season, SeasonParticipant


class AuditLog(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="audit_logs")
    actor_participant = models.ForeignKey(
        SeasonParticipant,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_actions",
    )
    action_type = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100)
    old_value_json = models.JSONField(default=dict, blank=True)
    new_value_json = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.action_type} on {self.target_type}:{self.target_id}"
