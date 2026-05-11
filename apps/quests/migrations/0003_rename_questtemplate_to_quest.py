from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("quests", "0002_seasonquest_rsvp_code"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="QuestTemplate",
            new_name="Quest",
        ),
        migrations.RenameField(
            model_name="seasonquest",
            old_name="quest_template",
            new_name="quest",
        ),
    ]
