from django.db import migrations, models
from django.db.models import Q


def demote_extra_active_quests(apps, schema_editor):
    SeasonQuest = apps.get_model("quests", "SeasonQuest")
    active_value = "active"
    pending_value = "pending"

    season_ids = (
        SeasonQuest.objects.filter(status=active_value)
        .values_list("season_id", flat=True)
        .distinct()
    )
    for season_id in season_ids:
        active_quests = list(
            SeasonQuest.objects.filter(season_id=season_id, status=active_value).order_by("-updated_at", "-id")
        )
        for season_quest in active_quests[1:]:
            season_quest.status = pending_value
            season_quest.save(update_fields=["status", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("quests", "0011_alter_seasonquest_duration_seconds_default"),
    ]

    operations = [
        migrations.RunPython(demote_extra_active_quests, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="seasonquest",
            constraint=models.UniqueConstraint(
                condition=Q(status="active"),
                fields=("season",),
                name="season_single_active_quest",
            ),
        ),
    ]
