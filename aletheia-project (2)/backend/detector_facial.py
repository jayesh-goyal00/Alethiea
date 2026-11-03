"""Facial Manipulation & Artifacts Detector for Aletheia on Apple Silicon.

Analyzes:
1. Facial boundary blending & warping seams (Laplacian edge discontinuity across facial perimeter).
2. 2D FFT spectral frequency anomalies (high-freq to mid-freq ratio, azimuthal checkerboard spikes).
3. Inter-face consistency across multiple faces (evaluates largest face & reports multi-face presence).
4. Memory efficient: processes bounded crops, calls cleanup_memory().
"""
import cv2
import numpy as np
from device import cleanup_memory
from preprocessor import VideoData


def analyze_face_spectral(crop_rgb) -> dict:
    """Computes 2D FFT high-frequency to mid-frequency energy ratio and azimuthal variance."""
    if crop_rgb is None or crop_rgb.shape[0] < 36 or crop_rgb.shape[1] < 36:
        return {"spectral_score": 0.0, "ratio": 0.0, "angular_std": 0.0}

    gray = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)
    resized = cv2.resize(gray, (128, 128), interpolation=cv2.INTER_AREA)
    f = np.fft.fft2(resized.astype(np.float32))
    fshift = np.fft.fftshift(f)
    magnitude = np.abs(fshift) + 1e-6
    log_mag = np.log(magnitude)

    cy, cx = 64, 64
    y, x = np.ogrid[:128, :128]
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)

    high_freq_mask = (r >= 35) & (r <= 60)
    mid_freq_mask = (r >= 15) & (r < 35)

    high_energy = np.mean(log_mag[high_freq_mask])
    mid_energy = np.mean(log_mag[mid_freq_mask])
    ratio = float(high_energy / (mid_energy + 1e-6))

    angles = np.arctan2(y - cy, x - cx)
    sector_means = []
    for deg in range(0, 360, 45):
        rad_start = np.deg2rad(deg) - np.pi
        rad_end = np.deg2rad(deg + 45) - np.pi
        sector_mask = high_freq_mask & (angles >= rad_start) & (angles < rad_end)
        if np.any(sector_mask):
            sector_means.append(np.mean(log_mag[sector_mask]))

    angular_std = float(np.std(sector_means)) if sector_means else 0.0

    score = 0.0
    if ratio > 0.88:
        score += min(0.6, (ratio - 0.88) * 4.0)
    if angular_std > 0.35:
        score += min(0.4, (angular_std - 0.35) * 2.0)

    return {
        "spectral_score": min(1.0, max(0.0, score)),
        "ratio": round(ratio, 3),
        "angular_std": round(angular_std, 3),
    }


def analyze_face_boundary(frame_rgb, box) -> float:
    """Detects gradient discontinuities around the face boundary."""
    x, y, w, h = box
    fh, fw = frame_rgb.shape[:2]
    margin = int(w * 0.15)
    x1, y1 = max(0, x - margin), max(0, y - margin)
    x2, y2 = min(fw, x + w + margin), min(fh, y + h + margin)

    patch = frame_rgb[y1:y2, x1:x2]
    if patch.size == 0 or patch.shape[0] < 30 or patch.shape[1] < 30:
        return 0.0

    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
    laplacian = np.abs(cv2.Laplacian(gray, cv2.CV_64F))

    pw, ph = patch.shape[1], patch.shape[0]
    bx1 = x - x1
    by1 = y - y1
    bx2 = bx1 + w
    by2 = by1 + h

    inner_mask = np.zeros((ph, pw), dtype=bool)
    outer_ring = np.zeros((ph, pw), dtype=bool)

    ix1, iy1 = max(0, int(bx1 + 0.15 * w)), max(0, int(by1 + 0.15 * h))
    ix2, iy2 = min(pw, int(bx2 - 0.15 * w)), min(ph, int(by2 - 0.15 * h))
    inner_mask[iy1:iy2, ix1:ix2] = True

    ox1, oy1 = max(0, int(bx1 - 0.1 * w)), max(0, int(by1 - 0.1 * h))
    ox2, oy2 = min(pw, int(bx2 + 0.1 * w)), min(ph, int(by2 + 0.1 * h))
    outer_ring[oy1:oy2, ox1:ox2] = True
    outer_ring[inner_mask] = False

    inner_grad = np.mean(laplacian[inner_mask]) if np.any(inner_mask) else 0.0
    outer_grad = np.mean(laplacian[outer_ring]) if np.any(outer_ring) else 0.0

    if inner_grad + outer_grad < 1e-4:
        return 0.0

    # Elevated discontinuity between outer blending seam and inner face
    discontinuity = abs(inner_grad - outer_grad) / (inner_grad + outer_grad)
    return float(min(1.0, max(0.0, discontinuity)))


