from __future__ import annotations

import os
import re
import csv
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import (
    HttpResponse,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.conf import settings
from django.core.files import File

from PIL import Image
import pytesseract

from .models import Photo, PhotoDetection, Species, Camera
from .forms import PhotoEditForm, CameraForm
from .utils.utils import require_researcher
from wildlife.utils.ocr import crop_bottom_strip, extract_overlay_meta_split

from .services.speciesnet import run_speciesnet_on_image, save_speciesnet_results
# ============================================================
# Public pages
# ============================================================

def index(request):
    return render(request, "wildlife/index.html")


def gallery(request):
    qs = Photo.objects.filter(is_published=True).order_by("-uploaded_at")

    species_ids = request.GET.getlist("species")
    camera_id = (request.GET.get("camera") or "").strip()

    start_date = (request.GET.get("start_date") or "").strip()
    end_date = (request.GET.get("end_date") or "").strip()

    temp_min = (request.GET.get("temp_min") or "").strip()
    temp_max = (request.GET.get("temp_max") or "").strip()

    pressure_min = (request.GET.get("pressure_min") or "").strip()
    pressure_max = (request.GET.get("pressure_max") or "").strip()

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

    context = {
        "photos": qs,
        "species_options": Species.objects.all().order_by("name"),
        "camera_options": Camera.objects.all().order_by("name"),
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

    # Build a disabled form so we can reuse `photo_form.html` styling in read-only mode
    form = PhotoEditForm(instance=photo)
    for name, field in form.fields.items():
        field.widget.attrs["disabled"] = "disabled"

    # Only show detections marked as visible
    detections = photo.detections.filter(is_shown=True)
    num_animals = detections.filter(category="1").count()
    num_people = detections.filter(category="2").count()
    num_vehicles = detections.filter(category="3").count()

    detection_species_names = []
    for det in detections:
        if det.species and det.species.name:
            detection_species_names.append(det.species.name)

    detection_boxes = []
    if photo.image and detections.exists():
        for det in detections:
            left_pct = (det.x or 0) * 100
            top_pct = (det.y or 0) * 100
            width_pct = (det.w or 0) * 100
            height_pct = (det.h or 0) * 100
            detection_boxes.append({
                "id": det.id,
                "left": left_pct,
                "top": top_pct,
                "width": width_pct,
                "height": height_pct,
                "label": det.get_category_display() if det.category else "Unknown",
                "species_name": det.species.name if det.species and det.species.name else None,
                "confidence": det.confidence,
                "bbox_tuple": (left_pct, top_pct, width_pct, height_pct),
            })

    is_researcher = request.user.is_authenticated and getattr(request.user, "is_researcher", False)
    can_unpublish = is_researcher and photo.is_published

    context = {
        "form": form,
        "photo": photo,
        "num_animals": num_animals,
        "num_people": num_people,
        "num_vehicles": num_vehicles,
        "has_detections": detections.exists(),
        "detection_species_names": sorted(set(detection_species_names)),
        "detection_boxes": detection_boxes,
        "read_only": True,
        "can_unpublish": can_unpublish,
    }

    return render(request, "wildlife/photo_form.html", context)


# ============================================================
# Researcher pages
# ============================================================

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
            # Ensure speciesnet_inbox directory exists
            inbox_path = Path(settings.SPECIESNET_INBOX_ROOT)
            inbox_path.mkdir(parents=True, exist_ok=True)
            
            trailcam_path = Path(settings.MEDIA_ROOT) / "trailcam"
            trailcam_path.mkdir(parents=True, exist_ok=True)
            
            # Process each uploaded file
            for uploaded_file in files:
                try:
                    # 1. Save to speciesnet_inbox temporarily
                    inbox_file_path = inbox_path / uploaded_file.name
                    with open(inbox_file_path, 'wb+') as destination:
                        for chunk in uploaded_file.chunks():
                            destination.write(chunk)
                    
                    # 2. Run OCR to extract metadata
                    ocr_data = None
                    try:
                        img = Image.open(inbox_file_path)
                        strip = crop_bottom_strip(img, pct=0.042).convert("L")
                        
                        # upscale to help OCR
                        scale = 3
                        strip = strip.resize((strip.width * scale, strip.height * scale))
                        
                        # binarize (white text on black bar)
                        strip = strip.point(lambda p: 255 if p > 140 else 0)
                        
                        w, h = strip.size
                        left   = strip.crop((0, 0, int(w * 0.40), h))
                        center = strip.crop((int(w * 0.35), 0, int(w * 0.75), h))
                        right  = strip.crop((int(w * 0.70), 0, w, h))
                        
                        config = "--oem 1 --psm 7"
                        t_left   = pytesseract.image_to_string(left, config=config)
                        t_center = pytesseract.image_to_string(center, config=config)
                        t_right  = pytesseract.image_to_string(right, config=config)
                        
                        ocr_data = extract_overlay_meta_split(t_left, t_center, t_right)
                    except Exception as e:
                        print(f"OCR warning for {uploaded_file.name}: {e}")
                    
                    # 3. Run SpeciesNet
                    speciesnet_result = run_speciesnet_on_image(inbox_file_path)
                    
                    # 4. Move file to trailcam folder
                    final_file_path = trailcam_path / uploaded_file.name
                    # Handle name collisions
                    counter = 1
                    while final_file_path.exists():
                        stem = Path(uploaded_file.name).stem
                        suffix = Path(uploaded_file.name).suffix
                        final_file_path = trailcam_path / f"{stem}_{counter}{suffix}"
                        counter += 1
                    
                    shutil.move(str(inbox_file_path), str(final_file_path))
                    
                    # 5. Create Photo object with metadata
                    relative_path = f"trailcam/{final_file_path.name}"
                    photo = Photo(
                        image=relative_path,
                        uploaded_by=request.user,
                        is_published=False
                    )
                    
                    # Apply OCR metadata if available
                    if ocr_data:
                        if ocr_data.camera_name:
                            cam = Camera.objects.filter(name=ocr_data.camera_name).first()
                            if cam:
                                photo.camera = cam
                                photo.latitude = cam.base_latitude
                                photo.longitude = cam.base_longitude
                        
                        if ocr_data.date_taken:
                            photo.date_taken = ocr_data.date_taken
                        if ocr_data.time_taken:
                            photo.time_taken = ocr_data.time_taken
                        if ocr_data.temperature_c is not None:
                            photo.temperature = ocr_data.temperature_c
                        if ocr_data.pressure_inhg is not None:
                            photo.pressure = ocr_data.pressure_inhg
                    
                    photo.save()
                    
                    # 6. Save SpeciesNet detection results
                    save_speciesnet_results(photo, speciesnet_result)
                    
                except Exception as e:
                    print(f"Error processing {uploaded_file.name}: {e}")
                    error = f"Error processing some files: {e}"
                    # Clean up inbox file if it still exists
                    try:
                        if inbox_file_path.exists():
                            inbox_file_path.unlink()
                    except:
                        pass
            
            if not error:
                return redirect("wildlife:upload_photos")

    recent_photos = Photo.objects.filter(is_published=False).order_by("-uploaded_at")[:50]

    return render(request, "wildlife/upload.html", {
        "error": error,
        "recent_photos": recent_photos,
        "camera_names": list(
            Camera.objects.filter(is_active=True)
            .order_by("name")
            .values_list("name", flat=True)
        ),
    })


# ============================================================
# Photo actions (staging)
# ============================================================

@login_required
@require_POST
def analyze_photo(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)

    # 1) Run OCR pipeline
    try:
        img = Image.open(photo.image.path)
        strip = crop_bottom_strip(img, pct=0.042).convert("L")

        # upscale to help OCR
        scale = 3
        strip = strip.resize((strip.width * scale, strip.height * scale))

        # binarize (white text on black bar)
        strip = strip.point(lambda p: 255 if p > 140 else 0)

        config = "--oem 1 --psm 7"

        w, h = strip.size
        left   = strip.crop((0, 0, int(w * 0.40), h))                 # temp/pressure
        center = strip.crop((int(w * 0.35), 0, int(w * 0.75), h))      # camera
        right  = strip.crop((int(w * 0.70), 0, w, h))                  # date/time

        t_left   = pytesseract.image_to_string(left, config=config)
        t_center = pytesseract.image_to_string(center, config=config)
        t_right  = pytesseract.image_to_string(right, config=config)

    except Exception as e:
        print("OCR ERROR:", e)
        return HttpResponseForbidden("OCR failed. Is Tesseract installed?")

    data = extract_overlay_meta_split(t_left, t_center, t_right)

    # set camera if exists
    if data.camera_name:
        cam = Camera.objects.filter(name=data.camera_name).first()
        if cam:
            photo.camera = cam
            # Also update lat/long from camera if not set
            if photo.latitude is None:
                photo.latitude = cam.base_latitude
            if photo.longitude is None:
                photo.longitude = cam.base_longitude

    if data.date_taken:
        photo.date_taken = data.date_taken
    if data.time_taken:
        photo.time_taken = data.time_taken
    if data.temperature_c is not None:
        photo.temperature = data.temperature_c
    if data.pressure_inhg is not None:
        photo.pressure = data.pressure_inhg

    photo.save()

    # 2) Run SpeciesNet
    try:
        result = run_speciesnet_on_image(Path(photo.image.path))
        save_speciesnet_results(photo, result)
    except Exception as e:
        print("SpeciesNet ERROR:", e)
    # After analyzing, show the edited photo page so the user can review/adjust fields
    return redirect("wildlife:photo_edit", pk=pk)


@login_required
@require_POST
def publish_photo(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)


    if photo.date_taken is None or photo.time_taken is None or photo.temperature is None or photo.pressure is None:
        return HttpResponseForbidden("Photo must be analyzed before publishing.")

    photo.is_published = True
    photo.save()
    return redirect("wildlife:upload_photos")


@login_required
@require_POST
def delete_photo_staging(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)

    if photo.is_published:
        return HttpResponseForbidden("Cannot delete published photos. Unpublish first.")

    # Locking removed — allow the current user to delete unpublished photos.

    if photo.image and os.path.isfile(photo.image.path):
        os.remove(photo.image.path)

    photo.delete()
    return redirect("wildlife:upload_photos")


@login_required
@require_POST
def update_photo_meta(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)
    # Page-based edit moved to `photo_edit` view. This JSON endpoint is removed.
    return JsonResponse({"ok": False, "error": "Endpoint removed. Use page-based editor."}, status=410)


@login_required
@require_POST
def update_detection_species(request, pk):
    """Update the species name and visibility for a detection."""
    require_researcher(request.user)
    detection = get_object_or_404(PhotoDetection, pk=pk)
    
    # Update species name if provided
    if "species_name" in request.POST:
        species_name = request.POST.get("species_name", "").strip()
        if species_name:
            from wildlife.services.speciesnet import get_or_create_species
            species = get_or_create_species(species_name)
            detection.species = species
        else:
            detection.species = None
    
    # Update visibility if provided
    if "is_shown" in request.POST:
        is_shown = request.POST.get("is_shown") == "true"
        detection.is_shown = is_shown
    
    detection.save()
    
    return JsonResponse({
        "success": True,
        "species_name": detection.species.name if detection.species else None,
        "is_shown": detection.is_shown
    })


@login_required
@require_POST
def unpublish_photo(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)

    if not photo.is_published:
        return HttpResponseForbidden("Photo is already unpublished.")

    photo.is_published = False
    photo.save()
    return redirect("wildlife:gallery")


def photo_card_detail(request, pk):
    """Lightweight page showing the same info as a gallery card.
    Non-researchers can view this page; researchers see an Unpublish button when applicable.
    """
    photo = get_object_or_404(Photo, pk=pk)

    detections = photo.detections.all()
    is_researcher = request.user.is_authenticated and getattr(request.user, "is_researcher", False)
    can_unpublish = is_researcher and photo.is_published

    context = {
        "photo": photo,
        "can_unpublish": can_unpublish,
        "detections": detections,
    }

    return render(request, "wildlife/photo_card_detail.html", context)

# ============================================================
# Export
# ============================================================

@login_required
def export_photos_csv(request):
    require_researcher(request.user)

    photos = Photo.objects.all()

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="trailcam_photos.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "id", "date_taken", "time_taken", "temperature", "pressure",
        "camera", "latitude", "longitude", "uploaded_by", "uploaded_at",
    ])

    for p in photos:
        writer.writerow([
            p.id,
            p.date_taken.isoformat() if p.date_taken else "",
            p.time_taken.strftime("%H:%M:%S") if p.time_taken else "",
            str(p.temperature) if p.temperature is not None else "",
            str(p.pressure) if p.pressure is not None else "",
            p.camera.name if p.camera else "",
            str(p.latitude) if p.latitude is not None else "",
            str(p.longitude) if p.longitude is not None else "",
            p.uploaded_by.username if p.uploaded_by else "",
            p.uploaded_at.isoformat(),
        ])

    return response


