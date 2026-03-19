"""Split long videos into Gemini-compatible segments."""
import os
from utils import run_ffprobe, run_ffmpeg, ensure_dir

# Gemini 2.0 Flash supports ~45 min video with audio
GEMINI_MAX_SECONDS = 2700  # 45 minutes
CHUNK_DURATION = 1200       # 20 minutes per chunk
OVERLAP = 90                # 90 second overlap between chunks


def get_duration(video_path: str) -> float:
    """Return video duration in seconds."""
    output = run_ffprobe([
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ])
    return float(output)


def chunk_video(video_path: str, temp_dir: str) -> list[tuple[float, str]]:
    """
    Split video into chunks if longer than GEMINI_MAX_SECONDS.

    Returns a list of (start_offset_seconds, chunk_file_path).
    For short videos, returns [(0.0, video_path)] with no splitting.
    """
    duration = get_duration(video_path)

    if duration <= GEMINI_MAX_SECONDS:
        return [(0.0, video_path)]

    print(f"  Video is {duration/60:.1f} min — splitting into {CHUNK_DURATION//60}-min chunks...")
    ensure_dir(temp_dir)

    chunks = []
    start = 0.0
    chunk_index = 0

    while start < duration:
        chunk_path = os.path.join(temp_dir, f"chunk_{chunk_index:03d}.mp4")
        actual_duration = min(CHUNK_DURATION + OVERLAP, duration - start)

        run_ffmpeg([
            "-ss", str(start),
            "-i", video_path,
            "-t", str(actual_duration),
            "-c", "copy",
            chunk_path
        ], f"chunk {chunk_index}")

        chunks.append((start, chunk_path))
        start += CHUNK_DURATION  # advance by chunk size (not including overlap)
        chunk_index += 1

    print(f"  Created {len(chunks)} chunks.")
    return chunks
