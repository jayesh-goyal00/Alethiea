"""Central hardware device selection and memory management for Apple Silicon (M-series).

Provides:
- Safe MPS detection with operational verification and automatic CPU fallback.
- Memory cleanup utilities (cache clearing, garbage collection).
- Process RAM monitoring using standard library resource module.
"""
import gc
import os
import resource
import sys
import torch

_DEVICE = None


def get_device(force_cpu: bool = False) -> torch.device:
    """Returns optimal PyTorch device for Apple Silicon (MPS with CPU fallback)."""
    global _DEVICE
    if force_cpu:
        return torch.device("cpu")

    if _DEVICE is not None:
        return _DEVICE

    # Allow environment override
    override = os.environ.get("ALETHEIA_DEVICE", "").strip().lower()
    if override == "cpu":
        _DEVICE = torch.device("cpu")
        return _DEVICE
    elif override == "mps":
        _DEVICE = torch.device("mps")
        return _DEVICE

    # Check Apple Silicon MPS availability
    if torch.backends.mps.is_available() and torch.backends.mps.is_built():
        try:
            # Verify MPS can actually execute a basic tensor operation
            test_tensor = torch.zeros((1, 1), device="mps")
            _ = test_tensor + 1.0
            del test_tensor
            _DEVICE = torch.device("mps")
            print("[DEVICE] Apple Silicon MPS (Metal Performance Shaders) active", file=sys.stderr)
            return _DEVICE
        except Exception as e:
            print(f"[DEVICE] MPS operational check failed ({e}). Falling back to CPU.", file=sys.stderr)

    _DEVICE = torch.device("cpu")
    print("[DEVICE] Running on CPU", file=sys.stderr)
    return _DEVICE


def cleanup_memory():
    """Releases cached GPU memory and forces garbage collection."""
    gc.collect()
    if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
        try:
            torch.mps.empty_cache()
        except Exception:
            pass


def get_memory_info() -> dict:
    """Returns current process memory metrics in MB using standard resource module."""
    # On macOS ru_maxrss is reported in bytes; on Linux in kilobytes
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        rss_mb = usage / (1024 * 1024)
    else:
        rss_mb = usage / 1024
    return {
        "max_rss_mb": round(rss_mb, 1),
    }
