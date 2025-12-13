from django.contrib import admin
from .models import User, Species, Camera, Photo, PhotoDetection

@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "species_summary", "camera", "date_taken", "pressure", "uploaded_by", "uploaded_at")
    list_filter = ("camera", "date_taken", "uploaded_at")
    search_fields = ("id", "image", "environment")

    def species_summary(self, obj):
        names = (
            obj.detections.select_related("species")
            .values_list("species__name", flat=True)
        )
        names = [n for n in names if n]
        return ", ".join(sorted(set(names))) if names else "Unknown"
    species_summary.short_description = "Species"

admin.site.register(User)
admin.site.register(Species)
admin.site.register(Camera)
admin.site.register(PhotoDetection)