# ============================================================
# Cameras CRUD (modal JSON)
# ============================================================

@login_required
def cameras_list(request):
    require_researcher(request.user)

    q = (request.GET.get("q") or "").strip()
    qs = Camera.objects.all().order_by("name")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))

    return render(request, "wildlife/camera_list.html", {
        "cameras": qs,
        "search_query": q,
    })


@login_required
def camera_new(request):
    """Page-based create view for Camera (replaces modal flow)."""
    require_researcher(request.user)

    if request.method == "POST":
        form = CameraForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("wildlife:cameras_list")
    else:
        form = CameraForm()

    return render(request, "wildlife/camera_form.html", {"form": form, "mode": "create"})


@login_required
def camera_edit(request, pk):
    """Page-based edit view for Camera (no locking)."""
    require_researcher(request.user)
    cam = get_object_or_404(Camera, pk=pk)

    if request.method == "POST":
        form = CameraForm(request.POST, instance=cam)
        if form.is_valid():
            form.save()
            return redirect("wildlife:cameras_list")
    else:
        form = CameraForm(instance=cam)

    return render(request, "wildlife/camera_form.html", {"form": form, "mode": "edit", "camera": cam})


CAMERA_NAME_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_]{1,63}$")

def _validate_camera_payload(data):
    errors = {}
    cleaned = {}

    name = (data.get("name") or "").strip().upper()
    if not name:
        errors["name"] = "Camera name is required."
    elif not CAMERA_NAME_RE.match(name):
        errors["name"] = "Use only letters/numbers and - or _. Example: TRAILCAM05"
    cleaned["name"] = name

    def parse_decimal(field, min_v, max_v, label):
        raw = (data.get(field) or "").strip()
        if raw == "":
            errors[field] = f"{label} is required."
            return None
        try:
            val = Decimal(raw)
        except (InvalidOperation, ValueError):
            errors[field] = f"{label} must be a number."
            return None
        if val < Decimal(str(min_v)) or val > Decimal(str(max_v)):
            errors[field] = f"{label} must be between {min_v} and {max_v}."
            return None
        return val

    lat = parse_decimal("base_latitude", -90, 90, "Latitude")
    lon = parse_decimal("base_longitude", -180, 180, "Longitude")
    if lat is not None:
        cleaned["base_latitude"] = lat
    if lon is not None:
        cleaned["base_longitude"] = lon

    desc = (data.get("description") or "").strip()
    if len(desc) > 255:
        errors["description"] = "Description must be 255 characters or fewer."
    cleaned["description"] = desc

    is_active_raw = (data.get("is_active") or "").strip().lower()
    cleaned["is_active"] = (is_active_raw in ("1", "true", "on", "yes"))

    return cleaned, errors


