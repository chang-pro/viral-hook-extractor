"""Cut clips from source video using FFmpeg."""
import os
from utils import run_ffmpeg


PAD_START = 1.5   # seconds to add before hook start
PAD_END = 1.0     # seconds to add after hook end


def cut_clip(
    source_path: str,
    start: float,
    end: float,
    output_path: str,
    video_duration: float = None,
    pad_start: float = PAD_START,
    pad_end: float = PAD_END,
) -> str:
    """
    Cut a clip from source_path between start and end (with padding).
    Returns output_path.
    """
    actual_start = max(0.0, start - pad_start)
    actual_end = end + pad_end

    if video_duration is not None:
        actual_end = min(actual_end, video_duration)

    duration = actual_end - actual_start

    run_ffmpeg([
        "-ss", f"{actual_start:.3f}",
        "-i", source_path,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        "-crf", "23",
        output_path
    ], f"cut clip {os.path.basename(output_path)}")

    return output_path
