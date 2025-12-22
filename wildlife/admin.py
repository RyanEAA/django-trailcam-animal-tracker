from django.contrib import admin
from .models import User, Species, Camera, Photo, PhotoDetection
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth import get_user_model

User = get_user_model()

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # Add your custom field to the "change user" page
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Researcher Info", {"fields": ("is_researcher",)}),
    )

    # Add your custom field to the "add user" page
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Researcher Info", {"fields": ("is_researcher",)}),
    )

    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_researcher",
        "is_active",
    )
    list_filter = ("is_researcher", "is_staff", "is_superuser", "is_active")


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

admin.site.register(Species)
admin.site.register(Camera)
admin.site.register(PhotoDetection)
