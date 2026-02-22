from __future__ import annotations

import os
import re
import csv
import shutil
import json
import random
from io import StringIO
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

from PIL import Image, ImageDraw
import pytesseract

from .models import Photo, PhotoDetection, Species, Camera, OcrMask
from .forms import PhotoEditForm, CameraForm
from .utils.utils import require_researcher
from wildlife.utils.ocr import crop_bottom_strip, extract_overlay_meta_split


def _clamp(v: float, min_v: float = 0.0, max_v: float = 1.0) -> float:
    return max(min_v, min(max_v, v))


def _crop_norm(img: Image.Image, x: float, y: float, w: float, h: float) -> Image.Image:
    width, height = img.size
    left = int(_clamp(x) * width)
    top = int(_clamp(y) * height)
    right = int(_clamp(x + w) * width)
    bottom = int(_clamp(y + h) * height)
    # Ensure non-zero box and within bounds
    right = max(right, left + 1)
    bottom = max(bottom, top + 1)
    right = min(right, width)
    bottom = min(bottom, height)
    return img.crop((left, top, right, bottom))


def _ocr_text_from_region(region: Image.Image) -> str:
    gray = region.convert("L")
    scale = 3
    gray = gray.resize((gray.width * scale, gray.height * scale))
    gray = gray.point(lambda p: 255 if p > 140 else 0)
    config = "--oem 1 --psm 7"
    return pytesseract.image_to_string(gray, config=config)


def _extract_overlay_meta(img: Image.Image, mask: OcrMask | None):
    """Run OCR using either a saved mask or the default strip split."""
    if mask:
        temperature = _crop_norm(img, float(mask.temperature_x), float(mask.temperature_y), float(mask.temperature_w), float(mask.temperature_h))
        pressure = _crop_norm(img, float(mask.pressure_x), float(mask.pressure_y), float(mask.pressure_w), float(mask.pressure_h))
        camera = _crop_norm(img, float(mask.camera_x), float(mask.camera_y), float(mask.camera_w), float(mask.camera_h))
        date = _crop_norm(img, float(mask.date_x), float(mask.date_y), float(mask.date_w), float(mask.date_h))
        time = _crop_norm(img, float(mask.time_x), float(mask.time_y), float(mask.time_w), float(mask.time_h))

        t_temperature = _ocr_text_from_region(temperature)
        t_pressure = _ocr_text_from_region(pressure)
        t_camera = _ocr_text_from_region(camera)
        t_date = _ocr_text_from_region(date)
        t_time = _ocr_text_from_region(time)

        # Combine temperature + pressure into left region, date + time into right region for compatibility
        t_left = f"{t_temperature} {t_pressure}"
        t_center = t_camera
        t_right = f"{t_date} {t_time}"
        return extract_overlay_meta_split(t_left, t_center, t_right)

    # Default behavior (bottom strip split)
    strip = crop_bottom_strip(img, pct=0.042).convert("L")
    scale = 3
    strip = strip.resize((strip.width * scale, strip.height * scale))
    strip = strip.point(lambda p: 255 if p > 140 else 0)

    w, h = strip.size
    left = strip.crop((0, 0, int(w * 0.40), h))
    center = strip.crop((int(w * 0.35), 0, int(w * 0.75), h))
    right = strip.crop((int(w * 0.70), 0, w, h))

    config = "--oem 1 --psm 7"
    t_left = pytesseract.image_to_string(left, config=config)
    t_center = pytesseract.image_to_string(center, config=config)
    t_right = pytesseract.image_to_string(right, config=config)
    return extract_overlay_meta_split(t_left, t_center, t_right)

from .services.speciesnet import run_speciesnet_on_image, save_speciesnet_results
# ============================================================
# Public pages
# ============================================================

def index(request):
    return render(request, "wildlife/index.html")


