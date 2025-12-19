from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

import csv

from .forms import PhotoUploadForm, PhotoEditForm
from .models import Photo, Species
from .utils.utils import require_researcher
from django.http import HttpResponse, HttpResponseForbidden

from django.db.models import Q
from django.shortcuts import render
from .models import Photo, Species, Camera

from wildlife.utils.ocr import crop_bottom_strip, extract_overlay_meta
import pytesseract
from PIL import Image
import os
from django.conf import settings
from django.http import JsonResponse
from datetime import datetime
# Create your views here.

# Home landing page
def index(request):
    return render(request, 'wildlife/index.html')


def gallery(request):
    # Start with published photos only (public gallery)
    qs = Photo.objects.filter(is_published=True).order_by("-uploaded_at")

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

    # Species filter must go through PhotoDetection (related_name="detections")
    if species_ids:
        qs = qs.filter(detections__species_id__in=species_ids).distinct()

    if camera_id:
        qs = qs.filter(camera_id=camera_id)

    if start_date:
        qs = qs.filter(date_taken__gte=start_date)
    if end_date:
        qs = qs.filter(date_taken__lte=end_date)

    if temp_min:
        qs = qs.filter(temperature__gte=temp_min)
    if temp_max:
        qs = qs.filter(temperature__lte=temp_max)

    if pressure_min:
        qs = qs.filter(pressure__gte=pressure_min)
    if pressure_max:
        qs = qs.filter(pressure__lte=pressure_max)

    # ---- options for the filter UI ----
    species_options = Species.objects.all().order_by("name")
    camera_options = Camera.objects.all().order_by("name")

    context = {
        "photos": qs,
        "species_options": species_options,
        "camera_options": camera_options,
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
    if not getattr(request.user, "is_researcher", False):
        return HttpResponseForbidden("Only researchers can upload photos.")

    error = None

    if request.method == "POST":
        files = request.FILES.getlist("images")
        if not files:
            error = "No files received. Please choose images before uploading."
        else:
            for f in files:
                Photo.objects.create(
                    image=f,
                    uploaded_by=request.user,
                )
            return redirect("wildlife:upload_photos")  # stay on upload page

    # Show this user’s latest uploads on the same page
    recent_photos = Photo.objects.filter(is_published=False).order_by("-uploaded_at")[:50]

    return render(request, "wildlife/upload.html", {
        "error": error,
        "recent_photos": recent_photos,
        "camera_options": Camera.objects.all().order_by("name"),
    })

@login_required
@require_POST
def analyze_photo(request, pk):
    """Process a photo to extract metadata and run animal classification"""
    require_researcher(request.user)

    photo = get_object_or_404(Photo, pk=pk)
    
    try:
        img = Image.open(photo.image.path)
        # strip = crop_bottom_strip(img, pct=0.05).convert("L")
        strip = crop_bottom_strip(img, pct=0.042).convert("L")

        text = pytesseract.image_to_string(strip)
        print("OCR TEXT >>>", repr(text))

        # upscale to help OCR
        scale = 3
        strip = strip.resize((strip.width * scale, strip.height * scale))

        # binarize (white text on black bar)
        strip = strip.point(lambda p: 255 if p > 140 else 0)

        config = "--oem 1 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/:.AMPMCHGinHg "

        w, h = strip.size

        # Split into regions: left (temp/pressure), center (camera), right (date/time)
        left   = strip.crop((0, 0, int(w * 0.40), h))
        center = strip.crop((int(w * 0.35), 0, int(w * 0.75), h))
        right  = strip.crop((int(w * 0.70), 0, w, h))

        t_left   = pytesseract.image_to_string(left, config=config)
        t_center = pytesseract.image_to_string(center, config=config)
        t_right  = pytesseract.image_to_string(right, config=config)

        text = f"{t_left}\n{t_center}\n{t_right}"

        print("OCR LEFT >>>", repr(t_left))
        print("OCR CENTER >>>", repr(t_center))
        print("OCR RIGHT >>>", repr(t_right))
        print("OCR ALL >>>", repr(text))

    except Exception as e:
        print("OCR ERROR:", e)
        return HttpResponseForbidden("OCR failed. Is Tesseract installed?")
    

    # extract metadata
    data = extract_overlay_meta(text)

    # set camera
    if data.camera_name and photo.camera is None:
        # only assing if camera exists
        cam = Camera.objects.filter(name=data.camera_name).first()
        if cam:
            photo.camera = cam


    # set other meta data
    if data.date_taken:
        photo.date_taken = data.date_taken
    if data.time_taken:
        photo.time_taken = data.time_taken
    if data.temperature_c is not None:
        photo.temperature = data.temperature_c
    if data.pressure_inhg is not None:
        photo.pressure = data.pressure_inhg

    print("PARSED >>>",
      "camera=", getattr(data, "camera_name", None),
      "date=", getattr(data, "date_taken", None),
      "time=", getattr(data, "time_taken", None),
      "temp=", getattr(data, "temperature_c", None),
      "press=", getattr(data, "pressure_inhg", None))

    # save updates
    photo.save()
    return redirect("wildlife:upload_photos")


@login_required
@require_POST
def publish_photo(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)
    
    # require analysis before publishing
    if photo.date_taken is None or photo.time_taken is None or photo.temperature is None or photo.pressure is None:
        return HttpResponseForbidden("Photo must be analyzed before publishing.")
    photo.is_published = True

    photo.is_published = True
    photo.save()
    return redirect("wildlife:upload_photos")

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
@require_POST
def delete_photo_staging(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)

    if photo.is_published:
        return HttpResponseForbidden("Cannot delete published photos. Unpublish first.")
    
    # deleting file form os
    if photo.image and os.path.isfile(photo.image.path):
        os.remove(photo.image.path)

    photo.delete()
    return redirect("wildlife:upload_photos")

@login_required
@require_POST
def unpublish_photo(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)

    if not photo.is_published:
        return HttpResponseForbidden("Photo is alread unpublished.")
    
    photo.is_published = False
    photo.save()

    return redirect("wildlife:gallery")


@login_required
@require_POST
def update_photo_meta(request, pk):
    require_researcher(request.user)

    photo = get_object_or_404(Photo, pk=pk)

    # Only editable in staging
    if photo.is_published:
        return JsonResponse({"ok": False, "error": "Cannot edit published photos. Unpublish first."}, status=403)

    # Read fields (sent via fetch form-encoded)
    camera_name = (request.POST.get("camera_name") or "").strip().upper()
    date_taken  = (request.POST.get("date_taken") or "").strip()
    time_taken  = (request.POST.get("time_taken") or "").strip()
    temperature = (request.POST.get("temperature") or "").strip()
    pressure    = (request.POST.get("pressure") or "").strip()

    errors = {}

    # ---- camera ----
    if camera_name:
        # normalize TRAILCAM5 -> TRAILCAM05
        m = re.match(r"^TRAILCAM0*(\d{1,3})$", camera_name)
        if not m:
            errors["camera_name"] = "Camera must look like TRAILCAM05"
        else:
            n = int(m.group(1))
            normalized = f"TRAILCAM{n:02d}"
            cam = Camera.objects.filter(name=normalized).first()
            if not cam:
                errors["camera_name"] = f"Camera '{normalized}' not found. Create it first."
            else:
                photo.camera = cam

    # ---- date ----
    if date_taken:
        try:
            # expecting YYYY-MM-DD from <input type="date">
            photo.date_taken = datetime.strptime(date_taken, "%Y-%m-%d").date()
        except ValueError:
            errors["date_taken"] = "Date must be YYYY-MM-DD"

    # ---- time ----
    if time_taken:
        try:
            # expecting HH:MM from <input type="time">
            photo.time_taken = datetime.strptime(time_taken, "%H:%M").time()
        except ValueError:
            errors["time_taken"] = "Time must be HH:MM (24-hour)"

    # ---- temperature ----
    if temperature:
        try:
            temp_val = float(temperature)
            if temp_val < -60 or temp_val > 80:
                errors["temperature"] = "Temperature looks out of range (-60 to 80°C)"
            else:
                photo.temperature = temp_val
        except ValueError:
            errors["temperature"] = "Temperature must be a number"

    # ---- pressure ----
    if pressure:
        try:
            press_val = float(pressure)
            if press_val < 20 or press_val > 35:
                errors["pressure"] = "Pressure looks out of range (20 to 35 inHg)"
            else:
                photo.pressure = press_val
        except ValueError:
            errors["pressure"] = "Pressure must be a number"

    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)

    photo.save()

    # Return updated values so UI can refresh nicely
    return JsonResponse({
        "ok": True,
        "photo": {
            "id": photo.id,
            "camera_name": photo.camera.name if photo.camera else "",
            "date_taken": photo.date_taken.isoformat() if photo.date_taken else "",
            "time_taken": photo.time_taken.strftime("%H:%M") if photo.time_taken else "",
            "temperature": str(photo.temperature) if photo.temperature is not None else "",
            "pressure": str(photo.pressure) if photo.pressure is not None else "",
        }
    })

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