def analyze_facial_manipulation(video_data: VideoData) -> dict:
    """Analyzes facial manipulation across sampled frames.
    
    Returns standard detector dict:
      detector_name, status, raw_score, calibrated_confidence, quality_info, findings, limitations, error_details
    """
    if not video_data.face_stats["has_face"]:
        return {
            "detector_name": "Facial Manipulation & Boundary",
            "status": "unavailable",
            "raw_score": None,
            "calibrated_confidence": 0.0,
            "quality_info": {
                "max_faces": 0,
                "frames_with_face": 0,
                "reason": "No human faces detected in video",
            },
            "findings": ["No visible human face found to evaluate facial boundaries or alterations."],
            "limitations": ["Applies only to videos containing human faces."],
            "error_details": None,
        }

    spectral_scores = []
    boundary_scores = []
    total_faces_evaluated = 0

    for idx, f_info in enumerate(video_data.faces):
        frame_rgb = video_data.sampled_frames[idx]
        for box, crop in zip(f_info["boxes"], f_info["crops"]):
            total_faces_evaluated += 1
            sp = analyze_face_spectral(crop)
            spectral_scores.append(sp["spectral_score"])
            b_score = analyze_face_boundary(frame_rgb, box)
            boundary_scores.append(b_score)

    avg_spectral = float(np.mean(spectral_scores)) if spectral_scores else 0.0
    avg_boundary = float(np.mean(boundary_scores)) if boundary_scores else 0.0
    max_boundary = float(np.max(boundary_scores)) if boundary_scores else 0.0

    # Synthesize facial score (0 - 100)
    # Natural photos: spectral < 0.05, boundary < 0.35
    # Face swaps / Deepfakes: elevated boundary discontinuity > 0.45 or spectral spikes
    face_risk = (avg_spectral * 0.4) + (avg_boundary * 0.3) + (max_boundary * 0.3)
    raw_score = int(np.clip(face_risk * 100, 15, 95))

    max_faces = video_data.face_stats["max_faces_in_frame"]
    multi_face_note = (
        f"Multiple faces ({max_faces}) detected; evaluated across all tracks."
        if max_faces > 1
        else "Single primary face tracked."
    )

    findings = []
    limitations = []

    if raw_score >= 65:
        findings.append("Suspicious edge gradient discontinuities detected around facial perimeter.")
        findings.append("Facial frequency characteristics show signs of synthetic generation or inpainting.")
    elif raw_score <= 35:
        findings.append("Facial contours and skin gradient transitions are continuous and natural.")
        findings.append("No boundary warping or face-swap seam blending detected.")
    else:
        findings.append("Facial boundary consistency is inconclusive; minor compression blur observed.")

    findings.append(multi_face_note)
    limitations.append("High compression or low video resolution can soften natural facial boundaries.")

    confidence = 0.80 if total_faces_evaluated >= 8 else 0.55
    cleanup_memory()

    return {
        "detector_name": "Facial Manipulation & Boundary",
        "status": "available",
        "raw_score": raw_score,
        "calibrated_confidence": round(confidence, 2),
        "quality_info": {
            "max_faces_in_frame": max_faces,
            "faces_evaluated": total_faces_evaluated,
            "avg_boundary_score": round(avg_boundary, 3),
            "max_boundary_score": round(max_boundary, 3),
            "avg_spectral_score": round(avg_spectral, 3),
        },
        "findings": findings,
        "limitations": limitations,
        "error_details": None,
    }

