from django.contrib import admin
from .models import Camera, Species, Sighting

# Register your models here.

@admin.register(Sighting)
class SightingAdmin(admin.ModelAdmin):
    list_display = ("id", "camera", "timestamp")
    list_filter = ("camera", "species")
    search_fields = ("camera__name", "species__name")

admin.site.register(Camera)
admin.site.register(Species)
