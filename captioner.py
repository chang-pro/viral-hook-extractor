"""Generate ASS karaoke captions and burn them into clips."""
import os
import re
import tempfile

from utils import run_ffmpeg


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Hook,Arial,80,&H00FFFFFF,&H0000A5FF,&H00101010,&H64000000,1,0,0,0,100,100,0,0,1,3,0,8,80,80,240,1
Style: Caption,Arial,64,&H00FFFFFF,&H0000A5FF,&H00101010,&H64000000,1,0,0,0,100,100,0,0,1,3,0,2,70,70,160,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""


def _seconds_to_ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis == 100:
        secs += 1
        centis = 0
    if secs == 60:
        minutes += 1
        secs = 0
    if minutes == 60:
        hours += 1
        minutes = 0
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _escape_ass_text(text: str) -> str:
    text = text.replace("\\", r"\\")
    text = text.replace("{", r"\{").replace("}", r"\}")
    return text.replace("\n", r"\N")


def _normalize_transcript(transcript: list) -> list[tuple[str, float]]:
    words = []
    for entry in transcript or []:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        word, timestamp = entry[0], entry[1]
        if not isinstance(timestamp, (int, float)):
            continue
        clean_word = str(word).strip()
        if clean_word:
            words.append((clean_word, float(timestamp)))
    return sorted(words, key=lambda item: item[1])


def _parse_srt_timestamp(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis) / 1000.0
    )


def _iter_srt_blocks(srt_content: str):
    blocks = re.split(r"\r?\n\s*\r?\n", srt_content.strip())
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        if "-->" not in lines[0] and len(lines) >= 3 and "-->" in lines[1]:
            lines = lines[1:]
        if "-->" not in lines[0]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[0].split("-->", 1)]
        text = " ".join(lines[1:]).strip()
        if not text:
            continue
        yield {
            "start": _parse_srt_timestamp(start_raw),
            "end": _parse_srt_timestamp(end_raw),
            "text": text,
        }


def _srt_to_ass_events(
    srt_content: str,
    clip_start: float,
    clip_end: float | None = None,
) -> list[str]:
    events = []
    for cue in _iter_srt_blocks(srt_content):
        if cue["end"] <= clip_start:
            continue
        if clip_end is not None and cue["start"] >= clip_end:
            continue
        rel_start = max(0.0, cue["start"] - clip_start)
        rel_end = cue["end"] - clip_start
        if clip_end is not None:
            rel_end = min(rel_end, clip_end - clip_start)
        if rel_end <= rel_start:
            continue
        text = _escape_ass_text(cue["text"])
        events.append(
            "Dialogue: 0,{start},{end},Caption,,0,0,0,,{text}".format(
                start=_seconds_to_ass_time(rel_start),
                end=_seconds_to_ass_time(rel_end),
                text=text,
            )
        )
    return events


def _transcript_to_ass_events(
    transcript: list,
    clip_start: float = 0.0,
    hook_line: str = "",
) -> list[str]:
    words = _normalize_transcript(transcript)
    if not words and not hook_line:
        return []

    events = []

    if hook_line:
        events.append(
            "Dialogue: 0,{start},{end},Hook,,0,0,0,,{text}".format(
                start=_seconds_to_ass_time(0.0),
                end=_seconds_to_ass_time(1.8),
                text=_escape_ass_text(hook_line.upper()),
            )
        )

    if not words:
        return events

    for index, (word, abs_time) in enumerate(words):
        rel_start = max(0.0, abs_time - clip_start)
        next_abs = words[index + 1][1] if index + 1 < len(words) else abs_time + 0.55
        rel_end = max(rel_start + 0.12, next_abs - clip_start)
        duration_cs = max(12, int(round((rel_end - rel_start) * 100)))
        text = "{\\k%d}%s" % (duration_cs, _escape_ass_text(word))
        events.append(
            "Dialogue: 0,{start},{end},Caption,,0,0,0,,{text}".format(
                start=_seconds_to_ass_time(rel_start),
                end=_seconds_to_ass_time(rel_end),
                text=text,
            )
        )

    return events


def generate_ass(
    transcript: list,
    clip_start: float = 0.0,
    hook_line: str = "",
) -> str:
    events = _transcript_to_ass_events(transcript, clip_start=clip_start, hook_line=hook_line)
    if not events:
        return ""
    return ASS_HEADER + "\n".join(events) + "\n"


def generate_ass_from_srt(
    srt_content: str,
    clip_start: float,
    clip_end: float | None = None,
    hook_line: str = "",
) -> str:
    events = []
    if hook_line:
        events.append(
            "Dialogue: 0,{start},{end},Hook,,0,0,0,,{text}".format(
                start=_seconds_to_ass_time(0.0),
                end=_seconds_to_ass_time(1.8),
                text=_escape_ass_text(hook_line.upper()),
            )
        )
    events.extend(_srt_to_ass_events(srt_content, clip_start=clip_start, clip_end=clip_end))
    if not events:
        return ""
    return ASS_HEADER + "\n".join(events) + "\n"


def burn_captions(input_path: str, ass_content: str, output_path: str) -> str:
    """Burn ASS subtitles into a video using FFmpeg."""
    if not ass_content.strip():
        run_ffmpeg(
            ["-i", input_path, "-c", "copy", output_path],
            f"copy (no captions) {os.path.basename(output_path)}",
        )
        return output_path

    ass_fd, ass_path = tempfile.mkstemp(suffix=".ass")
    try:
        with os.fdopen(ass_fd, "w", encoding="utf-8") as handle:
            handle.write(ass_content)

        ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
        run_ffmpeg(
            [
                "-i",
                input_path,
                "-vf",
                f"ass='{ass_escaped}'",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-preset",
                "fast",
                "-crf",
                "23",
                output_path,
            ],
            f"burn captions {os.path.basename(output_path)}",
        )
    finally:
        try:
            os.remove(ass_path)
        except OSError:
            pass

    return output_path
