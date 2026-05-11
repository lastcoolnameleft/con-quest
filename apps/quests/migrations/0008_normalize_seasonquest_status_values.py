from django.db import migrations


def normalize_status_values(apps, schema_editor):
    SeasonQuest = apps.get_model("quests", "SeasonQuest")
    SeasonQuest.objects.filter(status="waiting").update(status="pending")
    SeasonQuest.objects.filter(status="live").update(status="active")
    SeasonQuest.objects.filter(status="closed").update(status="complete")


def revert_status_values(apps, schema_editor):
    SeasonQuest = apps.get_model("quests", "SeasonQuest")
    SeasonQuest.objects.filter(status="pending").update(status="waiting")
    SeasonQuest.objects.filter(status="active").update(status="live")
    SeasonQuest.objects.filter(status="complete").update(status="closed")


class Migration(migrations.Migration):

    dependencies = [
        ("quests", "0007_alter_seasonquest_status"),
    ]

    operations = [
        migrations.RunPython(normalize_status_values, revert_status_values),
    ]
