from django import forms
from .models import Photo, PhotoDetection

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
        fields = ["species", "count", "confidence", "source"]
