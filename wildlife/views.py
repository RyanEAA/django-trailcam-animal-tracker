from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

import csv

from .forms import PhotoUploadForm, PhotoEditForm
from .models import Photo, Species
from .utils import require_researcher
from django.http import HttpResponse, HttpResponseForbidden

from django.db.models import Q
from django.shortcuts import render
from .models import Photo, Species, Camera


# Create your views here.

# Home landing page
def index(request):
    return render(request, 'wildlife/index.html')


def gallery(request):
    qs = Photo.objects.all().order_by("-uploaded_at")

    # ---- read filters from querystring ----
    species_ids = request.GET.getlist("species")  # multi-select
    camera_id = request.GET.get("camera", "").strip()

    start_date = request.GET.get("start_date", "").strip()
    end_date = request.GET.get("end_date", "").strip()

    temp_min = request.GET.get("temp_min", "").strip()
    temp_max = request.GET.get("temp_max", "").strip()

    pressure_min = request.GET.get("pressure_min", "").strip()
    pressure_max = request.GET.get("pressure_max", "").strip()

    # ---- apply filters ----
    if species_ids:
        qs = qs.filter(species_id__in=species_ids)

    # If you have a camera FK on Photo:
    if camera_id:
        qs = qs.filter(camera_id=camera_id)

    # Date range (assuming you have date_taken; fallback to uploaded_at date if not)
    # Prefer date_taken if you have it:
    if start_date:
        qs = qs.filter(date_taken__gte=start_date) if hasattr(Photo, "date_taken") else qs.filter(uploaded_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(date_taken__lte=end_date) if hasattr(Photo, "date_taken") else qs.filter(uploaded_at__date__lte=end_date)

    # Temperature range (only if Photo has temperature)
    if temp_min:
        qs = qs.filter(temperature__gte=temp_min)
    if temp_max:
        qs = qs.filter(temperature__lte=temp_max)

    # Pressure range (only if Photo has pressure)
    if pressure_min:
        qs = qs.filter(pressure__gte=pressure_min)
    if pressure_max:
        qs = qs.filter(pressure__lte=pressure_max)

    # ---- options for the filter UI ----
    species_options = Species.objects.all().order_by("name")
    camera_options = []
    try:
        camera_options = Camera.objects.all().order_by("name")
    except Exception:
        # If you don't have Camera model yet, ignore
        camera_options = []

    context = {
        "photos": qs,
        "species_options": species_options,
        "camera_options": camera_options,

        # echo current selections back to template
        "selected_species_ids": list(map(str, species_ids)),
        "selected_camera_id": camera_id,
        "start_date": start_date,
        "end_date": end_date,
        "temp_min": temp_min,
        "temp_max": temp_max,
        "pressure_min": pressure_min,
        "pressure_max": pressure_max,
    }
    return render(request, "wildlife/gallery.html", context)


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
    # Only allow researchers to upload
    if not getattr(request.user, "is_researcher", False):
        return HttpResponseForbidden("Only researchers can upload photos.")

    error = None

    if request.method == "POST":
        files = request.FILES.getlist("images")  # MUST match input name="images"

        print("DEBUG: POST received. FILES keys:", list(request.FILES.keys()))
        print("DEBUG: Number of files in 'images':", len(files))

        if not files:
            error = "No files received. Please drag and drop or choose images before uploading."
        else:
            for f in files:
                Photo.objects.create(
                    image=f,
                    uploaded_by=request.user,
                    uploaded_at=timezone.now(),
                )
            return redirect("wildlife:gallery")

    return render(request, "wildlife/upload.html", {"error": error})


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
