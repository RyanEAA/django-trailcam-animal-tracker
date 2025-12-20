from django.urls import path
from . import views

app_name = "wildlife"

urlpatterns = [
    path("", views.index, name="index"),
    path("gallery/", views.gallery, name="gallery"),
    path("upload/", views.upload_photos, name="upload_photos"),

    path("photo/<int:pk>/analyze/", views.analyze_photo, name="analyze_photo"),
    path("photo/<int:pk>/publish/", views.publish_photo, name="publish_photo"),

    path("photo/<int:pk>/delete-staging/", views.delete_photo_staging, name="delete_photo_staging"),
    path("photo/<int:pk>/meta/update/", views.update_photo_meta, name="update_photo_meta"),
    # upublish photo
    path("photo/<int:pk>/unpublish/", views.unpublish_photo, name="unpublish_photo"),
    # Cameras CRUD
    path("cameras/", views.cameras_list, name="cameras_list"),
    path("cameras/new/", views.camera_create, name="camera_create"),
    path("cameras/<int:pk>/edit/", views.camera_edit, name="camera_edit"),
    path("cameras/suggest/", views.cameras_suggest, name="cameras_suggest"),



]
