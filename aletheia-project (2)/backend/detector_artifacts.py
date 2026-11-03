"""Detects generative AI and deepfake artifacts in video frames.

Mechanisms:
1. Frequency Domain Artifacts (2D FFT):
   AI generators (GANs, Diffusion, neural upsamplers) create high-frequency
   spectral periodicities and unnatural energy distribution compared to real lenses.
2. Boundary Blending / Warping:
   Face swaps blend a synthetic face into an existing head, leaving edge gradient
   discontinuities and perimeter blur around the face contour.
3. Texture Consistency:
   Compares high-frequency noise variance between the face region and surrounding areas.
"""
import math
import numpy as np
import cv2


def analyze_spectral_artifacts(face_gray):
    """Calculates 2D FFT spectral energy distribution to detect AI synthesis patterns.
    
    Real camera sensors exhibit power falloff following natural scene statistics (1/f^a).
    Generative models exhibit high-frequency spikes and azimuthal variance anomalies.
    """
    if face_gray is None or face_gray.shape[0] < 40 or face_gray.shape[1] < 40:
        return 0.0

    # Resize to standard power of 2 for uniform FFT
    resized = cv2.resize(face_gray, (128, 128), interpolation=cv2.INTER_AREA)
    f = np.fft.fft2(resized.astype(np.float32))
    fshift = np.fft.fftshift(f)
    magnitude = np.abs(fshift) + 1e-6
    log_mag = np.log(magnitude)

    # Calculate radial energy distribution
    cy, cx = 64, 64
    y, x = np.ogrid[:128, :128]
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)

    # High frequency ring (between 35 and 60 pixels from DC center)
    high_freq_mask = (r >= 35) & (r <= 60)
    mid_freq_mask = (r >= 15) & (r < 35)

    high_energy = np.mean(log_mag[high_freq_mask])
    mid_energy = np.mean(log_mag[mid_freq_mask])

    # In natural optical photos, mid energy strongly dominates high energy.
    # In AI generated faces, the ratio high/mid is abnormally elevated.
    ratio = float(high_energy / (mid_energy + 1e-6))

    # Azimuthal directional variance (checkerboard artifacts cause angular variance spikes)
    angles = np.arctan2(y - cy, x - cx)
    sector_means = []
    for deg in range(0, 360, 45):
        rad_start = np.deg2rad(deg) - np.pi
        rad_end = np.deg2rad(deg + 45) - np.pi
        sector_mask = high_freq_mask & (angles >= rad_start) & (angles < rad_end)
        if np.any(sector_mask):
            sector_means.append(np.mean(log_mag[sector_mask]))

    angular_std = float(np.std(sector_means)) if sector_means else 0.0

    # Combine ratio and angular variance into an artifact score (0.0 to 1.0)
    score = 0.0
    if ratio > 0.88:
        score += min(0.6, (ratio - 0.88) * 4.0)
    if angular_std > 0.35:
        score += min(0.4, (angular_std - 0.35) * 2.0)

    return min(1.0, max(0.0, score))


def analyze_boundary_blending(frame, face_box):
    """Detects gradient discontinuities around the face boundary.
    
    Face swap models paste a new face mask onto a source body,
    creating edge blending blur or unnatural gradient jumps along the perimeter.
    """
    x, y, w, h = face_box
    fh, fw = frame.shape[:2]

    # Ensure box has margin around it
    margin = int(w * 0.15)
    x1 = max(0, x - margin)
    y1 = max(0, y - margin)
    x2 = min(fw, x + w + margin)
    y2 = min(fh, y + h + margin)

    patch = frame[y1:y2, x1:x2]
    if patch.size == 0 or patch.shape[0] < 30 or patch.shape[1] < 30:
        return 0.0

    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    # Calculate Laplacian gradients
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance_map = np.abs(laplacian)

    # Inner face zone vs outer boundary ring
    pw, ph = patch.shape[1], patch.shape[0]
    inner_mask = np.zeros((ph, pw), dtype=bool)
    outer_ring_mask = np.zeros((ph, pw), dtype=bool)

    # Elliptical masks
    cy, cx = ph // 2, pw // 2
    y_idx, x_idx = np.ogrid[:ph, :pw]
    norm_dist = ((x_idx - cx) / (w * 0.45 + 1e-5)) ** 2 + ((y_idx - cy) / (h * 0.45 + 1e-5)) ** 2

    inner_mask[norm_dist < 0.65] = True
    outer_ring_mask[(norm_dist >= 0.75) & (norm_dist <= 1.25)] = True

    if not np.any(inner_mask) or not np.any(outer_ring_mask):
        return 0.0

    inner_grad = float(np.mean(variance_map[inner_mask]))
    boundary_grad = float(np.mean(variance_map[outer_ring_mask]))

    # An unnatural drop at boundary (excessive Poisson blur) or huge spike (seam line)
    grad_ratio = boundary_grad / (inner_grad + 1e-5)
    anomaly = 0.0
    if grad_ratio < 0.35:  # boundary blurred out
        anomaly = min(1.0, (0.35 - grad_ratio) * 3.0)
    elif grad_ratio > 2.8:  # harsh boundary seam
        anomaly = min(1.0, (grad_ratio - 2.8) * 0.5)

    return float(anomaly)


def analyze_video_artifacts(video_path, face_boxes_sample):
    """Runs spectral and boundary artifact tests across sampled frames.
    
    face_boxes_sample: list of (frame, (x, y, w, h))
    Returns:
      spectral_score: float (0.0 to 1.0)
      boundary_score: float (0.0 to 1.0)
    """
    if not face_boxes_sample:
        return 0.0, 0.0

    spectral_scores = []
    boundary_scores = []

    for frame, box in face_boxes_sample:
        x, y, w, h = box
        face_crop = frame[y : y + h, x : x + w]
        if face_crop.size == 0:
            continue
        gray_face = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        s_score = analyze_spectral_artifacts(gray_face)
        b_score = analyze_boundary_blending(frame, box)
        spectral_scores.append(s_score)
        boundary_scores.append(b_score)

    avg_spectral = float(np.mean(spectral_scores)) if spectral_scores else 0.0
    avg_boundary = float(np.mean(boundary_scores)) if boundary_scores else 0.0
    return avg_spectral, avg_boundary

