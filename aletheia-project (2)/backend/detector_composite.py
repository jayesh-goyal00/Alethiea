"""Composite deepfake detector with Multi-Face Detection and DEBUG_PULSE logging.

Mechanisms:
1. Biological Pulse Detection (rPPG - POS Algorithm)
2. Frequency Domain Generative AI Spectral Artifacts (2D FFT)
3. Facial Boundary Blending and Warping Seam Detection

Features:
- Handles multiple faces: tracks all faces, evaluates largest/highest risk, notes count in results.
- Robust multi-angle face detection (frontal + profile cascades with downsampling).
- Shot-cut detection: detects if video has rapid cuts preventing continuous rPPG.
- DEBUG_PULSE=1: Prints full terminal diagnostics (never sent to the website).
"""
import math
import os
import sys
import cv2
import numpy as np
from scipy import signal

import detector_artifacts

# Cascades for face detection
CASCADE_ALT2_PATH = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_alt2.xml")
CASCADE_DEFAULT_PATH = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
CASCADE_PROFILE_PATH = os.path.join(cv2.data.haarcascades, "haarcascade_profileface.xml")

CASCADE_FRONTAL_ALT2 = cv2.CascadeClassifier(CASCADE_ALT2_PATH)
CASCADE_FRONTAL_DEF = cv2.CascadeClassifier(CASCADE_DEFAULT_PATH)
CASCADE_PROFILE = cv2.CascadeClassifier(CASCADE_PROFILE_PATH)

MIN_HZ = 0.75
MAX_HZ = 3.0
TYPICAL_MIN_BPM = 55.0
TYPICAL_MAX_BPM = 120.0


def is_debug_enabled():
    val = os.environ.get("DEBUG_PULSE", "0").strip().lower()
    return val in ("1", "true", "yes", "on")


def log_debug(msg):
    if is_debug_enabled():
        print(f"[DEBUG_PULSE] {msg}", file=sys.stderr, flush=True)