def search_species(request):
    """
    Search for species by partial name match.
    Returns a JSON list of species names matching the query.
    Used for autocomplete suggestions in the detection editor.
    """
    query = request.GET.get("q", "").strip().lower()
    
    if not query or len(query) < 1:
        return JsonResponse({"species": []})
    
    # Find species names that contain the query (case-insensitive)
    matching_species = Species.objects.filter(
        name__icontains=query
    ).values_list("name", flat=True).order_by("name")[:10]
    
    return JsonResponse({
        "species": list(matching_species)
    })


def index(request):
    return render(request, "wildlife/index.html")


def _build_gallery_filters(request):
    """
    Extract filter params from the request so we can reuse them for HTML
    rendering and exporting without duplicating logic.
    """
    return {
        "species_ids": request.GET.getlist("species"),
        "camera_id": (request.GET.get("camera") or "").strip(),
        "start_date": (request.GET.get("start_date") or "").strip(),
        "end_date": (request.GET.get("end_date") or "").strip(),
        "temp_min": (request.GET.get("temp_min") or "").strip(),
        "temp_max": (request.GET.get("temp_max") or "").strip(),
        "pressure_min": (request.GET.get("pressure_min") or "").strip(),
        "pressure_max": (request.GET.get("pressure_max") or "").strip(),
    }


def _apply_gallery_filters(filters):
    qs = Photo.objects.filter(is_published=True).order_by("-uploaded_at")

    if filters["species_ids"]:
        qs = qs.filter(detections__species_id__in=filters["species_ids"]).distinct()

    if filters["camera_id"]:
        qs = qs.filter(camera_id=filters["camera_id"])

    if filters["start_date"]:
        qs = qs.filter(date_taken__gte=filters["start_date"])
    if filters["end_date"]:
        qs = qs.filter(date_taken__lte=filters["end_date"])

    if filters["temp_min"]:
        qs = qs.filter(temperature__gte=filters["temp_min"])
    if filters["temp_max"]:
        qs = qs.filter(temperature__lte=filters["temp_max"])

    if filters["pressure_min"]:
        qs = qs.filter(pressure__gte=filters["pressure_min"])
    if filters["pressure_max"]:
        qs = qs.filter(pressure__lte=filters["pressure_max"])

    return qs


def gallery(request):
    filters = _build_gallery_filters(request)
    qs = _apply_gallery_filters(filters)

    # Prefetch detections for each photo to build bounding boxes
    qs = qs.prefetch_related('detections__species')
    
    # Build detection boxes for each photo
    photos_with_boxes = []
    photo_locations = []  # For map markers
    for photo in qs:
        detection_boxes = []
        for det in photo.detections.filter(is_shown=True):
            left_pct = (det.x or 0) * 100
            top_pct = (det.y or 0) * 100
            width_pct = (det.w or 0) * 100
            height_pct = (det.h or 0) * 100
            detection_boxes.append({
                "left": left_pct,
                "top": top_pct,
                "width": width_pct,
                "height": height_pct,
                "is_person": det.is_person(),
            })
        photos_with_boxes.append({
            "photo": photo,
            "detection_boxes": detection_boxes,
        })
        
        # Collect coordinates for map markers
        if photo.latitude and photo.longitude:
            # Add small random noise to obscure exact camera location
            # ~0.001 degrees is approximately 100 meters
            noise_lat = random.uniform(-0.001, 0.001)
            noise_lng = random.uniform(-0.001, 0.001)
            
            photo_locations.append({
                "id": photo.id,
                "lat": float(photo.latitude) + noise_lat,
                "lng": float(photo.longitude) + noise_lng,
                "camera": photo.camera.name if photo.camera else "Unknown",
                "date": photo.date_taken.strftime("%Y-%m-%d") if photo.date_taken else "Unknown",
            })

    context = {
        "photos_with_boxes": photos_with_boxes,
        "photo_locations": json.dumps(photo_locations),
        "species_options": Species.objects.all().order_by("name"),
        "camera_options": Camera.objects.all().order_by("name"),
        "selected_species_ids": list(map(str, filters["species_ids"])),
        "selected_camera_id": filters["camera_id"],
        "start_date": filters["start_date"],
        "end_date": filters["end_date"],
        "temp_min": filters["temp_min"],
        "temp_max": filters["temp_max"],
        "pressure_min": filters["pressure_min"],
        "pressure_max": filters["pressure_max"],
    }
    return render(request, "wildlife/gallery.html", context)


