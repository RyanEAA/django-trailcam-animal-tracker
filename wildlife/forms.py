from django import forms
from .models import Photo, PhotoDetection, Camera
from django.core.exceptions import ValidationError
import re


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True  # needed for Django 5


class PhotoUploadForm(forms.Form):
    images = forms.FileField(
        widget=MultiFileInput(attrs={"multiple": True}),
        required=True,
        label="Trailcam photos",
    )


class PhotoEditForm(forms.ModelForm):
    class Meta:
        model = Photo
        fields = [
            "camera",
            "date_taken",
            "time_taken",
            "temperature",
            "pressure",
            "latitude",
            "longitude",
            "is_published",
        ]


class PhotoDetectionForm(forms.ModelForm):
    class Meta:
        model = PhotoDetection
        fields = ["species", "confidence", "source"]


class CameraForm(forms.ModelForm):
    class Meta:
        model = Camera
        fields = ["name", "base_latitude", "base_longitude", "description", "is_active"]

        widgets = {
            "description": forms.TextInput(attrs={"placeholder": "Optional notes (location, trail name, etc.)"}),
        }

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip().upper().replace(" ", "")

        # normalizze to TRAILCAMXX format
        m = re.match(r"^TRAILCAM0*(\d{1,3})$", name)

        if not m:
            raise ValidationError("Camera name must be in format TRAILCAMXX (e.g. TRAILCAM05)")
        n = int(m.group(1))
        return f"TRAILCAM{n:02d}"
    
    def clean(self):
        cleaned = super().clean()
        lat = cleaned.get("base_latitude")
        lng = cleaned.get("base_longitude")

        if lat is None or lng is None:
            raise ValidationError("Both base latitude and longitude are required.")
        
        # simple bounds check
        if not (-90 <= lat <= 90):
            raise ValidationError("base_latitude", "Latitude must be between -90 and 90.")
        if not(-180 <= lng <= 180):
            raise ValidationError("base_longitude", "Longitude must be between -180 and 180.")
        
        return cleaned

        