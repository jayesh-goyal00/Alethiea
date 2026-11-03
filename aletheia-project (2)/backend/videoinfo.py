"""Reads basic facts about a video file. No web framework in here, so it is easy to test."""
import hashlib
import json
import os
import subprocess

ALLOWED_EXT = {".mp4", ".mov", ".webm"}


class VideoError(Exception):
    """A problem with the video that is safe to show to the user."""


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fps(stream):
    # ffprobe gives frame rates as fractions such as "30000/1001"
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = stream.get(key) or "0/0"
        try:
            num, den = raw.split("/")
            num, den = float(num), float(den)
            if den > 0 and num > 0:
                return round(num / den, 2)
        except ValueError:
            pass
    return None


def _clock(seconds):
    s = int(round(seconds))
    return "%d:%02d" % (s // 60, s % 60)


def probe(path):
    """Returns {'fps': '29.97', 'duration': '0:42', 'seconds': 42.0}. Raises VideoError if it is not a usable video."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        raise RuntimeError("ffprobe is not installed on the server.")
    except subprocess.TimeoutExpired:
        raise VideoError("The video took too long to read.")
    if out.returncode != 0:
        raise VideoError("This file could not be read as a video.")
    try:
        info = json.loads(out.stdout)
    except ValueError:
        raise VideoError("This file could not be read as a video.")
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise VideoError("No video found in this file.")
    try:
        seconds = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    except ValueError:
        seconds = 0
    if seconds <= 0:
        raise VideoError("Could not work out how long this video is.")
    fps = _fps(video)
    return {"fps": ("%.2f" % fps) if fps else None, "duration": _clock(seconds), "seconds": seconds}


def safe_name(name):
    name = os.path.basename(name or "video")
    return name[:120] or "video"
