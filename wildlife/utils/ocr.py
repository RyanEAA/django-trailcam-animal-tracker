from __future__ import annotations

import re
from datetime import datetime, date, time
from PIL import Image
from dataclasses import dataclass
from typing import Optional

def crop_bottom_strip(img: Image.Image, pct: float=0.2) -> Image.Image:
    """Crop the bottom pct portion of the image"""
    w, h = img.size
    y0 = int(h * (1 - pct))   # start near bottom
    return img.crop((0, y0, w, h))


@dataclass
class OverlayMeta:
    camera_name: Optional[str] = None     # e.g. "TRAILCAM05"
    date_taken: Optional[date] = None     # datetime.date
    time_taken: Optional[time] = None     # datetime.time
    temperature_c: Optional[float] = None # e.g. 23.0
    pressure_inhg: Optional[float] = None # e.g. 29.09
    raw_text: str = ""                    # normalized text (debug)


def normalize_overlay_text(raw: str) -> str:
    """
    Normalize common OCR issues:
    - O vs 0 in TRAILCAM0X
    - missing spaces between tokens
    - junk punctuation
    """
    t = (raw or "").upper()

    # Fix common camera OCR confusion: TRAILCAMO5 -> TRAILCAM05
    t = re.sub(r"\bTRAILCAMO(?=\d)\b", "TRAILCAM0", t)  # rare exact
    t = re.sub(r"\bTRAILCAMO(\d)\b", r"TRAILCAM0\1", t) # common
    t = t.replace("TRAILCAMO", "TRAILCAM0")             # fallback

    # Insert spaces where OCR jammed tokens:
    # 23C29.09INHG -> 23C 29.09INHG
    t = re.sub(r"(\d)C(\d)", r"\1C \2", t)

    # 29.09INHG -> 29.09 INHG
    t = re.sub(r"(\d)(INHG)\b", r"\1 \2", t)

    # 12/06/202505:41PM -> 12/06/2025 05:41PM
    t = re.sub(r"(\d{2}/\d{2}/\d{4})(\d{1,2}:\d{2}\s*[AP]M)\b", r"\1 \2", t)

    # Remove weird punctuation but keep useful separators
    t = re.sub(r"[^\w\s:/\.]", " ", t)

    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def extract_overlay_meta(raw_text: str) -> OverlayMeta:
    """
    Extract camera, date, time, temperature (C), and pressure (inHg)
    from OCR text produced from the trailcam overlay bar.
    """
    t = normalize_overlay_text(raw_text)
    meta = OverlayMeta(raw_text=t)

    # ---- Camera ----
    # Matches: TRAILCAM05, TRAILCAM5, TRAILCAM005 (normalize -> TRAILCAM05)
    m = re.search(r"\bTRAILCAM0*(\d{1,3})\b", t)
    if m:
        n = int(m.group(1))
        meta.camera_name = f"TRAILCAM{n:02d}"

    # ---- Date ----
    # Matches: 12/06/2025
    m = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", t)
    if m:
        try:
            meta.date_taken = datetime.strptime(m.group(1), "%m/%d/%Y").date()
        except ValueError:
            pass

    # ---- Time ----
    # Matches: 05:41PM or 5:41PM (optional space before AM/PM is OK)
    m = re.search(r"\b(\d{1,2}:\d{2})\s*([AP]M)\b", t)
    if m:
        try:
            hhmm = m.group(1)
            ampm = m.group(2)
            meta.time_taken = datetime.strptime(hhmm + ampm, "%I:%M%p").time()
        except ValueError:
            pass

    # ---- Temperature (C) ----
    # Matches: 23C, -2C, 23.5C
    m = re.search(r"\b(-?\d+(?:\.\d+)?)\s*C\b", t)
    if m:
        try:
            meta.temperature_c = float(m.group(1))
        except ValueError:
            pass

    # ---- Pressure (inHg) ----
    # Trailcam pressure is typically "29.48 INHG" (two digits dot two digits).
    # Strict regex avoids accidentally capturing only "9" from "29.09".
    m = re.search(r"\b(\d{2}\.\d{2})\s*INHG\b", t)
    if m:
        try:
            meta.pressure_inhg = float(m.group(1))
        except ValueError:
            pass

    return meta
