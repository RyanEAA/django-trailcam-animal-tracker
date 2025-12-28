# wildlife/services/speciesnet.py

from __future__ import annotations

import json
import subprocess
import tempfile
import shutil
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from django.conf import settings

from wildlife.models import Photo, PhotoDetection, Species


def run_speciesnet_on_image(image_path: Path) -> Dict[str, Any]:
    """
    Run SpeciesNet on a single image and return parsed results.
    
    SpeciesNet expects a folder path, so we create a temporary folder
    with the single image, run detection, and parse results.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        Dictionary with SpeciesNet prediction data
        
    Example output structure:
    {
        "filepath": "/path/to/image.jpg",
        "prediction": "uuid;taxonomic;path;common name",
        "prediction_score": 0.95,
        "prediction_source": "classifier",
        "detections": [
            {
                "bbox": [x, y, w, h],
                "conf": 0.98,
                "category": "animal",
                "species": "uuid;taxonomic;path;common name",
                "species_conf": 0.95
            }
        ]
    }
    """
    # Create a temporary directory for SpeciesNet to process
    with tempfile.TemporaryDirectory(prefix='speciesnet_') as temp_dir:
        temp_folder = Path(temp_dir)
        output_json = temp_folder / 'predictions.json'
        
        # Copy image to temp folder (SpeciesNet processes folders)
        temp_image = temp_folder / image_path.name
        shutil.copy2(str(image_path), str(temp_image))
        
        try:
            # Choose python executable (default to current interpreter)
            python_bin = getattr(settings, "SPECIESNET_PYTHON", sys.executable)

            # Run SpeciesNet (detector + classifier) on the temp folder
            cmd = [
                python_bin,
                '-m',
                'speciesnet.scripts.run_model',
                '--folders', str(temp_folder),
                '--predictions_json', str(output_json),
            ]
            print(f"[SpeciesNet] Running: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=300  # 5 minute timeout
            )

            if result.stdout:
                print(f"[SpeciesNet] stdout: {result.stdout.strip()}")
            if result.stderr:
                print(f"[SpeciesNet] stderr: {result.stderr.strip()}")
            
            # Parse the JSON output
            if not output_json.exists():
                print(f"SpeciesNet did not create output file: {output_json}")
                return {
                    "filepath": str(image_path),
                    "prediction": None,
                    "prediction_score": 0.0,
                    "detections": []
                }
            
            with open(output_json, 'r') as f:
                data = json.load(f)
            
            # SpeciesNet outputs a dict with "predictions" list
            if isinstance(data, dict) and 'predictions' in data:
                predictions = data['predictions']
                if predictions and len(predictions) > 0:
                    # Return the first (and should be only) prediction
                    return predictions[0]
            elif isinstance(data, list) and data:
                return data[0]
            
            # Return empty result if no predictions
            return {
                "filepath": str(image_path),
                "prediction": None,
                "prediction_score": 0.0,
                "detections": []
            }
            
        except subprocess.CalledProcessError as e:
            print(f"SpeciesNet CLI error: {e.stderr}")
            return {
                "filepath": str(image_path),
                "prediction": None,
                "prediction_score": 0.0,
                "detections": [],
                "error": f"Command failed: {e.stderr}"
            }
        except subprocess.TimeoutExpired as e:
            print(f"SpeciesNet timeout after 5 minutes")
            return {
                "filepath": str(image_path),
                "prediction": None,
                "prediction_score": 0.0,
                "detections": [],
                "error": "SpeciesNet processing timed out"
            }
        except Exception as e:
            print(f"Error running SpeciesNet: {e}")
            return {
                "filepath": str(image_path),
                "prediction": None,
                "prediction_score": 0.0,
                "detections": [],
                "error": str(e)
            }


def extract_common_name(species_string: Optional[str]) -> Optional[str]:
    """
    Extract the common name from a SpeciesNet species string.
    
    Format: "uuid;class;order;family;genus;species;common name"
    Example: "990ae9dd-7a59-4344-afcb-1b7b21368000;mammalia;primates;hominidae;homo;sapiens;human"
    Returns: "human"
    """
    if not species_string:
        return None
    
    parts = species_string.split(';')
    if len(parts) >= 7:
        # Last part is the common name
        return parts[-1].strip().title()
    
    return None


