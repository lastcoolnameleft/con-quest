from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("seasons", "0003_season_keep_image_exif"),
    ]

    operations = [
        migrations.AlterField(
            model_name="season",
            name="is_private",
            field=models.BooleanField(default=False),
        ),
    ]
