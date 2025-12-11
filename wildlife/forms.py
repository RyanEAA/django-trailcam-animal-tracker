from django import forms
from .models import Photo

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
        fields = ["species", "date_taken", "environment", "latitude", "longitude"]
