"""Biological Pulse Detector using Remote Photoplethysmography (rPPG - POS Algorithm).

Analyzes subtle facial skin color variations associated with human blood circulation.
Requirements:
- rPPG must be optional.
- If a video has no usable face, marks rPPG as UNAVAILABLE.
- If a video consists of rapid cuts (< 3s continuous shot), marks rPPG as UNAVAILABLE.
- Never classifies a video as fake merely because rPPG cannot analyse it.
"""
import math
import os
import sys
import cv2
import numpy as np
from scipy import signal

from device import cleanup_memory

# Bundled Haar Cascade for skin ROI detection within face
CASCADE_PATH = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
FACE_CASCADE = cv2.CascadeClassifier(CASCADE_PATH)

MIN_HZ = 0.75      # 45 bpm
MAX_HZ = 3.0       # 180 bpm
TYPICAL_MIN_BPM = 55.0
TYPICAL_MAX_BPM = 120.0


def extract_face_roi(frame):
    """Detects primary frontal face and returns forehead/cheek skin ROI."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = FACE_CASCADE.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=4, minSize=(50, 50)
    )
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    # Forehead & upper cheek: 15% to 55% height, 20% to 80% width
    roi_y1 = int(y + 0.15 * h)
    roi_y2 = int(y + 0.55 * h)
    roi_x1 = int(x + 0.20 * w)
    roi_x2 = int(x + 0.80 * w)
    return frame[roi_y1:roi_y2, roi_x1:roi_x2]


def pos_algorithm(rgb_signals, fps):
    """Plane-Orthogonal-to-Skin (POS) rPPG algorithm (Wang et al., 2017)."""
    n = len(rgb_signals)
    if n < int(fps * 2.0):
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


def analyze_video_pulse(video_path: str, start_sec: float = 0.0, end_sec: float = None, max_frames: int = 450) -> dict:
    """Analyzes pulse signals across a continuous video shot.
    
    Returns standard detector dict:
      detector_name, status, raw_score, calibrated_confidence, quality_info, findings, limitations, error_details
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {
            "detector_name": "rPPG Biological Pulse",
            "status": "failed",
            "raw_score": None,
            "calibrated_confidence": 0.0,
            "quality_info": {"error": "Cannot open video file"},
            "findings": ["Video file could not be opened for pulse reading."],
            "limitations": ["Corrupt or unsupported video container."],
            "error_details": "Failed to open video capture",
        }

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or math.isnan(fps) or fps < 5.0 or fps > 120.0:
        fps = 30.0

    # Position at start_sec
    start_frame = int(start_sec * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    limit_frames = int((end_sec - start_sec) * fps) if end_sec else max_frames
    limit_frames = min(limit_frames, max_frames)

    frame_count = 0
    rgb_means = []
    face_detected_frames = 0

    while frame_count < limit_frames:
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1

        roi = extract_face_roi(frame)
        if roi is not None and roi.size > 0:
            face_detected_frames += 1
            rgb_mean = np.mean(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB), axis=(0, 1))
            rgb_means.append(rgb_mean)
        else:
            if rgb_means:
                rgb_means.append(rgb_means[-1])

    cap.release()

    face_ratio = face_detected_frames / max(1, frame_count)
    if face_ratio < 0.25 or len(rgb_means) < int(fps * 2.5):
        return {
            "detector_name": "rPPG Biological Pulse",
            "status": "unavailable",
            "raw_score": 50,
            "calibrated_confidence": 0.3,
            "quality_info": {
                "face_ratio": round(face_ratio, 2),
                "frames_analyzed": frame_count,
                "reason": "Insufficient facial visibility in continuous shot",
            },
            "findings": [
                "No human face tracked continuously for long enough to read micro-vascular pulse.",
            ],
            "limitations": [
                "rPPG requires continuous visible facial skin across at least 2.5 seconds.",
                "Absence of pulse detection does NOT indicate manipulation.",
            ],
            "error_details": None,
            "checks": [
                {"label": "Pulse wave", "text": "No clear face found for long enough to read a pulse.", "ok": False},
                {"label": "Face life signs", "text": "Skin regions could not be tracked steadily.", "ok": False},
                {"label": "Heart rate signal", "text": "No stable heartbeat rhythm found.", "ok": False},
            ],
        }

    pulse_signal = pos_algorithm(np.array(rgb_means), fps)
    if pulse_signal is None or len(pulse_signal) < int(fps * 2.0):
        return {
            "detector_name": "rPPG Biological Pulse",
            "status": "unavailable",
            "raw_score": 50,
            "calibrated_confidence": 0.3,
            "quality_info": {"reason": "Signal processing window insufficient"},
            "findings": ["Pulse wave signal is too short or discontinuous to extract heart rate."],
            "limitations": ["Lighting shifts or subject head movement obscured pulse signal."],
            "error_details": None,
            "checks": [
                {"label": "Pulse wave", "text": "Pulse wave is unclear or too short to read.", "ok": False},
                {"label": "Face life signs", "text": "Skin color variations are uneven.", "ok": False},
                {"label": "Heart rate signal", "text": "No distinct heartbeat rhythm found.", "ok": False},
            ],
        }

    # Spectral analysis with Welch PSD
    freqs, psd = signal.welch(pulse_signal, fs=fps, nperseg=min(len(pulse_signal), int(fps * 5)))
    valid_idx = np.where((freqs >= MIN_HZ) & (freqs <= MAX_HZ))[0]

    if len(valid_idx) == 0:
        snr = 0.0
        peak_bpm = None
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

    has_natural_pulse = (
        peak_bpm is not None
        and TYPICAL_MIN_BPM <= peak_bpm <= TYPICAL_MAX_BPM
        and snr >= 1.2
    )

    if has_natural_pulse:
        raw_score = 22  # Strong indication of authentic biological pulse
        confidence = min(0.92, 0.6 + snr * 0.1)
        findings = [
            f"Natural cardiovascular pulse wave detected (~{int(peak_bpm)} bpm).",
            f"Steady skin blood-flow micro-blush rhythm identified (SNR {snr:.1f}).",
        ]
        checks = [
            {"label": "Pulse wave", "text": f"Natural pulse rhythm detected (~{int(peak_bpm)} bpm).", "ok": True},
            {"label": "Face life signs", "text": "Healthy blood-flow color changes detected in skin.", "ok": True},
            {"label": "Heart rate signal", "text": f"Steady heartbeat pattern identified (SNR {snr:.1f}).", "ok": True},
        ]
    else:
        raw_score = 50  # Neutral: inconclusive
        confidence = 0.45
        reason = "Pulse signal is obscured or irregular."
        if peak_bpm and (peak_bpm < TYPICAL_MIN_BPM or peak_bpm > TYPICAL_MAX_BPM):
            reason = f"Irregular frequency found (~{int(peak_bpm)} bpm). Compression or camera motion likely obscures it."
        findings = [reason]
        checks = [
            {"label": "Pulse wave", "text": "Weak or inconsistent pulse signal found.", "ok": False},
            {"label": "Face life signs", "text": "Skin color variations do not form a steady rhythm.", "ok": False},
            {"label": "Heart rate signal", "text": reason, "ok": False},
        ]

    cleanup_memory()

    return {
        "detector_name": "rPPG Biological Pulse",
        "status": "available",
        "raw_score": raw_score,
        "calibrated_confidence": round(confidence, 2),
        "quality_info": {
            "snr": round(snr, 2),
            "bpm": peak_bpm,
            "face_ratio": round(face_ratio, 2),
            "frames_analyzed": frame_count,
        },
        "findings": findings,
        "limitations": [
            "Severe video recompression or poor room lighting can hide real pulse signals.",
            "Absence of pulse signal alone does NOT prove manipulation.",
        ],
        "error_details": None,
        "checks": checks,
    }
