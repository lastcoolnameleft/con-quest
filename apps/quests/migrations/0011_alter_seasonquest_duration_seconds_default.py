from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quests", "0010_alter_seasonquest_late_defaults"),
    ]

    operations = [
        migrations.AlterField(
            model_name="seasonquest",
            name="duration_seconds",
            field=models.PositiveIntegerField(default=300),
        ),
    ]
