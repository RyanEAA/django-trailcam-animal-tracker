from typing import List, Dict, Any
import numpy as np
from PIL import Image

from megadetector.detection import run_detector
from wildlife.models import Photo, PhotoDetection

# lazy load global detector
_detector = None

def get_detector():
    global _detector
    if _detector is None:
        # download and load MDv5 the first time
        _detector = run_detector.load_detector('MDV5A')
    return _detector


def run_megadetector(photo:Photo, conf_threshold: float = 0.2) -> Dict[str, Any]:
    """
    Docstring for run_megadetector
    
    run MegaDetector on a Phot and returns the raw result dict
    Does not write to the database
    """

    img = Image.open(photo.image.path).convert("RGB")
    model = get_detector()
    result = model.generate_detections_one_image(np.array(img))

    # filter detections in-place
    result["detections"] = [
        d for d in result.get("detections", [])
        if d.get("conf", 0.0) >= conf_threshold
    ]

    return result

def save_megadetector_results(photo:Photo, result:Dict[str, Any]) -> None:
    """
    Persist MegaDetector outputs into Photo + PhotoDetection rows
    """

    # store raw JSON result on the PHoto
    photo.megadetector_result = result
    photo.save()

    # create detection rows
    for det in result.get("detections", []):
        cat = det.get("category") 
        conf = det.get("conf", 0.0)
        x, y, w, h = det.get("bbox", [0,0,0,0])  # normalized

        # just store box
        PhotoDetection.objects.create(
            photo=photo,
            species=None,
            confidence=conf,
            x=x,
            y=y,
            w=w,
            h=h,
            source="megadetector",
            category=cat
        )