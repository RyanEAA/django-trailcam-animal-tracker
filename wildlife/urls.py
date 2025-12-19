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



    # optional detail/edit/delete
    # path("photo/<int:pk>/", views.photo_detail, name="photo_detail"),
    # path("photo/<int:pk>/edit/", views.edit_photo, name="edit_photo"),
    # path("photo/<int:pk>/delete/", views.delete_photo, name="delete_photo"),
]
