from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("quests", "0003_rename_questtemplate_to_quest"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="seasonquest",
            name="entry_policy",
        ),
    ]
