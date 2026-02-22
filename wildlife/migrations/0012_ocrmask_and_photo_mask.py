from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("wildlife", "0011_alter_camera_base_latitude_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="OcrMask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("sample_image", models.ImageField(upload_to="ocr_masks/")),
                ("left_x", models.DecimalField(decimal_places=6, max_digits=7)),
                ("left_y", models.DecimalField(decimal_places=6, max_digits=7)),
                ("left_w", models.DecimalField(decimal_places=6, max_digits=7)),
                ("left_h", models.DecimalField(decimal_places=6, max_digits=7)),
                ("center_x", models.DecimalField(decimal_places=6, max_digits=7)),
                ("center_y", models.DecimalField(decimal_places=6, max_digits=7)),
                ("center_w", models.DecimalField(decimal_places=6, max_digits=7)),
                ("center_h", models.DecimalField(decimal_places=6, max_digits=7)),
                ("right_x", models.DecimalField(decimal_places=6, max_digits=7)),
                ("right_y", models.DecimalField(decimal_places=6, max_digits=7)),
                ("right_w", models.DecimalField(decimal_places=6, max_digits=7)),
                ("right_h", models.DecimalField(decimal_places=6, max_digits=7)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddField(
            model_name="photo",
            name="ocr_mask",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="photos", to="wildlife.ocrmask"),
        ),
    ]
