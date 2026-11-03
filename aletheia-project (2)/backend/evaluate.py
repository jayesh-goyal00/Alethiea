"""Evaluates deepfake detection candidate methods on test videos.

Runs candidate detectors on all clips in:
  - test_videos/real/
  - test_videos/fake/

Prints a structured comparison table with detection scores and processing time.
"""
import glob
import os
import sys
import time

# Ensure backend directory is in path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import detector_composite
import videoinfo


def get_verdict(score):
    if score < 40:
        return "Likely real"
    elif score < 70:
        return "Not sure"
    else:
        return "Likely fake"


def evaluate_folder(folder_path, label):
    extensions = ("*.mp4", "*.mov", "*.webm", "*.mkv")
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(folder_path, ext)))
        files.extend(glob.glob(os.path.join(folder_path, ext.upper())))
    files = sorted(set(files))

    results = []
    for file_path in files:
        fname = os.path.basename(file_path)
        start_time = time.time()
        try:
            info = videoinfo.probe(file_path)
            fps_str = info.get("fps", "?")
            dur_str = info.get("duration", "?")
        except Exception:
            fps_str = "?"
            dur_str = "?"

        # Run Composite Detector (pulse rPPG + 2D FFT spectral artifacts + boundary blending)
        det_res = detector_composite.analyze_video(file_path)
        elapsed = time.time() - start_time

        bpm_display = str(int(det_res["bpm"])) if det_res.get("bpm") else "-"
        verdict = get_verdict(det_res["score"])

        results.append({
            "category": label,
            "filename": fname,
            "duration": dur_str,
            "fps": fps_str,
            "score": det_res["score"],
            "bpm": bpm_display,
            "verdict": verdict,
            "time_sec": round(elapsed, 2),
            "checks": det_res.get("checks", []),
        })
    return results


def print_table(results):
    print("=" * 90)
    print(f"{'Category':<10} | {'Filename':<30} | {'Dur':<6} | {'FPS':<6} | {'Score':<6} | {'BPM':<5} | {'Verdict':<12} | {'Time (s)':<8}")
    print("-" * 90)
    for r in results:
        fname = r["filename"]
        if len(fname) > 28:
            fname = fname[:25] + "..."
        print(
            f"{r['category']:<10} | {fname:<30} | {r['duration']:<6} | {r['fps']:<6} | "
            f"{r['score']:<6} | {r['bpm']:<5} | {r['verdict']:<12} | {r['time_sec']:<8.2f}"
        )
    print("=" * 90)


def main():
    real_dir = os.path.join(PROJECT_ROOT, "test_videos", "real")
    fake_dir = os.path.join(PROJECT_ROOT, "test_videos", "fake")

    # Also accept specific video passed on CLI
    cli_files = [f for f in sys.argv[1:] if os.path.isfile(f)]

    all_results = []
    if cli_files:
        print(f"Analyzing {len(cli_files)} specified video(s)...")
        for f in cli_files:
            start_time = time.time()
            try:
                info = videoinfo.probe(f)
                fps_str = info.get("fps", "?")
                dur_str = info.get("duration", "?")
            except Exception:
                fps_str = "?"
                dur_str = "?"
            det_res = detector_composite.analyze_video(f)
            elapsed = time.time() - start_time
            bpm_display = str(int(det_res["bpm"])) if det_res.get("bpm") else "-"
            all_results.append({
                "category": "CLI",
                "filename": os.path.basename(f),
                "duration": dur_str,
                "fps": fps_str,
                "score": det_res["score"],
                "bpm": bpm_display,
                "verdict": get_verdict(det_res["score"]),
                "time_sec": round(elapsed, 2),
            })
    else:
        real_results = evaluate_folder(real_dir, "Real")
        fake_results = evaluate_folder(fake_dir, "Fake")
        all_results = real_results + fake_results

    if not all_results:
        print("\nNo test videos found in:")
        print(f"  - {real_dir}")
        print(f"  - {fake_dir}")
        print("\nTo evaluate detectors:")
        print("  1. Place test clips into 'test_videos/real/' and 'test_videos/fake/'.")
        print("  2. Or run: python evaluate.py /path/to/any_video.mp4\n")
        return

    print_table(all_results)

    # Print summary metrics
    real_items = [r for r in all_results if r["category"] == "Real"]
    fake_items = [r for r in all_results if r["category"] == "Fake"]

    if real_items:
        # False positives: real video marked as "Likely fake" (score >= 70)
        false_fakes = sum(1 for r in real_items if r["score"] >= 70)
        print(f"Real videos tested: {len(real_items)} | False 'fake' classifications: {false_fakes} ({false_fakes/len(real_items)*100:.1f}%)")
    if fake_items:
        caught_fakes = sum(1 for r in fake_items if r["score"] >= 70)
        print(f"Fake videos tested: {len(fake_items)} | Marked 'Likely fake': {caught_fakes} ({caught_fakes/len(fake_items)*100:.1f}%)")

    total_time = sum(r["time_sec"] for r in all_results)
    avg_time = total_time / len(all_results)
    print(f"Average analysis time per video: {avg_time:.2f}s")


if __name__ == "__main__":
    main()

