from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    is_researcher = models.BooleanField(default=False)

class Species(models.Model):
    name = models.CharField(max_length=128, unique=True)

    def __str__(self):
        return self.name


class Camera(models.Model):
    # e.g. "TRAILCAM03" or "03" or "StEdwards-03"
    name = models.CharField(max_length=64, unique=True)

    # Base location for that camera
    base_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    base_longitude = models.DecimalField(max_digits=9, decimal_places=6)

    # Optional metadata
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Photo(models.Model):
    image = models.ImageField(upload_to='trailcam/')

    # NEW: Camera FK
    camera = models.ForeignKey(Camera, null=True, blank=True, on_delete=models.SET_NULL)

    species = models.ForeignKey(Species, null=True, blank=True, on_delete=models.SET_NULL)
    date_taken = models.DateField(null=True, blank=True)
    environment = models.CharField(max_length=255, blank=True)

    # Photo’s location (can be copied from camera base lat/long)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    pressure = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    uploaded_by = models.ForeignKey(
        'wildlife.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='uploaded_photos',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    megadetector_result = models.JSONField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # If a camera is chosen and photo lat/long aren't set, default them from camera base coords
        if self.camera and (self.latitude is None or self.longitude is None):
            self.latitude = self.latitude if self.latitude is not None else self.camera.base_latitude
            self.longitude = self.longitude if self.longitude is not None else self.camera.base_longitude
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.species or 'Unknown'} ({self.pk})"