def gallery_export(request):
    """
    Export filtered gallery photos to CSV with one row per detection.
    
    Each row includes:
    - Photo metadata: name, temperature, pressure, date/time, camera
    - Detection data: animal species, image URL, normalized bounding box (x, y, w, h)
    
    Bounding box coordinates are normalized (0.0–1.0):
      x: fraction from left edge (0.0=leftmost, 1.0=rightmost)
      y: fraction from top edge (0.0=topmost, 1.0=bottommost)
      w: box width as fraction of image width
      h: box height as fraction of image height
    
    Example: x=0.1, y=0.2, w=0.3, h=0.4 means the detected object occupies
    a box 10% from the left, 20% from the top, and is 30% wide and 40% tall.
    """
    filters = _build_gallery_filters(request)
    qs = _apply_gallery_filters(filters).prefetch_related("detections__species", "camera")

    header = [
        "Picture Name",
        "Animals Detected",
        "Temperature (°C)",
        "Pressure (inHg)",
        "Time",
        "Date",
        "Camera",
        "Image URL",
        "BBox X",
        "BBox Y",
        "BBox W",
        "BBox H",
    ]

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)

    for photo in qs:
        detections = photo.detections.filter(is_shown=True).select_related("species")

        image_url = request.build_absolute_uri(photo.image.url) if photo.image else ""

        def write_row(species_label: str, det):
            x = det.x if det and det.x is not None else ""
            y = det.y if det and det.y is not None else ""
            w = det.w if det and det.w is not None else ""
            h = det.h if det and det.h is not None else ""
            writer.writerow([
                os.path.basename(photo.image.name) if photo.image else f"Photo {photo.id}",
                species_label,
                photo.temperature if photo.temperature is not None else "",
                photo.pressure if photo.pressure is not None else "",
                photo.time_taken.isoformat() if photo.time_taken else "",
                photo.date_taken.isoformat() if photo.date_taken else "",
                photo.camera.name if photo.camera else "",
                image_url,
                x,
                y,
                w,
                h,
            ])

        if detections.exists():
            for det in detections:
                species_name = det.species.name if det.species else (det.get_category_display() or "Unknown")
                write_row(species_name, det)
        else:
            write_row("Unknown", None)

    filename = f"gallery_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


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
                "is_person": det.is_person(),
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
    selected_mask = None
    if request.method == "POST":
        mask_id = (request.POST.get("ocr_mask") or "").strip()
        if mask_id:
            selected_mask = OcrMask.objects.filter(id=mask_id).first()
        files = request.FILES.getlist("images")
        if not files:
            error = "No files received. Please choose images before uploading."
        else:
            # Ensure speciesnet_inbox directory exists
            inbox_path = Path(settings.SPECIESNET_INBOX_ROOT)
            inbox_path.mkdir(parents=True, exist_ok=True)
            
            trailcam_path = Path(settings.MEDIA_ROOT) / "trailcam"
            trailcam_path.mkdir(parents=True, exist_ok=True)
            
            # Process each uploaded file (filter to images only)
            allowed_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
            skipped_non_images = []
            for uploaded_file in files:
                try:
                    # Skip non-images based on content type or extension
                    suffix = Path(uploaded_file.name).suffix.lower()
                    content_type = getattr(uploaded_file, "content_type", "") or ""
                    if not (content_type.startswith("image/") or suffix in allowed_exts):
                        skipped_non_images.append(uploaded_file.name)
                        continue

                    # 1. Save to speciesnet_inbox temporarily
                    inbox_file_path = inbox_path / uploaded_file.name
                    with open(inbox_file_path, 'wb+') as destination:
                        for chunk in uploaded_file.chunks():
                            destination.write(chunk)
                    
                    # 2. Run OCR to extract metadata
                    ocr_data = None
                    try:
                        img = Image.open(inbox_file_path)
                        ocr_data = _extract_overlay_meta(img, selected_mask)
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

                    if selected_mask:
                        photo.ocr_mask = selected_mask
                    
                    # Apply OCR metadata if available
                    if ocr_data:
                        if ocr_data.camera_name:
                            cam = Camera.objects.filter(name=ocr_data.camera_name).first()
                            if not cam:
                                # Create new camera with default St. Edwards University coordinates
                                cam = Camera.objects.create(
                                    name=ocr_data.camera_name,
                                    base_latitude=30.2311,
                                    base_longitude=-97.7524,
                                    description="needs proper lat and long"
                                )
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
            # If we skipped files, append a note
            if skipped_non_images:
                skip_msg = f"Skipped non-image files: {', '.join(skipped_non_images[:5])}"
                if len(skipped_non_images) > 5:
                    skip_msg += f" +{len(skipped_non_images)-5} more"
                error = (error + "\n" + skip_msg) if error else skip_msg
            
            if not error:
                return redirect("wildlife:upload_photos")

    recent_photos = Photo.objects.filter(is_published=False).order_by("-uploaded_at")[:50]
    ocr_masks = OcrMask.objects.order_by("name")

    return render(request, "wildlife/upload.html", {
        "error": error,
        "recent_photos": recent_photos,
        "ocr_masks": ocr_masks,
        "selected_mask_id": selected_mask.id if selected_mask else "",
        "camera_names": list(
            Camera.objects.filter(is_active=True)
            .order_by("name")
            .values_list("name", flat=True)
        ),
    })


