"""Pulse detector using Remote Photoplethysmography (rPPG - POS Algorithm).

Analyzes facial skin color variations across continuous frames to detect
human pulse signals and heart rate rhythm.
"""
import math
import os
import cv2
import numpy as np
from scipy import signal

# Bundled Haar Cascade for face detection
CASCADE_PATH = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
FACE_CASCADE = cv2.CascadeClassifier(CASCADE_PATH)

# Human heart rate boundaries: 45 bpm (0.75 Hz) to 180 bpm (3.0 Hz)
MIN_HZ = 0.75
MAX_HZ = 3.0
TYPICAL_MIN_BPM = 55.0
TYPICAL_MAX_BPM = 120.0


def extract_face_roi(frame):
    """Detects primary frontal face and returns forehead/cheek skin ROI."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = FACE_CASCADE.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
    )
    if len(faces) == 0:
        return None
    # Pick largest detected face
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    # Forehead & upper cheek region: 15% to 55% height, 20% to 80% width
    # This avoids eyes, mouth movements, and hair.
    roi_y1 = int(y + 0.15 * h)
    roi_y2 = int(y + 0.55 * h)
    roi_x1 = int(x + 0.20 * w)
    roi_x2 = int(x + 0.80 * w)
    return frame[roi_y1:roi_y2, roi_x1:roi_x2]


def pos_algorithm(rgb_signals, fps):
    """Plane-Orthogonal-to-Skin (POS) rPPG algorithm (Wang et al., 2017).
    
    rgb_signals: numpy array of shape (N, 3) where columns are R, G, B
    fps: frames per second
    """
    n = len(rgb_signals)
    if n < int(fps * 2):  # Need at least 2 seconds of continuous signal
        return None

    # Temporal normalization over sliding windows (e.g. 1.6s)
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
        # Mean normalize per channel
        mean_rgb = np.mean(segment, axis=0) + 1e-6
        norm_rgb = segment / mean_rgb

        # Spatial projections
        # S1 = G - B
        # S2 = -2R + G + B
        s1 = norm_rgb[:, 1] - norm_rgb[:, 2]
        s2 = -2.0 * norm_rgb[:, 0] + norm_rgb[:, 1] + norm_rgb[:, 2]

        std_s1 = np.std(s1)
        std_s2 = np.std(s2)
        if std_s2 > 1e-6:
            alpha = std_s1 / std_s2
            h_segment = s1 + alpha * s2
            # Add overlap-add
            h[t : t + win_len] += h_segment - np.mean(h_segment)

    # Bandpass filter within human pulse frequency range
    nyquist = 0.5 * fps
    low = max(0.01, MIN_HZ / nyquist)
    high = min(0.99, MAX_HZ / nyquist)
    if low >= high:
        return None

    b, a = signal.butter(2, [low, high], btype="bandpass")
    filtered = signal.filtfilt(b, a, h)
    return filtered


def analyze_pulse(video_path, max_duration_sec=30.0):
    """Analyzes pulse signals across continuous windows in a video.
    
    Returns a dict with:
      - score: integer (0-100)
      - bpm: float or None
      - has_pulse: bool
      - checks: list of check objects for the frontend
      - details: dict of metrics
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {
            "score": 50,
            "bpm": None,
            "has_pulse": False,
            "checks": [
                {"label": "Pulse wave", "text": "Could not read video stream.", "ok": False},
                {"label": "Face life signs", "text": "Video frames could not be opened.", "ok": False},
                {"label": "Heart rate signal", "text": "No signal available.", "ok": False},
            ],
            "details": {"error": "Cannot open video"},
        }

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or math.isnan(fps) or fps < 5.0 or fps > 120.0:
        fps = 30.0  # fallback assumption

    max_frames = int(fps * max_duration_sec)
    frame_count = 0
    rgb_means = []
    face_detected_frames = 0

    while True:
        ret, frame = cap.read()
        if not ret or frame_count >= max_frames:
            break
        frame_count += 1

        roi = extract_face_roi(frame)
        if roi is not None and roi.size > 0:
            face_detected_frames += 1
            # Compute mean RGB (convert BGR to RGB)
            rgb_mean = np.mean(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB), axis=(0, 1))
            rgb_means.append(rgb_mean)
        else:
            # If face is lost, keep previous or mark pause
            if rgb_means:
                rgb_means.append(rgb_means[-1])

    cap.release()

    face_ratio = (face_detected_frames / max(1, frame_count))
    if face_ratio < 0.25 or len(rgb_means) < int(fps * 3):
        # Face not clearly detected for enough frames -> Weak/unclear signal
        return {
            "score": 50,
            "bpm": None,
            "has_pulse": False,
            "checks": [
                {"label": "Pulse wave", "text": "No clear face found for long enough to read a pulse.", "ok": False},
                {"label": "Face life signs", "text": "Skin regions could not be tracked steadily.", "ok": False},
                {"label": "Heart rate signal", "text": "No stable heartbeat rhythm found.", "ok": False},
            ],
            "details": {
                "face_ratio": round(face_ratio, 2),
                "frames_analyzed": frame_count,
                "reason": "Insufficient face presence",
            },
        }

    # Run POS algorithm
    rgb_arr = np.array(rgb_means)
    pulse_signal = pos_algorithm(rgb_arr, fps)

    if pulse_signal is None or len(pulse_signal) < int(fps * 2):
        return {
            "score": 50,
            "bpm": None,
            "has_pulse": False,
            "checks": [
                {"label": "Pulse wave", "text": "Pulse wave is unclear or too short to read.", "ok": False},
                {"label": "Face life signs", "text": "Skin color variations are uneven.", "ok": False},
                {"label": "Heart rate signal", "text": "No distinct heartbeat rhythm found.", "ok": False},
            ],
            "details": {"reason": "Short or missing signal"},
        }

    # Spectral analysis using Welch's PSD
    freqs, psd = signal.welch(pulse_signal, fs=fps, nperseg=min(len(pulse_signal), int(fps * 6)))
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

        # Calculate SNR around peak (+- 0.2 Hz) vs remaining spectrum
        peak_band = np.abs(valid_freqs - peak_freq) <= 0.2
        peak_power = np.sum(valid_psd[peak_band])
        noise_power = np.sum(valid_psd[~peak_band]) + 1e-8
        snr = float(peak_power / noise_power)

    # Determine verdict and checks
    # Natural pulse: typical BPM (55-120) and reasonable SNR (> 1.2)
    has_natural_pulse = (
        peak_bpm is not None
        and TYPICAL_MIN_BPM <= peak_bpm <= TYPICAL_MAX_BPM
        and snr >= 1.2
    )

    if has_natural_pulse:
        score = 25  # Likely real
        checks = [
            {"label": "Pulse wave", "text": f"Natural pulse rhythm detected (~{int(peak_bpm)} bpm).", "ok": True},
            {"label": "Face life signs", "text": "Healthy blood-flow color changes detected in skin.", "ok": True},
            {"label": "Heart rate signal", "text": f"Steady heartbeat pattern identified (SNR {snr:.1f}).", "ok": True},
        ]
    else:
        # Weak or unclear pulse -> 50 ("Not sure")
        # Remember rule: weak pulse does NOT mean fake; it means not sure.
        score = 50
        reason_text = "Pulse signal is weak or obscured."
        if peak_bpm and (peak_bpm < TYPICAL_MIN_BPM or peak_bpm > TYPICAL_MAX_BPM):
            reason_text = f"Irregular frequency found (~{int(peak_bpm)} bpm). Lighting or compression may obscure it."
        checks = [
            {"label": "Pulse wave", "text": "Weak or inconsistent pulse signal found.", "ok": False},
            {"label": "Face life signs", "text": "Skin color variations do not form a steady rhythm.", "ok": False},
            {"label": "Heart rate signal", "text": reason_text, "ok": False},
        ]

    return {
        "score": score,
        "bpm": peak_bpm,
        "has_pulse": has_natural_pulse,
        "checks": checks,
        "details": {
            "snr": round(snr, 2),
            "bpm": peak_bpm,
            "face_ratio": round(face_ratio, 2),
            "frames_analyzed": frame_count,
        },
    }

