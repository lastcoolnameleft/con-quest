from django.core.exceptions import ValidationError
from django.db import models

from apps.seasons.models import Season, SeasonParticipant


class Quest(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    default_duration_seconds = models.PositiveIntegerField(default=120)
    default_points_max = models.PositiveSmallIntegerField(default=5)
    default_media_rules_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.title


class SeasonQuest(models.Model):
    class QuestMode(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        OPEN = "open", "Drop-in"

    class AssignmentPolicy(models.TextChoices):
        HOST_ASSIGNED = "host_assigned", "Host Assigned"
        OPEN_CLAIM = "open_claim", "Open Claim"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        COMPLETE = "complete", "Closed"
        ARCHIVED = "archived", "Archived"

    class RevealPolicy(models.TextChoices):
        INSTANT = "instant", "Instant"
        AFTER_CLOSE = "after_close", "End Of Quest"
        END_OF_EVENT = "end_of_event", "End Of Season"

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="quests")
    quest = models.ForeignKey(Quest, on_delete=models.PROTECT, related_name="season_quests")
    title_override = models.CharField(max_length=200, blank=True)
    description_override = models.TextField(blank=True)
    quest_mode = models.CharField(max_length=16, choices=QuestMode.choices, default=QuestMode.OPEN)
    assignment_policy = models.CharField(
        max_length=20, choices=AssignmentPolicy.choices, default=AssignmentPolicy.OPEN_CLAIM
    )
    rsvp_code = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    start_mode = models.CharField(max_length=20, default="admin_triggered")
    duration_seconds = models.PositiveIntegerField(default=120)
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    reveal_policy = models.CharField(max_length=20, choices=RevealPolicy.choices, default=RevealPolicy.INSTANT)
    points_max = models.PositiveSmallIntegerField(default=5)
    allow_late_submissions = models.BooleanField(default=False)
    late_grace_seconds = models.PositiveIntegerField(default=0)
    created_by_participant = models.ForeignKey(
        SeasonParticipant,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_quests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def resolved_title(self) -> str:
        return self.title_override or self.quest.title

    @property
    def resolved_description(self) -> str:
        return self.description_override or self.quest.description

    @property
    def effective_rsvp_code(self) -> str:
        return (self.rsvp_code or self.season.join_code or "").strip().upper()

    def clean(self) -> None:
        if self.quest_mode == self.QuestMode.SCHEDULED:
            if self.duration_seconds == 0:
                raise ValidationError("Scheduled quests must have a positive duration.")

    def allowed_next_statuses(self) -> set[str]:
        transitions = {
            self.Status.DRAFT: {self.Status.PENDING, self.Status.ARCHIVED},
            self.Status.PENDING: {self.Status.ACTIVE, self.Status.ARCHIVED},
            self.Status.ACTIVE: {self.Status.COMPLETE, self.Status.ARCHIVED},
            self.Status.COMPLETE: {self.Status.ARCHIVED},
            self.Status.ARCHIVED: set(),
        }
        return transitions.get(self.status, set())

    def can_transition_to(self, target_status: str) -> bool:
        return target_status in self.allowed_next_statuses()

    def __str__(self) -> str:
        return f"{self.resolved_title} ({self.season.slug})"


class QuestAssignment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUBMITTED = "submitted", "Submitted"
        SCORED = "scored", "Scored"
        MISSED = "missed", "Missed"
        EXCUSED = "excused", "Excused"

    class Source(models.TextChoices):
        HOST_ASSIGNED = "host_assigned", "Host Assigned"
        OPEN_CLAIM = "open_claim", "Open Claim"
        QR_SCAN = "qr_scan", "QR Scan"
        RSVP_CODE = "rsvp_code", "RSVP Code"

    season_quest = models.ForeignKey(SeasonQuest, on_delete=models.CASCADE, related_name="assignments")
    participant = models.ForeignKey(SeasonParticipant, on_delete=models.CASCADE, related_name="quest_assignments")
    assigned_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    assignment_source = models.CharField(max_length=20, choices=Source.choices, default=Source.OPEN_CLAIM)
    submission_due_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["season_quest", "participant"], name="season_quest_participant_unique")
        ]

    def __str__(self) -> str:
        return f"{self.participant.handle} -> {self.season_quest.resolved_title}"