@login_required
def test_ocr_region(request):
    """Test OCR on a region image and return extracted text."""
    require_researcher(request.user)
    
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)
    
    region_image = request.FILES.get("region_image")
    if not region_image:
        return JsonResponse({"error": "No image provided"}, status=400)
    
    try:
        # Open image and prepare for OCR
        img = Image.open(region_image)
        print(f"Region image size: {img.size}, mode: {img.mode}")
        
        # Convert to RGB if needed, then to grayscale
        if img.mode == "RGBA":
            img = img.convert("RGB")
        img = img.convert("L")
        
        # Upscale for better OCR
        scale = 4
        new_width = img.width * scale
        new_height = img.height * scale
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Apply binarization to create clean black text on white
        # Threshold at 128 (middle value) to create high contrast
        img = img.point(lambda p: 255 if p > 128 else 0, "1")
        
        # Convert back to L mode for OCR
        img = img.convert("L")
        
        # Encode processed image to base64 for preview
        import base64
        from io import BytesIO
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        print(f"Base64 image length: {len(img_base64)}, upscaled size: {img.size}")
        
        # Run OCR
        ocr_text = pytesseract.image_to_string(img).strip()
        print(f"OCR result: '{ocr_text}'")
        
        return JsonResponse({"ocr_text": ocr_text, "image_data": img_base64})
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"OCR test error: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def ocr_masks(request):
    require_researcher(request.user)

    errors = {}
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        sample_image = request.FILES.get("sample_image")

        def parse_norm(field):
            raw = (request.POST.get(field) or "").strip()
            if raw == "":
                errors[field] = "Required."
                return None
            try:
                val = Decimal(raw)
            except (InvalidOperation, ValueError):
                errors[field] = "Must be a number."
                return None
            if val < Decimal("0") or val > Decimal("1"):
                errors[field] = "Must be between 0 and 1."
                return None
            return val

        if not name:
            errors["name"] = "Name is required."
        if not sample_image:
            errors["sample_image"] = "Sample image is required."

        # Parse all 5 regions: temperature, pressure, camera, date, time
        temperature_x = parse_norm("temperature_x")
        temperature_y = parse_norm("temperature_y")
        temperature_w = parse_norm("temperature_w")
        temperature_h = parse_norm("temperature_h")

        pressure_x = parse_norm("pressure_x")
        pressure_y = parse_norm("pressure_y")
        pressure_w = parse_norm("pressure_w")
        pressure_h = parse_norm("pressure_h")

        camera_x = parse_norm("camera_x")
        camera_y = parse_norm("camera_y")
        camera_w = parse_norm("camera_w")
        camera_h = parse_norm("camera_h")

        date_x = parse_norm("date_x")
        date_y = parse_norm("date_y")
        date_w = parse_norm("date_w")
        date_h = parse_norm("date_h")

        time_x = parse_norm("time_x")
        time_y = parse_norm("time_y")
        time_w = parse_norm("time_w")
        time_h = parse_norm("time_h")

        # Basic size validation
        for prefix in ["temperature", "pressure", "camera", "date", "time"]:
            w_val = eval(f"{prefix}_w")
            h_val = eval(f"{prefix}_h")
            if w_val is not None and w_val <= 0:
                errors[f"{prefix}_w"] = "Width must be > 0."
            if h_val is not None and h_val <= 0:
                errors[f"{prefix}_h"] = "Height must be > 0."

        if not errors:
            OcrMask.objects.create(
                name=name,
                sample_image=sample_image,
                temperature_x=temperature_x,
                temperature_y=temperature_y,
                temperature_w=temperature_w,
                temperature_h=temperature_h,
                pressure_x=pressure_x,
                pressure_y=pressure_y,
                pressure_w=pressure_w,
                pressure_h=pressure_h,
                camera_x=camera_x,
                camera_y=camera_y,
                camera_w=camera_w,
                camera_h=camera_h,
                date_x=date_x,
                date_y=date_y,
                date_w=date_w,
                date_h=date_h,
                time_x=time_x,
                time_y=time_y,
                time_w=time_w,
                time_h=time_h,
            )
            return redirect("wildlife:ocr_masks")

    masks = OcrMask.objects.order_by("name")

    return render(request, "wildlife/meta_mask_ocr.html", {
        "masks": masks,
        "errors": errors,
    })


