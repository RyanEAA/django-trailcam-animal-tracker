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

    # JSON endpoints for modal save
    path("camera/create/", views.camera_create, name="camera_create"),
    path("camera/<int:pk>/update/", views.camera_update, name="camera_update"),



]
