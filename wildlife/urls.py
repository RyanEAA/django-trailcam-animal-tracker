from django.urls import path
from . import views

app_name = "wildlife"

urlpatterns = [
    path("", views.index, name="index"),
    path("gallery/", views.gallery, name="gallery"),
    path("upload/", views.upload_photos, name="upload_photos"),

    # Phot detail and edit
    path("photo/<int:pk>/analyze/", views.analyze_photo, name="analyze_photo"),
    path("photo/<int:pk>/publish/", views.publish_photo, name="publish_photo"),
    path("photo/<int:pk>/delete-staging/", views.delete_photo_staging, name="delete_photo_staging"),
    # photo meta JSON endpoint removed; use page-based editor
    path("photo/<int:pk>/unpublish/", views.unpublish_photo, name="unpublish_photo"),

    ## photo model open/close locks removed

    # Cameras CRUD
    path("cameras/", views.cameras_list, name="cameras_list"),

    # Page-based camera create/edit (replaces modal UI)
    path("camera/new/", views.camera_new, name="camera_new"),
    path("camera/<int:pk>/edit/", views.camera_edit, name="camera_edit"),
    # Page-based photo editor
    path("photo/<int:pk>/edit/", views.photo_edit, name="photo_edit"),

    # camera JSON endpoints removed; use page-based create/edit views

    # camera model open/close locks removed


]