@login_required
def edit_ocr_mask(request, pk):
    require_researcher(request.user)
    mask = get_object_or_404(OcrMask, pk=pk)

    errors = {}
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        sample_image = request.FILES.get("sample_image")

        def parse_norm(field):
            raw = (request.POST.get(field) or "").strip()
            if raw == "":
                errors[field] = "Required."
                return None
            try:
                val = Decimal(raw)
            except (InvalidOperation, ValueError):
                errors[field] = "Must be a number."
                return None
            if val < Decimal("0") or val > Decimal("1"):
                errors[field] = "Must be between 0 and 1."
                return None
            return val

        if not name:
            errors["name"] = "Name is required."

        # Parse all 5 regions: temperature, pressure, camera, date, time
        temperature_x = parse_norm("temperature_x")
        temperature_y = parse_norm("temperature_y")
        temperature_w = parse_norm("temperature_w")
        temperature_h = parse_norm("temperature_h")

        pressure_x = parse_norm("pressure_x")
        pressure_y = parse_norm("pressure_y")
        pressure_w = parse_norm("pressure_w")
        pressure_h = parse_norm("pressure_h")

        camera_x = parse_norm("camera_x")
        camera_y = parse_norm("camera_y")
        camera_w = parse_norm("camera_w")
        camera_h = parse_norm("camera_h")

        date_x = parse_norm("date_x")
        date_y = parse_norm("date_y")
        date_w = parse_norm("date_w")
        date_h = parse_norm("date_h")

        time_x = parse_norm("time_x")
        time_y = parse_norm("time_y")
        time_w = parse_norm("time_w")
        time_h = parse_norm("time_h")

        # Basic size validation
        for prefix in ["temperature", "pressure", "camera", "date", "time"]:
            w_val = eval(f"{prefix}_w")
            h_val = eval(f"{prefix}_h")
            if w_val is not None and w_val <= 0:
                errors[f"{prefix}_w"] = "Width must be > 0."
            if h_val is not None and h_val <= 0:
                errors[f"{prefix}_h"] = "Height must be > 0."

        if not errors:
            mask.name = name
            if sample_image:
                mask.sample_image = sample_image
            mask.temperature_x = temperature_x
            mask.temperature_y = temperature_y
            mask.temperature_w = temperature_w
            mask.temperature_h = temperature_h
            mask.pressure_x = pressure_x
            mask.pressure_y = pressure_y
            mask.pressure_w = pressure_w
            mask.pressure_h = pressure_h
            mask.camera_x = camera_x
            mask.camera_y = camera_y
            mask.camera_w = camera_w
            mask.camera_h = camera_h
            mask.date_x = date_x
            mask.date_y = date_y
            mask.date_w = date_w
            mask.date_h = date_h
            mask.time_x = time_x
            mask.time_y = time_y
            mask.time_w = time_w
            mask.time_h = time_h
            mask.save()
            return redirect("wildlife:ocr_masks")

    return render(request, "wildlife/meta_mask_ocr.html", {
        "mask": mask,
        "errors": errors,
        "is_edit": True,
    })


