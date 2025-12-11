from django.urls import path
from . import views

app_name = "wildlife"

urlpatterns = [
    path("", views.gallery, name="gallery"),
    path("upload/", views.upload_photos, name="upload_photos"),
    path("photo/<int:pk>/", views.photo_detail, name="photo_detail"),
    path("photo/<int:pk>/edit/", views.edit_photo, name="edit_photo"),
    path("photo/<int:pk>/delete/", views.delete_photo, name="delete_photo"),
    path("export/csv/", views.export_photos_csv, name="export_photos_csv"),
]
