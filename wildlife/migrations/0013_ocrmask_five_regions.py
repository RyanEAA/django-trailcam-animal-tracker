from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wildlife", "0012_ocrmask_and_photo_mask"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="ocrmask",
            name="left_x",
        ),
        migrations.RemoveField(
            model_name="ocrmask",
            name="left_y",
        ),
        migrations.RemoveField(
            model_name="ocrmask",
            name="left_w",
        ),
        migrations.RemoveField(
            model_name="ocrmask",
            name="left_h",
        ),
        migrations.RemoveField(
            model_name="ocrmask",
            name="center_x",
        ),
        migrations.RemoveField(
            model_name="ocrmask",
            name="center_y",
        ),
        migrations.RemoveField(
            model_name="ocrmask",
            name="center_w",
        ),
        migrations.RemoveField(
            model_name="ocrmask",
            name="center_h",
        ),
        migrations.RemoveField(
            model_name="ocrmask",
            name="right_x",
        ),
        migrations.RemoveField(
            model_name="ocrmask",
            name="right_y",
        ),
        migrations.RemoveField(
            model_name="ocrmask",
            name="right_w",
        ),
        migrations.RemoveField(
            model_name="ocrmask",
            name="right_h",
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="temperature_x",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="temperature_y",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="temperature_w",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="temperature_h",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="pressure_x",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="pressure_y",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="pressure_w",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="pressure_h",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="camera_x",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="camera_y",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="camera_w",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="camera_h",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="date_x",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="date_y",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="date_w",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="date_h",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="time_x",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="time_y",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="time_w",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
        migrations.AddField(
            model_name="ocrmask",
            name="time_h",
            field=models.DecimalField(decimal_places=6, max_digits=7),
        ),
    ]