@login_required
@require_POST
def delete_ocr_mask(request, pk):
    require_researcher(request.user)
    mask = get_object_or_404(OcrMask, pk=pk)
    mask.delete()
    return redirect("wildlife:ocr_masks")


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
        data = _extract_overlay_meta(img, photo.ocr_mask)
    except Exception as e:
        print("OCR ERROR:", e)
        return HttpResponseForbidden("OCR failed. Is Tesseract installed?")

    # set camera if exists, create if not
    if data.camera_name:
        cam = Camera.objects.filter(name=data.camera_name).first()
        if not cam:
            # Create new camera with default St. Edwards University coordinates
            cam = Camera.objects.create(
                name=data.camera_name,
                base_latitude=30.2311,
                base_longitude=-97.7524,
                description="needs proper lat and long"
            )
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


    # If the publish came from the edit form, save latest changes first.
    try:
        form = PhotoEditForm(request.POST, instance=photo)
        if form.is_valid():
            form.save()
    except Exception:
        # If not from edit form or validation fails, continue with existing values
        pass

    if photo.date_taken is None or photo.time_taken is None or photo.temperature is None or photo.pressure is None:
        return HttpResponseForbidden("Photo must be analyzed before publishing.")

    # Permanently black out human detections in the image
    if photo.image:
        person_detections = photo.detections.filter(category="2", is_shown=True)
        
        if person_detections.exists():
            # Open the image
            img_path = photo.image.path
            img = Image.open(img_path)
            draw = ImageDraw.Draw(img)
            
            # Draw black rectangles over person detections
            width, height = img.size
            for det in person_detections:
                if det.x is not None and det.y is not None and det.w is not None and det.h is not None:
                    # Convert normalized coordinates to pixel coordinates
                    x1 = int(float(det.x) * width)
                    y1 = int(float(det.y) * height)
                    x2 = int((float(det.x) + float(det.w)) * width)
                    y2 = int((float(det.y) + float(det.h)) * height)
                    
                    # Draw black filled rectangle
                    draw.rectangle([x1, y1, x2, y2], fill='black')
            
            # Save the modified image back
            img.save(img_path)

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
    """Update the species name and visibility for a detection.
    
    Species names are only saved when the request includes a 'save_species' flag.
    This prevents partial/incomplete species names from being created during typing.
    """
    require_researcher(request.user)
    detection = get_object_or_404(PhotoDetection, pk=pk)
    
    # Update species name only if explicitly saving (not on every keystroke)
    if "save_species" in request.POST and "species_name" in request.POST:
        species_name = request.POST.get("species_name", "").strip()
        if species_name:
            from wildlife.services.speciesnet import get_or_create_species
            species = get_or_create_species(species_name)
            detection.species = species
        else:
            detection.species = None
        detection.save()
    
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
            # Reload the same edit page instead of sending to upload
            return redirect("wildlife:photo_edit", pk=pk)
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
