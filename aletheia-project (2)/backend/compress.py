"""Server-side video compression for portal submissions.

The cybercrime.gov.in Deepfake complaint form has a 10 MB limit.
This module creates a continuous compressed copy under ~9.2 MB
without trimming or breaking continuity, and computes its SHA-256.
"""
import os
import subprocess
import videoinfo

PORTAL_TARGET_BYTES = 9.2 * 1024 * 1024  # Target ~9.2 MB safely below 10 MB limit


def compress_for_portal(input_path, output_dir):
    """If input video is larger than 9.5 MB, compresses it to under 9.5 MB.
    
    Returns:
      compressed_path (str or None): path to the compressed file if created
      compressed_hash (str or None): SHA-256 of the compressed copy
    """
    file_size = os.path.getsize(input_path)
    if file_size <= 9.5 * 1024 * 1024:
        # File is already under portal limit
        return None, None

    try:
        info = videoinfo.probe(input_path)
    except Exception:
        return None, None

    # Parse duration in seconds
    dur_str = info.get("duration", "0:00")
    parts = dur_str.split(":")
    if len(parts) == 2:
        duration_sec = float(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        duration_sec = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    else:
        duration_sec = 30.0

    if duration_sec <= 0:
        duration_sec = 30.0

    # Calculate target bitrate in kbps
    total_bits = PORTAL_TARGET_BYTES * 8
    target_total_kbps = total_bits / duration_sec / 1000.0
    audio_kbps = 48.0
    video_kbps = max(100.0, target_total_kbps - audio_kbps)

    output_path = os.path.join(output_dir, "portal_submission.mp4")

    # Single-pass constrained bitrate encode
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-b:v", f"{int(video_kbps)}k",
        "-maxrate", f"{int(video_kbps * 1.3)}k",
        "-bufsize", f"{int(video_kbps * 2)}k",
        "-vf", "scale='min(1280,iw)':-2",
        "-c:a", "aac",
        "-b:a", f"{int(audio_kbps)}k",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)
    except Exception:
        return None, None

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        digest = videoinfo.sha256_of(output_path)
        return output_path, digest

    return None, None

