from __future__ import annotations

import os
import re
import csv
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

from PIL import Image
import pytesseract

from .models import Photo, Species, Camera
from .forms import PhotoEditForm
from .utils.utils import require_researcher, _require_my_lock, _lock_status
from wildlife.utils.ocr import crop_bottom_strip, extract_overlay_meta_split


# ============================================================
# Lock helpers (30 second TTL)
# NOTE: You said you have these in utils.py already.
# Keeping them here makes views.py self-contained and avoids bad imports.
# You can move them back to utils later.
# ============================================================

LOCK_TTL = timedelta(seconds=30)

def _lock_is_active(opened_at):
    return bool(opened_at) and (opened_at + LOCK_TTL) > timezone.now()

def _lock_status(obj):
    """
    obj must have:
      - opened_by (User FK nullable)
      - opened_at (DateTime nullable)
    """
    active = bool(getattr(obj, "opened_by_id", None)) and _lock_is_active(getattr(obj, "opened_at", None))
    opened_by = getattr(obj.opened_by, "username", None) if getattr(obj, "opened_by", None) else None
    expires_in = None
    if getattr(obj, "opened_at", None):
        expires_in = max(0, int((obj.opened_at + LOCK_TTL - timezone.now()).total_seconds()))
    return {
        "active": active,
        "opened_by": opened_by,
        "expires_in": expires_in,
    }

def _require_my_lock_or_403(obj, user):
    """
    Enforce staging-only locking:
    - If the object is "published" (Photo), do not enforce.
    - If lock is active and owned by someone else => forbid.
    - If lock is missing/expired => forbid (forces proper open->edit flow)
    """
    # Only photos have is_published; cameras always enforce lock.
    if hasattr(obj, "is_published") and obj.is_published:
        return True

    if not getattr(obj, "opened_by_id", None) or not _lock_is_active(getattr(obj, "opened_at", None)):
        return False

    return obj.opened_by_id == user.id


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
    return render(request, "wildlife/photo_detail.html", {"photo": photo})


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
            for f in files:
                Photo.objects.create(image=f, uploaded_by=request.user)
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

    # lock enforcement (staging only)
    if not _require_my_lock_or_403(photo, request.user):
        return HttpResponseForbidden("Photo is opened by another user.")

    try:
        img = Image.open(photo.image.path)
        strip = crop_bottom_strip(img, pct=0.042).convert("L")

        # upscale to help OCR
        scale = 3
        strip = strip.resize((strip.width * scale, strip.height * scale))

        # binarize (white text on black bar)
        strip = strip.point(lambda p: 255 if p > 140 else 0)

        config = "--oem 1 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/:.AMPMCHGinHg "

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

    if data.date_taken:
        photo.date_taken = data.date_taken
    if data.time_taken:
        photo.time_taken = data.time_taken
    if data.temperature_c is not None:
        photo.temperature = data.temperature_c
    if data.pressure_inhg is not None:
        photo.pressure = data.pressure_inhg

    photo.save()
    return redirect("wildlife:upload_photos")


@login_required
@require_POST
def publish_photo(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)

    # lock enforcement (staging only)
    if not _require_my_lock_or_403(photo, request.user):
        return HttpResponseForbidden("Photo is opened by another user.")

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

    # lock enforcement
    if not _require_my_lock_or_403(photo, request.user):
        return HttpResponseForbidden("Photo is opened by another user.")

    if photo.image and os.path.isfile(photo.image.path):
        os.remove(photo.image.path)

    photo.delete()
    return redirect("wildlife:upload_photos")


@login_required
@require_POST
def update_photo_meta(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)

    # This is called via fetch() in your modal → always return JSON
    if photo.is_published:
        return JsonResponse({"ok": False, "error": "Cannot edit metadata of published photos."}, status=403)

    if not _require_my_lock_or_403(photo, request.user):
        return JsonResponse({"ok": False, "error": "Photo is opened by another user."}, status=409)

    camera_name = (request.POST.get("camera_name") or "").strip().upper()
    date_taken  = (request.POST.get("date_taken") or "").strip()
    time_taken  = (request.POST.get("time_taken") or "").strip()
    temperature = (request.POST.get("temperature") or "").strip()
    pressure    = (request.POST.get("pressure") or "").strip()

    errors = {}

    # ---- camera ----
    if camera_name:
        m = re.match(r"^TRAILCAM0*(\d{1,3})$", camera_name)
        if not m:
            errors["camera_name"] = "Camera must look like TRAILCAM05"
        else:
            n = int(m.group(1))
            normalized = f"TRAILCAM{n:02d}" if n < 100 else f"TRAILCAM{n}"
            cam = Camera.objects.filter(name=normalized).first()
            if not cam:
                errors["camera_name"] = f"Camera '{normalized}' not found. Create it first."
            else:
                photo.camera = cam

    # ---- date ----
    if date_taken:
        try:
            photo.date_taken = datetime.strptime(date_taken, "%Y-%m-%d").date()
        except ValueError:
            errors["date_taken"] = "Date must be YYYY-MM-DD"

    # ---- time ----
    if time_taken:
        try:
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
@require_POST
def unpublish_photo(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)

    if not photo.is_published:
        return HttpResponseForbidden("Photo is already unpublished.")

    photo.is_published = False
    photo.save()
    return redirect("wildlife:gallery")


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

    cleaned, errors = _validate_camera_payload(request.POST)
    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)

    if Camera.objects.filter(name=cleaned["name"]).exists():
        return JsonResponse({"ok": False, "errors": {"name": "That camera name already exists."}}, status=400)

    cam = Camera.objects.create(**cleaned)
    return JsonResponse({"ok": True, "camera": {
        "id": cam.id,
        "name": cam.name,
        "base_latitude": str(cam.base_latitude),
        "base_longitude": str(cam.base_longitude),
        "description": cam.description or "",
        "is_active": cam.is_active,
    }})


