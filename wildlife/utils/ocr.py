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
    - missing spaces between tokens
    - junk punctuation
    - keep useful separators
    NOTE: camera-specific normalization is handled by normalize_camera_name()
    """
    t = (raw or "").upper()

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


_CAM_RE = re.compile(
    r"(TRAIL\s*CAM)\s*[-_ ]*\s*([0-9OQD]{1,3})",
    re.IGNORECASE
)

def normalize_camera_name(raw: str) -> str | None:
    """
    Normalizes OCR camera strings to canonical form like:
    - TRAILCAM05
    - TRAILCAM105

    Handles OCR confusions:
    O -> 0
    Q -> 0
    D -> 0
    """
    if not raw:
        return None

    s = (raw or "").upper().strip()
    match = _CAM_RE.search(s)
    if not match:
        return None

    raw_num = match.group(2)

    cleaned = (
        raw_num
        .replace("O", "0")
        .replace("Q", "0")
        .replace("D", "0")
    )

    try:
        n = int(cleaned)
    except ValueError:
        return None

    if n < 100:
        return f"TRAILCAM{n:02d}"
    return f"TRAILCAM{n}"


@dataclass
class OverlayMeta:
    camera_name: Optional[str] = None
    date_taken: Optional[date] = None
    time_taken: Optional[time] = None
    temperature_c: Optional[float] = None
    pressure_inhg: Optional[float] = None
    raw_text: str = ""


def _extract_temp_pressure(left_text: str) -> tuple[Optional[float], Optional[float]]:
    """
    Left region example: '23C 29.09 INHG'
    """
    t = normalize_overlay_text(left_text)

    temp = None
    press = None

    m = re.search(r"\b(-?\d+(?:\.\d+)?)\s*C\b", t)
    if m:
        try:
            temp = float(m.group(1))
        except ValueError:
            pass

    # strict 2 digits dot 2 digits (avoids grabbing '9' out of 29.09)
    m = re.search(r"\b(\d{2}\.\d{2})\s*INHG\b", t)
    if m:
        try:
            press = float(m.group(1))
        except ValueError:
            pass

    return temp, press


def _extract_camera(center_text: str) -> Optional[str]:
    """
    Center region example: 'TRAILCAMQ5' -> normalize -> 'TRAILCAM05'
    """
    # camera normalization already uppercases & handles Q/O/D -> 0
    return normalize_camera_name(center_text)


def _extract_date_time(right_text: str) -> tuple[Optional[date], Optional[time]]:
    """
    Right region example: '12/06/2025 05:41PM'
    """
    t = normalize_overlay_text(right_text)

    d = None
    tm = None

    m = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", t)
    if m:
        try:
            d = datetime.strptime(m.group(1), "%m/%d/%Y").date()
        except ValueError:
            pass

    m = re.search(r"\b(\d{1,2}:\d{2})\s*([AP]M)\b", t)
    if m:
        try:
            tm = datetime.strptime(m.group(1) + m.group(2), "%I:%M%p").time()
        except ValueError:
            pass

    return d, tm


def extract_overlay_meta_split(left_text: str, center_text: str, right_text: str) -> OverlayMeta:
    """
    Extracts metadata from already-split OCR regions.
    """
    meta = OverlayMeta()

    temp, press = _extract_temp_pressure(left_text)
    meta.temperature_c = temp
    meta.pressure_inhg = press

    meta.camera_name = _extract_camera(center_text)

    d, tm = _extract_date_time(right_text)
    meta.date_taken = d
    meta.time_taken = tm

    # debug combined normalized text (useful in logs)
    meta.raw_text = " | ".join([
        normalize_overlay_text(left_text),
        normalize_overlay_text(center_text),
        normalize_overlay_text(right_text),
    ])

    return meta
