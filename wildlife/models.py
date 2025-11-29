from django.db import models

# Create your models here.
class Camera(models.Model):
    name = models.CharField(max_length=100)
    latitude = models.FloatField()
    longitude = models.FloatField()
    location_description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.name
    
class Species(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name
    
class Sighting(models.Model):
    image = models.ImageField(upload_to='sightings/')
    timestamp = models.DateTimeField(auto_now_add=True)
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE)
    species = models.ForeignKey(Species, on_delete=models.CASCADE)
    weather = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.species.name} sighted at {self.camera.name} on {self.timestamp}"