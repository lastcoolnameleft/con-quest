from django.conf import settings
from django.db import models
from django.db.models import Q
import secrets


class Season(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    join_code = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.join_code:
            self.join_code = secrets.token_urlsafe(6)[:8].upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title


class SeasonParticipant(models.Model):
    class Role(models.TextChoices):
        HOST = "host", "Host"
        PLAYER = "player", "Player"
        VIEWER = "viewer", "Viewer"
        ADMIN = "admin", "Admin"

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="participants")
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="season_participations",
    )
    handle = models.CharField(max_length=50)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.PLAYER)
    is_guest = models.BooleanField(default=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["season", "handle"], name="season_handle_unique"),
            models.UniqueConstraint(
                fields=["season", "account"],
                condition=Q(account__isnull=False),
                name="season_account_unique_when_set",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.handle} @ {self.season.slug}"
