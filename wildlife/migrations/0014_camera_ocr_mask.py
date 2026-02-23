from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wildlife", "0013_ocrmask_five_regions"),
    ]

    operations = [
        migrations.AddField(
            model_name="camera",
            name="ocr_mask",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="cameras",
                to="wildlife.ocrmask",
            ),
        ),
    ]
