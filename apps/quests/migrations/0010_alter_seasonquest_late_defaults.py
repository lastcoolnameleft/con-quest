from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quests", "0009_alter_seasonquest_quest_mode_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="seasonquest",
            name="allow_late_submissions",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="seasonquest",
            name="late_grace_seconds",
            field=models.PositiveIntegerField(default=300),
        ),
    ]
