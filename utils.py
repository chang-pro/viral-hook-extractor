"""Shared utilities for the video clipper pipeline."""
import os
import subprocess
import shutil


def seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def ensure_dir(path: str) -> str:
    """Create directory if it doesn't exist, return path."""
    os.makedirs(path, exist_ok=True)
    return path


def cleanup_files(paths: list[str]) -> None:
    """Remove a list of files/directories, ignoring errors."""
    for p in paths:
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass


def run_ffmpeg(args: list[str], description: str = "") -> None:
    """Run an ffmpeg command, raise RuntimeError on failure."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        label = f" ({description})" if description else ""
        raise RuntimeError(f"FFmpeg failed{label}:\n{result.stderr.strip()}")


def run_ffprobe(args: list[str]) -> str:
    """Run an ffprobe command and return stdout."""
    cmd = ["ffprobe"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed:\n{result.stderr.strip()}")
    return result.stdout.strip()
