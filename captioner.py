"""Generate SRT subtitles from Gemini transcript and burn into clips."""
import os
import tempfile
from utils import seconds_to_srt_time, run_ffmpeg

WORDS_PER_LINE = 4      # max words per subtitle line
MAX_LINE_DURATION = 2.5 # max seconds a subtitle line stays on screen


def _group_words_into_lines(words_with_times: list[tuple[str, float]], clip_start: float) -> list[dict]:
    """
    Group word-timestamp pairs into subtitle lines.
    Returns list of {start, end, text} dicts (times relative to clip start).
    """
    if not words_with_times:
        return []

    lines = []
    current_words = []
    current_start = None

    for word, abs_time in words_with_times:
        rel_time = abs_time - clip_start
        if rel_time < -1.0:
            continue  # word is before this clip

        if current_start is None:
            current_start = max(0.0, rel_time)

        current_words.append((word, rel_time))

        line_duration = rel_time - current_start
        if len(current_words) >= WORDS_PER_LINE or line_duration >= MAX_LINE_DURATION:
            line_end = rel_time + 0.3
            lines.append({
                "start": current_start,
                "end": line_end,
                "text": " ".join(w for w, _ in current_words)
            })
            current_words = []
            current_start = None

    # Flush remaining words
    if current_words:
        last_time = current_words[-1][1]
        lines.append({
            "start": current_start,
            "end": last_time + 1.0,
            "text": " ".join(w for w, _ in current_words)
        })

    return lines


def generate_srt(transcript: list, clip_start: float = 0.0) -> str:
    """
    Generate SRT content from a transcript.

    transcript: list of [word, timestamp] pairs from Gemini
    clip_start: absolute timestamp where the clip starts (to make relative)
    """
    if not transcript:
        return ""

    # Normalise: accept [[word, time], ...] or [[word, time], ...]
    words_with_times = []
    for entry in transcript:
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            word, t = entry[0], entry[1]
            if isinstance(t, (int, float)):
                words_with_times.append((str(word), float(t)))

    if not words_with_times:
        return ""

    lines = _group_words_into_lines(words_with_times, clip_start)

    srt_parts = []
    for i, line in enumerate(lines, start=1):
        srt_parts.append(
            f"{i}\n"
            f"{seconds_to_srt_time(line['start'])} --> {seconds_to_srt_time(line['end'])}\n"
            f"{line['text']}\n"
        )

    return "\n".join(srt_parts)


def burn_captions(
    input_path: str,
    srt_content: str,
    output_path: str,
) -> str:
    """
    Burn SRT subtitles into a video using FFmpeg.
    If srt_content is empty, just copies the file.
    Returns output_path.
    """
    if not srt_content.strip():
        # No captions — just copy
        run_ffmpeg(["-i", input_path, "-c", "copy", output_path],
                   f"copy (no captions) {os.path.basename(output_path)}")
        return output_path

    # Write SRT to a temp file
    srt_fd, srt_path = tempfile.mkstemp(suffix=".srt")
    try:
        with os.fdopen(srt_fd, "w", encoding="utf-8") as f:
            f.write(srt_content)

        # FFmpeg subtitles filter — escape backslashes for Windows paths
        srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")

        subtitle_style = (
            "FontName=Arial,"
            "FontSize=16,"
            "Bold=1,"
            "Outline=2,"
            "PrimaryColour=&H00FFFFFF,"  # white
            "OutlineColour=&H00000000,"  # black outline
            "Alignment=2,"               # bottom center
            "MarginV=40"
        )

        run_ffmpeg([
            "-i", input_path,
            "-vf", f"subtitles='{srt_escaped}':force_style='{subtitle_style}'",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-crf", "23",
            output_path
        ], f"burn captions {os.path.basename(output_path)}")
    finally:
        try:
            os.remove(srt_path)
        except OSError:
            pass

    return output_path
