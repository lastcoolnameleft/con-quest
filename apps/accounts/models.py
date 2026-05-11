from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


class Account(AbstractUser):
    class Provider(models.TextChoices):
        LOCAL = "local", "Local"
        GOOGLE = "google", "Google"
        GITHUB = "github", "GitHub"

    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.LOCAL)
    provider_user_id = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_user_id"],
                condition=~Q(provider_user_id=""),
                name="accounts_unique_provider_user",
            )
        ]

    def __str__(self) -> str:
        return self.username
