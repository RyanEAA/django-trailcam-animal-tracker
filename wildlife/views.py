from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

import csv

from .forms import PhotoUploadForm, PhotoEditForm
from .models import Photo, Species
from .utils import require_researcher
from django.http import HttpResponse



# Create your views here.

# Home landing page
def index(request):
    return render(request, 'wildlife/index.html')


def gallery(request):
    """
    Public gallery (GET):
      - Anyone can view photos.
      - Filters can be added later.

    Researcher upload (POST):
      - If a logged-in researcher submits the form,
        handle multi-file upload and then reload the gallery.
    """
    # Handle upload if it's a POST from a researcher
    if request.method == "POST":
        if not request.user.is_authenticated or not getattr(request.user, "is_researcher", False):
            return HttpResponseForbidden("Only researchers can upload photos.")

        form = PhotoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist("images")
            for f in files:
                Photo.objects.create(
                    image=f,
                    uploaded_by=request.user,
                    uploaded_at=timezone.now(),
                )
            # After upload, redirect to GET to avoid resubmitting on refresh
            return redirect("wildlife:gallery")
    else:
        form = PhotoUploadForm() if request.user.is_authenticated and getattr(request.user, "is_researcher", False) else None

    photos = Photo.objects.all().select_related("species").order_by("-uploaded_at")
    species_list = Species.objects.all().order_by("name")

    return render(
        request,
        "wildlife/gallery.html",
        {
            "photos": photos,
            "species_list": species_list,
            "upload_form": form,
        },
    )


def photo_detail(request, pk):
    photo = get_object_or_404(Photo, pk=pk)
    return render(request, "wildlife/photo_detail.html", {"photo": photo})


@login_required
def researcher_dashboard(request):
    require_researcher(request.user)
    photos = Photo.objects.filter(uploaded_by=request.user).order_by("-uploaded_at")
    return render(request, "wildlife/researcher_dashboard.html", {"photos": photos})


@login_required
def upload_photos(request):
    if not request.user.is_researcher:
        return HttpResponseForbidden("Only researchers can upload.")

    if request.method == "POST":
        form = PhotoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist("images")
            for f in files:
                Photo.objects.create(
                    image=f,
                    uploaded_by=request.user,
                    uploaded_at=timezone.now(),
                )
            return redirect("wildlife:gallery")
    else:
        form = PhotoUploadForm()

    return render(
        request,
        "wildlife/upload.html",
        {"form": form},
    )


@login_required
def edit_photo(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)

    # If you want only uploader to edit, enforce here:
    # if photo.uploaded_by != request.user: raise PermissionDenied()

    if request.method == "POST":
        form = PhotoEditForm(request.POST, instance=photo)
        if form.is_valid():
            form.save()
            return redirect("wildlife:researcher_dashboard")
    else:
        form = PhotoEditForm(instance=photo)

    return render(request, "wildlife/edit_photo.html", {"form": form, "photo": photo})

@login_required
def delete_photo(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)

    if request.method == "POST":
        photo.delete()
        return redirect("wildlife:researcher_dashboard")

    return render(request, "wildlife/confirm_delete.html", {"photo": photo})

@login_required
def export_photos_csv(request):
    require_researcher(request.user)

    # You could re-use gallery filters here if you want
    photos = Photo.objects.all().select_related("species")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="trailcam_photos.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "id", "species", "date_taken", "environment",
        "latitude", "longitude", "uploaded_by", "uploaded_at",
    ])

    for p in photos:
        writer.writerow([
            p.id,
            p.species.name if p.species else "",
            p.date_taken.isoformat() if p.date_taken else "",
            p.environment,
            p.latitude or "",
            p.longitude or "",
            p.uploaded_by.username if p.uploaded_by else "",
            p.uploaded_at.isoformat(),
        ])

    return response