def get_or_create_species(common_name: str) -> Optional[Species]:
    """
    Get or create a Species object by common name.
    Returns None if common_name is None or empty.
    """
    if not common_name:
        return None
    
    species, created = Species.objects.get_or_create(
        name=common_name
    )
    return species


def save_speciesnet_results(photo: Photo, result: Dict[str, Any]) -> None:
    """
    Save SpeciesNet detection results as PhotoDetection objects.
    
    Args:
        photo: Photo object to attach detections to
        result: SpeciesNet result dictionary
    """
    # Persist raw result for debugging/inspection
    photo.speciesnet_result = result
    photo.save(update_fields=['speciesnet_result'])

    # Delete existing detections for this photo (in case of re-analysis)
    PhotoDetection.objects.filter(photo=photo).delete()
    
    detections = result.get('detections', [])

    # Fallback species from top-level prediction or classifications
    fallback_species_string = result.get('prediction')
    fallback_species_conf = result.get('prediction_score', 0.0)

    # Log the fallback common name for debugging
    fallback_common = extract_common_name(fallback_species_string)
    if fallback_common:
        print(f"[SpeciesNet] Fallback species: {fallback_common}")

    # If there is a classifications block, pick the top class as fallback
    try:
        classes = result.get('classifications', {}).get('classes') or []
        scores = result.get('classifications', {}).get('scores') or []
        if classes and scores and len(classes) == len(scores):
            top_idx = max(range(len(scores)), key=lambda i: scores[i])
            fallback_species_string = fallback_species_string or classes[top_idx]
            fallback_species_conf = max(fallback_species_conf, scores[top_idx])
    except Exception:
        pass
    
    if not detections:
        # No detections found - but we might have a top-level prediction
        prediction = fallback_species_string
        prediction_score = fallback_species_conf
        
        if prediction and prediction_score > 0:
            # Create a single detection for the whole image
            common_name = extract_common_name(prediction)
            species = get_or_create_species(common_name) if common_name else None
            
            PhotoDetection.objects.create(
                photo=photo,
                species=species,
                confidence=prediction_score,
                x=0.0,
                y=0.0,
                w=1.0,
                h=1.0,
                source='speciesnet',
                category='1'
            )
        else:
            print(f"[SpeciesNet] No detections/prediction for photo {photo.id}")
        return
    
    for det in detections:
        # Extract bounding box (normalized coordinates)
        bbox = det.get('bbox', [0, 0, 0, 0])
        if len(bbox) == 4:
            x, y, w, h = bbox
        else:
            x, y, w, h = 0, 0, 0, 0
        
        # Extract detection confidence
        conf = det.get('conf', 0.0)
        
        # Extract species information (prefer explicit species/prediction; ignore generic labels)
        species_string = det.get('species') or det.get('prediction')
        label = det.get('label')
        if not species_string and label and ';' in label:
            species_string = label

        species_conf = det.get('species_conf', det.get('species_score', det.get('score', conf)))

        # Fallback to top-level prediction if missing
        if not species_string and fallback_species_string:
            species_string = fallback_species_string
            species_conf = max(species_conf or 0.0, fallback_species_conf or 0.0)
        
        # Parse common name from species string
        common_name = extract_common_name(species_string)
        
        # Get or create Species object
        species = get_or_create_species(common_name) if common_name else None
        
        # Create PhotoDetection
        PhotoDetection.objects.create(
            photo=photo,
            species=species,
            confidence=species_conf,
            x=x,
            y=y,
            w=w,
            h=h,
            source='speciesnet',
            category=det.get('category') or '1'  # default to animal
        )
    
    # Also store the raw JSON result on the Photo for reference
    photo.speciesnet_result = result
    photo.save(update_fields=['speciesnet_result'])
