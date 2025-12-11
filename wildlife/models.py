from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    is_researcher = models.BooleanField(default=False)

class Species(models.Model):
    name = models.CharField(max_length=128, unique=True)

    def __str__(self):
        return self.name

class Photo(models.Model):
    image = models.ImageField(upload_to='trailcam/')
    species = models.ForeignKey(Species, null=True, blank=True, on_delete=models.SET_NULL)
    date_taken = models.DateField(null=True, blank=True)
    environment = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    uploaded_by = models.ForeignKey(
        'wildlife.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='uploaded_photos',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    megadetector_result = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.species or 'Unknown'} ({self.pk})"