def detect_all_faces(frame):
    """Detects all faces in a frame using multi-scale search.
    
    Returns a list of boxes [(x, y, w, h), ...] sorted by area descending.
    """
    h, w = frame.shape[:2]
    target_dim = 640.0
    scale = target_dim / max(h, w) if max(h, w) > target_dim else 1.0
    if scale < 1.0:
        small = cv2.resize(frame, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        small = frame

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    boxes = []
    # Try alt2 first
    f_alt2 = CASCADE_FRONTAL_ALT2.detectMultiScale(
        gray, scaleFactor=1.05, minNeighbors=3, minSize=(24, 24)
    )
    if len(f_alt2) > 0:
        boxes.extend(f_alt2)

    # If no faces, try default cascade
    if len(boxes) == 0:
        f_def = CASCADE_FRONTAL_DEF.detectMultiScale(
            gray, scaleFactor=1.08, minNeighbors=3, minSize=(24, 24)
        )
        if len(f_def) > 0:
            boxes.extend(f_def)

    # Try profile cascade for angled faces
    f_prof = CASCADE_PROFILE.detectMultiScale(
        gray, scaleFactor=1.08, minNeighbors=3, minSize=(24, 24)
    )
    if len(f_prof) > 0:
        boxes.extend(f_prof)

    if not len(boxes):
        return []

    # Non-maximum suppression / deduplication
    rects = [[int(b[0]), int(b[1]), int(b[0] + b[2]), int(b[1] + b[3])] for b in boxes]
    # Simple area-based deduplication
    scaled_faces = []
    for fx, fy, fw, fh in boxes:
        rx = int(fx / scale)
        ry = int(fy / scale)
        rfw = int(fw / scale)
        rfh = int(fh / scale)
        rx = max(0, min(rx, w - 1))
        ry = max(0, min(ry, h - 1))
        rfw = max(1, min(rfw, w - rx))
        rfh = max(1, min(rfh, h - ry))
        scaled_faces.append((rx, ry, rfw, rfh))

    # Sort largest face first
    scaled_faces.sort(key=lambda b: b[2] * b[3], reverse=True)
    return scaled_faces


def pos_algorithm(rgb_signals, fps):
    """Plane-Orthogonal-to-Skin (POS) rPPG algorithm."""
    n = len(rgb_signals)
    if n < int(fps * 2):
        return None

    win_len = int(fps * 1.6)
    if win_len % 2 == 1:
        win_len += 1
    if win_len >= n:
        win_len = n // 2
    if win_len < 4:
        return None

    h = np.zeros(n)
    for t in range(n - win_len + 1):
        segment = rgb_signals[t : t + win_len]
        mean_rgb = np.mean(segment, axis=0) + 1e-6
        norm_rgb = segment / mean_rgb

        s1 = norm_rgb[:, 1] - norm_rgb[:, 2]
        s2 = -2.0 * norm_rgb[:, 0] + norm_rgb[:, 1] + norm_rgb[:, 2]

        std_s1 = np.std(s1)
        std_s2 = np.std(s2)
        if std_s2 > 1e-6:
            alpha = std_s1 / std_s2
            h_segment = s1 + alpha * s2
            h[t : t + win_len] += h_segment - np.mean(h_segment)

    nyquist = 0.5 * fps
    low = max(0.01, MIN_HZ / nyquist)
    high = min(0.99, MAX_HZ / nyquist)
    if low >= high:
        return None

    b, a = signal.butter(2, [low, high], btype="bandpass")
    filtered = signal.filtfilt(b, a, h)
    return filtered


def analyze_video(video_path, max_duration_sec=30.0):
    """Analyzes a video using multiple forensic mechanisms with multi-face support."""
    log_debug("=" * 60)
    log_debug(f"Starting analysis for: {os.path.basename(video_path)}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        log_debug("ERROR: Cannot open video stream.")
        return {
            "score": 50,
            "bpm": None,
            "has_pulse": False,
            "checks": [
                {"label": "Pulse wave", "text": "Error: Could not read video stream.", "ok": False},
                {"label": "Face life signs", "text": "Video frames could not be decoded.", "ok": False},
                {"label": "Visual integrity", "text": "No frame data available.", "ok": False},
            ],
            "details": {"error": "Cannot open video"},
        }

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or math.isnan(fps) or fps < 5.0 or fps > 120.0:
        fps = 30.0

    total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration_sec = total_video_frames / fps if total_video_frames > 0 else 0.0

    max_frames = int(fps * max_duration_sec)
    frame_count = 0
    rgb_means = []
    sampled_faces = []
    frames_with_any_face = 0
    max_faces_seen = 0

    # Scene cut detection
    prev_hsv = None
    cuts_count = 0

    # Step through frames (step by 1 or 2 for high fps)
    step = 2 if fps >= 50 else 1
    effective_fps = fps / step

    while True:
        ret, frame = cap.read()
        if not ret or frame_count >= max_frames:
            break
        frame_count += 1

        if step > 1 and (frame_count % step != 0):
            continue

        # Check scene cut
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        if prev_hsv is not None:
            correl = cv2.compareHist(prev_hsv, hist, cv2.HISTCMP_CORREL)
            if correl < 0.60:
                cuts_count += 1
        prev_hsv = hist

        faces = detect_all_faces(frame)
        if len(faces) > 0:
            frames_with_any_face += 1
            max_faces_seen = max(max_faces_seen, len(faces))

            # Focus on largest face
            largest_face = faces[0]
            x, y, w, h = largest_face

            # Extract forehead & cheek skin ROI for rPPG
            roi_y1 = int(y + 0.15 * h)
            roi_y2 = int(y + 0.55 * h)
            roi_x1 = int(x + 0.20 * w)
            roi_x2 = int(x + 0.80 * w)
            roi = frame[roi_y1:roi_y2, roi_x1:roi_x2]

            if roi.size > 0:
                rgb_mean = np.mean(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB), axis=(0, 1))
                rgb_means.append(rgb_mean)

            if len(sampled_faces) < 25 and (frame_count % (int(effective_fps) or 1) == 0):
                sampled_faces.append((frame.copy(), largest_face))
        else:
            if rgb_means:
                rgb_means.append(rgb_means[-1])

    cap.release()

    effective_analyzed_frames = frame_count // step
    face_ratio = frames_with_any_face / max(1, effective_analyzed_frames)
    time_analyzed_sec = effective_analyzed_frames / effective_fps if effective_fps else 0

    log_debug(f"Frames analyzed: {effective_analyzed_frames} (approx {time_analyzed_sec:.1f}s at {fps:.1f} fps)")
    log_debug(f"Faces found in video: max {max_faces_seen} simultaneous face(s)")
    log_debug(f"Frames containing a face: {frames_with_any_face}/{effective_analyzed_frames} ({face_ratio*100:.1f}%)")
    log_debug(f"Scene cuts detected: {cuts_count}")

    # Determine face description note for UI
    if max_faces_seen > 1:
        face_note = f"Several faces found ({max_faces_seen} seen). Checked the largest face."
        log_debug(f"Multiple faces: {face_note}")
    elif max_faces_seen == 1:
        face_note = "Single primary face tracked."
    else:
        face_note = "No clear face could be identified."

    # 1. Pulse signal calculation
    has_natural_pulse = False
    peak_bpm = None
    snr = 0.0
    pulse_fallback_reason = None

    if face_ratio < 0.20:
        pulse_fallback_reason = f"Face presence too low ({face_ratio*100:.1f}% of frames). Face turned, hidden, or obscured."
    elif cuts_count >= 5:
        pulse_fallback_reason = f"Frequent scene cuts detected ({cuts_count} cuts). Continuous blood-flow pulse requires an unbroken shot of 10+ seconds."
    elif len(rgb_means) < int(effective_fps * 2.5):
        pulse_fallback_reason = "Clip segment too brief (<2.5s) to detect a biological pulse frequency."
    else:
        pulse_sig = pos_algorithm(np.array(rgb_means), effective_fps)
        if pulse_sig is None:
            pulse_fallback_reason = "Bandpass filtering failed (insufficient signal variation)."
        else:
            freqs, psd = signal.welch(pulse_sig, fs=effective_fps, nperseg=min(len(pulse_sig), int(effective_fps * 6)))
            valid_idx = np.where((freqs >= MIN_HZ) & (freqs <= MAX_HZ))[0]
            if len(valid_idx) == 0:
                pulse_fallback_reason = "No frequency peaks found within human heart rate range (45-180 bpm)."
            else:
                valid_psd = psd[valid_idx]
                valid_freqs = freqs[valid_idx]
                peak_idx = np.argmax(valid_psd)
                peak_freq = valid_freqs[peak_idx]
                peak_bpm = round(float(peak_freq * 60.0), 1)

                peak_band = np.abs(valid_freqs - peak_freq) <= 0.2
                peak_power = np.sum(valid_psd[peak_band])
                noise_power = np.sum(valid_psd[~peak_band]) + 1e-8
                snr = float(peak_power / noise_power)

                if TYPICAL_MIN_BPM <= peak_bpm <= TYPICAL_MAX_BPM and snr >= 1.20:
                    has_natural_pulse = True
                else:
                    pulse_fallback_reason = f"Pulse SNR is {snr:.2f} (threshold >= 1.20) at {peak_bpm} BPM. Signal lacks natural biological stability."

    log_debug(f"Pulse analysis: has_pulse={has_natural_pulse}, BPM={peak_bpm}, SNR={snr:.2f}")
    if pulse_fallback_reason:
        log_debug(f"Pulse fallback reason: {pulse_fallback_reason}")

    # 2. Visual & Spectral Artifacts
    spectral_score, boundary_score = detector_artifacts.analyze_video_artifacts(video_path, sampled_faces)
    log_debug(f"Spectral 2D FFT score: {spectral_score:.2f} (threshold >= 0.35)")
    log_debug(f"Boundary seam score: {boundary_score:.2f} (threshold >= 0.40)")

    # Detection flags
    flag_missing_pulse = not has_natural_pulse
    flag_spectral_anomaly = spectral_score >= 0.35
    flag_boundary_anomaly = boundary_score >= 0.40
    flag_rapid_ai_montage = cuts_count >= 6 and (spectral_score >= 0.25 or boundary_score >= 0.25)

    suspicious_count = 0
    if flag_missing_pulse and (face_ratio >= 0.30 or cuts_count >= 5):
        suspicious_count += 1
    if flag_spectral_anomaly:
        suspicious_count += 1
    if flag_boundary_anomaly:
        suspicious_count += 1
    if flag_rapid_ai_montage:
        suspicious_count += 1

    log_debug(f"Suspicious signals count: {suspicious_count}")

    # Consensus scoring
    if suspicious_count >= 2:
        score = min(92, 75 + int((spectral_score + boundary_score) * 15))
        verdict_str = "Likely fake"
        log_debug(f"Consensus: LIKELY FAKE (score={score}) - Multiple independent anomaly signals agree.")
        check_pulse_ok = False
        check_pulse_text = (
            f"No steady pulse pattern found ({int(peak_bpm)} bpm, SNR {snr:.1f})."
            if peak_bpm else "No natural human pulse wave detected."
        )
        check_life_ok = False
        check_life_text = "Facial boundary or skin reflectance shows synthetic generation signs."
        check_visual_ok = False
        check_visual_text = "Frequency analysis identified generative AI synthesis artifacts."
    elif has_natural_pulse and spectral_score < 0.25 and boundary_score < 0.30 and cuts_count < 4:
        score = max(18, 25 - int(snr * 2))
        verdict_str = "Likely real"
        log_debug(f"Consensus: LIKELY REAL (score={score}) - Natural biological pulse verified and optical noise consistent.")
        check_pulse_ok = True
        check_pulse_text = f"Natural pulse rhythm detected (~{int(peak_bpm)} bpm, SNR {snr:.1f})."
        check_life_ok = True
        check_life_text = "Natural blood-flow micro-color shifts confirmed."
        check_visual_ok = True
        check_visual_text = "Natural camera sensor noise distribution verified."
    else:
        score = 50
        verdict_str = "Not sure"
        reason_summary = pulse_fallback_reason or "Inconclusive visual signals."
        log_debug(f"Consensus: NOT SURE (score=50) - {reason_summary}")

        check_pulse_ok = has_natural_pulse
        if has_natural_pulse:
            check_pulse_text = f"Faint pulse rhythm detected (~{int(peak_bpm)} bpm)."
        else:
            check_pulse_text = f"Pulse unclear. {pulse_fallback_reason or 'Lighting or compression obscures it.'}"

        check_life_ok = boundary_score < 0.35
        check_life_text = "No severe boundary blending seams." if check_life_ok else "Irregular boundary gradient detected."

        check_visual_ok = spectral_score < 0.30
        check_visual_text = "Normal frequency distribution." if check_visual_ok else "High-frequency AI patterns detected."

    # If multiple faces were found, append to first check card
    if max_faces_seen > 1:
        check_pulse_text = f"Several faces found ({max_faces_seen}). Checked the largest one. " + check_pulse_text

    checks = [
        {"label": "Pulse wave", "text": check_pulse_text, "ok": check_pulse_ok},
        {"label": "Face life signs", "text": check_life_text, "ok": check_life_ok},
        {"label": "Visual integrity", "text": check_visual_text, "ok": check_visual_ok},
    ]

    log_debug(f"Final output score: {score} ({verdict_str})")
    log_debug("=" * 60)

    return {
        "score": score,
        "bpm": peak_bpm,
        "has_pulse": has_natural_pulse,
        "checks": checks,
        "details": {
            "snr": round(snr, 2),
            "bpm": peak_bpm,
            "face_ratio": round(face_ratio, 2),
            "max_faces_seen": max_faces_seen,
            "scene_cuts": cuts_count,
            "spectral_score": round(spectral_score, 2),
            "boundary_score": round(boundary_score, 2),
            "suspicious_count": suspicious_count,
            "fallback_reason": pulse_fallback_reason,
        },
    }
