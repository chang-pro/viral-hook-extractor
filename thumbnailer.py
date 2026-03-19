"""Export still thumbnails for detected hooks."""
import os

from utils import ensure_dir, run_ffmpeg


def extract_thumbnail(
    source_path: str,
    timestamp: float,
    output_path: str,
    width: int = 1080,
) -> str:
    """Extract one frame and scale it to a predictable width."""
    ensure_dir(os.path.dirname(output_path) or ".")
    run_ffmpeg(
        [
            "-ss",
            f"{max(0.0, timestamp):.3f}",
            "-i",
            source_path,
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:-2",
            output_path,
        ],
        f"extract thumbnail {os.path.basename(output_path)}",
    )
    return output_path
