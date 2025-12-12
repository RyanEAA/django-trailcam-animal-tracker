from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Photo, Species, Camera

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Role", {"fields": ("is_researcher",)}),
    )
    list_display = ("username", "email", "is_researcher", "is_staff", "is_superuser")

@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "species", "date_taken", "uploaded_by")
    list_filter = ("species", "date_taken")

# admin.site.register(User)
# admin.site.register(Species)
# admin.site.register(Camera)
# admin.site.register(Photo)