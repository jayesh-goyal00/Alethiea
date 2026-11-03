"""Video Preprocessing Pipeline for Aletheia on Apple Silicon.

Responsibilities:
1. Extract video metadata (fps, duration, resolution, total frames).
2. Segment video into shots using PySceneDetect (prevents comparing unrelated scenes).
3. Sample bounded batches of frames (adaptive: 16-32 frames) to protect 16GB RAM.
4. Detect faces across sampled frames using MTCNN (CPU-safe) with deduplication.
5. Identify longest continuous shot for temporal/biological pulse analysis.
"""
import os
import sys
import cv2
import numpy as np
from scenedetect import detect, ContentDetector
from facenet_pytorch import MTCNN

# MTCNN initialized on CPU to avoid MPS pooling dimension limitations
_MTCNN = None


def get_face_detector():
    global _MTCNN
    if _MTCNN is None:
        _MTCNN = MTCNN(keep_all=True, device="cpu", post_process=False)
    return _MTCNN


class VideoData:
    def __init__(self, path: str):
        self.path = path
        self.fps = 30.0
        self.duration_sec = 0.0
        self.width = 0
        self.height = 0
        self.total_frames = 0
        self.scenes = []  # list of (start_sec, end_sec)
        self.longest_shot = (0.0, 0.0)
        self.sampled_frames = []  # list of RGB uint8 arrays (bounded, max 32)
        self.sampled_frame_indices = []
        self.faces = []  # list of dicts: {'frame_idx', 'boxes', 'crops'}
        self.face_stats = {
            "max_faces_in_frame": 0,
            "frames_with_face": 0,
            "has_face": False,
            "face_coverage_ratio": 0.0,
        }


def preprocess_video(video_path: str, max_sampled_frames: int = 24) -> VideoData:
    """Preprocesses a video: probes metadata, detects scene cuts, samples bounded frames, detects faces."""
    data = VideoData(video_path)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    data.fps = fps if (fps and 5.0 <= fps <= 120.0) else 30.0
    data.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    data.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    data.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    data.duration_sec = data.total_frames / data.fps if data.fps > 0 else 0.0
    cap.release()

    # 1. Detect scenes using PySceneDetect
    try:
        scene_list = detect(video_path, ContentDetector(threshold=27.0))
        if scene_list:
            data.scenes = [(s[0].get_seconds(), s[1].get_seconds()) for s in scene_list]
        else:
            data.scenes = [(0.0, data.duration_sec)]
    except Exception as e:
        print(f"[PREPROCESSOR] Scene detection fallback ({e})", file=sys.stderr)
        data.scenes = [(0.0, data.duration_sec)]

    # 2. Find longest continuous shot
    longest_dur = 0.0
    longest_shot = (0.0, data.duration_sec)
    for start, end in data.scenes:
        dur = end - start
        if dur > longest_dur:
            longest_dur = dur
            longest_shot = (start, end)
    data.longest_shot = longest_shot

    # 3. Bounded frame sampling across the video
    sample_count = min(max_sampled_frames, max(8, data.total_frames))
    step = max(1, data.total_frames // sample_count)
    frame_indices = [i * step for i in range(sample_count) if i * step < data.total_frames]

    cap = cv2.VideoCapture(video_path)
    cur_idx = 0
    sampled_frames = []
    sampled_indices = []

    for target_idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)
        ret, frame = cap.read()
        if not ret:
            break
        # Convert to RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        sampled_frames.append(rgb)
        sampled_indices.append(target_idx)

    cap.release()
    data.sampled_frames = sampled_frames
    data.sampled_frame_indices = sampled_indices

    # 4. Multi-face detection on sampled frames
    detector = get_face_detector()
    frames_with_face = 0
    max_faces = 0

    for idx, frame_rgb in enumerate(sampled_frames):
        try:
            boxes, _ = detector.detect(frame_rgb)
        except Exception:
            boxes = None

        if boxes is not None and len(boxes) > 0:
            frames_with_face += 1
            max_faces = max(max_faces, len(boxes))
            crops = []
            valid_boxes = []
            fh, fw = frame_rgb.shape[:2]
            for b in boxes:
                x1, y1, x2, y2 = [int(v) for v in b]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(fw, x2), min(fh, y2)
                if (x2 - x1) >= 30 and (y2 - y1) >= 30:
                    valid_boxes.append((x1, y1, x2 - x1, y2 - y1))
                    crops.append(frame_rgb[y1:y2, x1:x2])
            data.faces.append({
                "sample_idx": idx,
                "frame_idx": sampled_indices[idx],
                "boxes": valid_boxes,
                "crops": crops,
            })
        else:
            data.faces.append({
                "sample_idx": idx,
                "frame_idx": sampled_indices[idx],
                "boxes": [],
                "crops": [],
            })

    total_sampled = max(1, len(sampled_frames))
    data.face_stats["max_faces_in_frame"] = max_faces
    data.face_stats["frames_with_face"] = frames_with_face
    data.face_stats["has_face"] = frames_with_face > 0
    data.face_stats["face_coverage_ratio"] = round(frames_with_face / total_sampled, 2)

    return data