@login_required
@require_POST
def camera_create(request):
    require_researcher(request.user)
    # Endpoint removed: use page-based `camera_new` view instead.
    return JsonResponse({"ok": False, "error": "Endpoint removed. Use page-based editor."}, status=410)


@login_required
@require_POST
def camera_update(request, pk):
    require_researcher(request.user)
    cam = get_object_or_404(Camera, pk=pk)
    # Endpoint removed: use page-based `camera_edit` view instead.
    return JsonResponse({"ok": False, "error": "Endpoint removed. Use page-based editor."}, status=410)


# ============================================================
# Lock endpoints (Photo + Camera)
# IMPORTANT: These assume you added fields on BOTH models:
#   opened_by = FK(User, null=True, blank=True, on_delete=SET_NULL)
#   opened_at = DateTimeField(null=True, blank=True)
# ============================================================

# Lock endpoints removed — locking has been disabled in favor of simple page-based editing.


@login_required
def photo_edit(request, pk):
    """Page-based editor for a staging photo (no locking)."""
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)

    if photo.is_published:
        return HttpResponseForbidden("Cannot edit published photos.")

    if request.method == "POST":
        form = PhotoEditForm(request.POST, instance=photo)
        if form.is_valid():
            form.save()
            return redirect("wildlife:upload_photos")
    else:
        form = PhotoEditForm(instance=photo)

    # ---- detection summary ----
    # Researchers see all detections (including hidden ones) so they can toggle them
    detections = photo.detections.all()
    num_animals = detections.filter(category="1").count()
    num_people = detections.filter(category="2").count()
    num_vehicles = detections.filter(category="3").count()

    detection_species_names = []
    for det in detections:
        if det.species and det.species.name:
            detection_species_names.append(det.species.name)

    # ---- bounding boxes (percent coords) ----
    # Store boxes as percentages so they scale with the displayed image size
    detection_boxes = []
    if photo.image and detections.exists():
        for det in detections:
            # det.x, det.y, det.w, det.h are normalized (0..1)
            left_pct = (det.x or 0) * 100
            top_pct = (det.y or 0) * 100
            width_pct = (det.w or 0) * 100
            height_pct = (det.h or 0) * 100

            detection_boxes.append({
                "id": det.id,
                "left": left_pct,
                "top": top_pct,
                "width": width_pct,
                "height": height_pct,
                "label": det.get_category_display() if det.category else "Unknown",
                "species_name": det.species.name if det.species and det.species.name else None,
                "confidence": det.confidence,
                "bbox_tuple": (left_pct, top_pct, width_pct, height_pct),
                "is_shown": det.is_shown,
            })

    context = {
        "form": form,
        "photo": photo,
        "num_animals": num_animals,
        "num_people": num_people,
        "num_vehicles": num_vehicles,
        "has_detections": detections.exists(),
        "detection_species_names": sorted(set(detection_species_names)),
        "detection_boxes": detection_boxes,
    }

    return render(request, "wildlife/photo_form.html", context)


# Lock endpoints removed — camera open/close no longer used.
