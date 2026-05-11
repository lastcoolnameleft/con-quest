from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("quests", "0004_remove_seasonquest_entry_policy"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="seasonquest",
            name="season_display_order_unique",
        ),
        migrations.RemoveField(
            model_name="seasonquest",
            name="display_order",
        ),
    ]