@login_required
@require_POST
def camera_update(request, pk):
    require_researcher(request.user)
    cam = get_object_or_404(Camera, pk=pk)

    # ENFORCE LOCK
    if not _require_my_lock(cam, request.user):
        lock = _lock_status(cam)
        lock["is_mine"] = (cam.opened_by_id == request.user.id) and lock["active"]
        return JsonResponse(
            {"ok": False, "error": f"Camera is opened by {lock['opened_by'] or 'another user'}", "lock": lock},
            status=409
        )

    cleaned, errors = _validate_camera_payload(request.POST)
    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)

    if Camera.objects.filter(name=cleaned["name"]).exclude(pk=cam.pk).exists():
        return JsonResponse({"ok": False, "errors": {"name": "That camera name already exists."}}, status=400)

    cam.name = cleaned["name"]
    cam.base_latitude = cleaned["base_latitude"]
    cam.base_longitude = cleaned["base_longitude"]
    cam.description = cleaned["description"]
    cam.is_active = cleaned["is_active"]
    cam.save()

    return JsonResponse({"ok": True, "camera": {
        "id": cam.id,
        "name": cam.name,
        "base_latitude": str(cam.base_latitude),
        "base_longitude": str(cam.base_longitude),
        "description": cam.description or "",
        "is_active": cam.is_active,
    }})


# ============================================================
# Lock endpoints (Photo + Camera)
# IMPORTANT: These assume you added fields on BOTH models:
#   opened_by = FK(User, null=True, blank=True, on_delete=SET_NULL)
#   opened_at = DateTimeField(null=True, blank=True)
# ============================================================

@login_required
@require_POST
def photo_open(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)

    # Only lock staging photos
    if photo.is_published:
        return JsonResponse({"ok": True, "lock": {"active": False}})

    with transaction.atomic():
        photo = Photo.objects.select_for_update().get(pk=pk)

        # locked by someone else and still active
        if photo.opened_by_id and _lock_is_active(photo.opened_at) and photo.opened_by_id != request.user.id:
            lock = _lock_status(photo)
            lock["is_mine"] = False
            return JsonResponse({"ok": False, "lock": lock}, status=409)

        # acquire/refresh
        photo.opened_by = request.user
        photo.opened_at = timezone.now()
        photo.save(update_fields=["opened_by", "opened_at"])

    lock = _lock_status(photo)
    lock["is_mine"] = True
    return JsonResponse({"ok": True, "lock": lock})


@login_required
@require_POST
def photo_close(request, pk):
    require_researcher(request.user)
    photo = get_object_or_404(Photo, pk=pk)

    if photo.is_published:
        return JsonResponse({"ok": True})

    with transaction.atomic():
        photo = Photo.objects.select_for_update().get(pk=pk)
        if photo.opened_by_id == request.user.id:
            photo.opened_by = None
            photo.opened_at = None
            photo.save(update_fields=["opened_by", "opened_at"])

    return JsonResponse({"ok": True})


@login_required
@require_POST
def camera_open(request, pk):
    require_researcher(request.user)
    cam = get_object_or_404(Camera, pk=pk)

    with transaction.atomic():
        cam = Camera.objects.select_for_update().get(pk=pk)

        if cam.opened_by_id and _lock_is_active(cam.opened_at) and cam.opened_by_id != request.user.id:
            lock = _lock_status(cam)
            lock["is_mine"] = False
            return JsonResponse({"ok": False, "lock": lock}, status=409)

        cam.opened_by = request.user
        cam.opened_at = timezone.now()
        cam.save(update_fields=["opened_by", "opened_at"])

    lock = _lock_status(cam)
    lock["is_mine"] = True
    return JsonResponse({"ok": True, "lock": lock})


@login_required
@require_POST
def camera_close(request, pk):
    require_researcher(request.user)
    cam = get_object_or_404(Camera, pk=pk)

    with transaction.atomic():
        cam = Camera.objects.select_for_update().get(pk=pk)
        if cam.opened_by_id == request.user.id:
            cam.opened_by = None
            cam.opened_at = None
            cam.save(update_fields=["opened_by", "opened_at"])

    return JsonResponse({"ok": True})
