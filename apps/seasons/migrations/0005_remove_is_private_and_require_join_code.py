import secrets

from django.db import migrations, models


def ensure_join_codes(apps, schema_editor):
    Season = apps.get_model("seasons", "Season")
    for season in Season.objects.filter(join_code__in=[None, ""]):
        season.join_code = secrets.token_urlsafe(6)[:8].upper()
        season.save(update_fields=["join_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("seasons", "0004_alter_season_is_private_default_open"),
    ]

    operations = [
        migrations.RunPython(ensure_join_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="season",
            name="join_code",
            field=models.CharField(max_length=20),
        ),
        migrations.RemoveField(
            model_name="season",
            name="is_private",
        ),
    ]
