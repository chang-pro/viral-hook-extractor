"""Analyze video chunks with Gemini CLI and extract hooks with timestamps."""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


TYPE_MAP = {
    "humor": "funny",
    "comedy": "funny",
    "dramatic": "dramatic",
    "drama": "dramatic",
    "opening": "opening",
    "conflict": "dramatic",
    "argument": "dramatic",
    "shock": "opening",
}

HOOK_PROFILES = {
    "hot": {
        "label": "hot hook",
        "prompt": (
            "Prioritize the clips most likely to stop a scroll immediately: arguments, disrespect, "
            "accusations, jealousy, money talk, betrayal, reveals, funny reactions, sudden emotion shifts, "
            "catchphrases, and visible payoff moments. Avoid calm motivational or generic explanatory sections "
            "unless they contain an unusually strong emotional spike."
        ),
    },
    "balanced": {
        "label": "balanced",
        "prompt": (
            "Balance hook strength, clip clarity, and replay value. Pick clips that are broadly shareable and "
            "self-contained, even if they are less explosive."
        ),
    },
    "story": {
        "label": "story",
        "prompt": (
            "Allow slightly more setup if the payoff is strong. Favor coherent scenes and mini-story arcs that "
            "still open with a strong hook."
        ),
    },
}

PROJECT_CONTEXT_MD = """# Viral Hook Extractor Strategy

This project is for short-form hook extraction from Jamaican videos.

## Audience and content style
- Jamaican drama, lifestyle, funny tension, relationship conflict, street talk, expressive reactions.
- Preserve patois wording. Do not flatten everything into standard American English.
- A good result feels like the hottest, most replayable moment from the source.

## What counts as a strong hook
- A direct accusation, challenge, disrespect, threat, or reveal.
- A funny reaction or hard punchline.
- A sudden emotional shift.
- A strong first line that creates curiosity immediately.
- A clip where the payoff is visible or audible, not just implied.

## What to avoid by default
- Long calm setup before the interesting part.
- Generic preaching or motivational talk with no sharp turn.
- Clips that only make sense with too much missing context.

## Output rules
- The hook should land in the first 1 to 3 seconds of the clip.
- Choose the minimum setup needed before the hook.
- Prefer clips that still feel complete after the hook lands.
"""


def build_hook_prompt(
    focus_prompt: str = "",
    clip_count_hint: int = 8,
    hook_profile: str = "hot",
) -> str:
    """Build a compact one-line prompt that works reliably with Gemini CLI."""
    focus_prompt = (focus_prompt or "").strip()
    profile = HOOK_PROFILES.get(hook_profile, HOOK_PROFILES["hot"])
    prompt = (
        "Return ONLY a raw JSON array of {count} hook-based clip candidates for this video. "
        "Each item must include start, end, hook_time, type, hook_score, flow_score, value_score, "
        "trend_score, conflict_score, surprise_score, reaction_score, payoff_score, context_penalty, "
        "virality_score, reason, hook_line, and thumbnail_time. "
        "Rules: type must be funny, dramatic, or opening. "
        "hook_score, flow_score, value_score, trend_score, conflict_score, surprise_score, "
        "reaction_score, payoff_score, and context_penalty must be integers from 0 to 25. "
        "virality_score must be an integer from 0 to 100. "
        "The clip must start on the hook or very close to it, and the main hook must land within the first 1 to 3 seconds. "
        "Use the minimum setup required before the reveal, reaction, conflict, or punchline. "
        "This is Jamaican content, so keep patois wording instead of translating to standard English. "
        "{profile_prompt} "
        "conflict_score = how much tension, disrespect, confrontation, or stakes the clip has. "
        "surprise_score = how unexpected the reveal, line, or turn is. "
        "reaction_score = how strong the visible or audible reaction payoff is. "
        "payoff_score = how complete and satisfying the moment feels by the end. "
        "context_penalty = how much outside context is required to understand it; higher means worse. "
        "thumbnail_time should be the best visual frame for the clip. "
        "Do not include a full transcript in this candidate pass."
    ).format(
        count=max(3, min(clip_count_hint, 6)),
        profile_prompt=profile["prompt"],
    )
    if focus_prompt:
        prompt += f" Additional user instructions: {focus_prompt}."
    return prompt


def _find_gemini_cli() -> str:
    """Return the Gemini CLI executable path."""
    for candidate in ("gemini.cmd", "gemini"):
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError("Gemini CLI was not found on PATH. Install it and sign in with your Google account.")


def _parse_hooks_text(text: str) -> list[dict]:
    """Extract JSON array from Gemini's response text."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    hooks = json.loads(text)
    if not isinstance(hooks, list):
        raise ValueError("Expected a JSON array from Gemini CLI.")
    return hooks


def _normalize_type(value: str) -> str:
    if not value:
        return "opening"
    normalized = TYPE_MAP.get(str(value).strip().lower(), str(value).strip().lower())
    return normalized if normalized in {"funny", "dramatic", "opening"} else "opening"


def _to_int_score(value, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _transcript_to_pairs(transcript, start: float, end: float) -> list[list]:
    if isinstance(transcript, list):
        pairs = []
        for entry in transcript:
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue
            word, ts = entry[0], entry[1]
            try:
                pairs.append([str(word).strip(), round(float(ts), 2)])
            except (TypeError, ValueError):
                continue
        return [pair for pair in pairs if pair[0]]

    if not transcript:
        return []

    words = [word for word in re.split(r"\s+", str(transcript).strip()) if word]
    if not words:
        return []

    duration = max(1.0, float(end) - float(start))
    step = duration / max(len(words), 1)
    return [[word, round(float(start) + step * index, 2)] for index, word in enumerate(words)]


def _clamp_score(value: int) -> int:
    return max(0, min(25, value))


def _compute_selection_score(hook: dict, hook_profile: str) -> int:
    virality = float(hook.get("virality_score", 0))
    conflict = float(hook.get("conflict_score", 0))
    surprise = float(hook.get("surprise_score", 0))
    reaction = float(hook.get("reaction_score", 0))
    payoff = float(hook.get("payoff_score", 0))
    context_penalty = float(hook.get("context_penalty", 0))

    hotness = max(0.0, min(100.0, (conflict + surprise + reaction + payoff) - (context_penalty * 1.5)))
    storyness = max(0.0, min(100.0, (payoff * 2.6) + (hook.get("flow_score", 0) * 1.4) - (context_penalty * 1.1)))

    if hook_profile == "balanced":
        score = virality
    elif hook_profile == "story":
        score = (virality * 0.70) + (storyness * 0.30)
    else:
        score = (virality * 0.55) + (hotness * 0.45)

    if hook.get("type") == "dramatic":
        score += 2.0
    if hook.get("type") == "funny":
        score += 1.5

    return int(round(max(0.0, min(100.0, score))))


def _normalize_hook(hook: dict, hook_profile: str) -> dict:
    start = float(hook.get("start", 0.0))
    end = float(hook.get("end", max(start + 15.0, 15.0)))
    hook_time = hook.get("hook_time", start)
    try:
        hook_time = float(hook_time)
    except (TypeError, ValueError):
        hook_time = start

    normalized = {
        "start": round(start, 2),
        "end": round(end, 2),
        "hook_time": round(hook_time, 2),
        "type": _normalize_type(hook.get("type")),
        "hook_score": _clamp_score(_to_int_score(hook.get("hook_score"), 0)),
        "flow_score": _clamp_score(_to_int_score(hook.get("flow_score"), 0)),
        "value_score": _clamp_score(_to_int_score(hook.get("value_score"), 0)),
        "trend_score": _clamp_score(_to_int_score(hook.get("trend_score"), 0)),
        "conflict_score": _clamp_score(_to_int_score(hook.get("conflict_score"), 0)),
        "surprise_score": _clamp_score(_to_int_score(hook.get("surprise_score"), 0)),
        "reaction_score": _clamp_score(_to_int_score(hook.get("reaction_score"), 0)),
        "payoff_score": _clamp_score(_to_int_score(hook.get("payoff_score"), 0)),
        "context_penalty": _clamp_score(_to_int_score(hook.get("context_penalty"), 0)),
        "virality_score": max(
            0,
            min(
                100,
                _to_int_score(
                    hook.get("virality_score"),
                    _to_int_score(hook.get("hook_score"), 0)
                    + _to_int_score(hook.get("flow_score"), 0)
                    + _to_int_score(hook.get("value_score"), 0)
                    + _to_int_score(hook.get("trend_score"), 0),
                ),
            ),
        ),
        "reason": str(hook.get("reason", "")).strip(),
        "hook_line": str(hook.get("hook_line", "")).strip(),
        "transcript": _transcript_to_pairs(hook.get("transcript"), start, end),
        "thumbnail_time": round(float(hook.get("thumbnail_time", hook_time)), 2),
    }
    normalized["selection_score"] = _compute_selection_score(normalized, hook_profile)
    return normalized


def _stage_chunk_for_cli(chunk_path: str) -> tuple[str, str]:
    """Create a clean Gemini CLI workdir with a local context file."""
    chunk_path = os.path.abspath(chunk_path)
    work_dir = tempfile.mkdtemp(prefix="gemini_cli_")
    staged_path = os.path.join(work_dir, os.path.basename(chunk_path))
    try:
        os.link(chunk_path, staged_path)
    except OSError:
        shutil.copy2(chunk_path, staged_path)

    with open(os.path.join(work_dir, "GEMINI.md"), "w", encoding="utf-8") as handle:
        handle.write(PROJECT_CONTEXT_MD)

    return work_dir, staged_path


def _run_cli_for_chunk(
    chunk_path: str,
    focus_prompt: str,
    clip_count_hint: int,
    hook_profile: str,
) -> list[dict]:
    cli_path = _find_gemini_cli()
    work_dir, staged_path = _stage_chunk_for_cli(chunk_path)
    base_prompt = f"@{Path(staged_path).name} " + build_hook_prompt(
        focus_prompt=focus_prompt,
        clip_count_hint=clip_count_hint,
        hook_profile=hook_profile,
    )

    last_error = ""
    try:
        for attempt in range(1, 4):
            prompt = base_prompt
            if attempt > 1:
                prompt += " Previous response was invalid. Return ONLY the raw JSON array."

            result = subprocess.run(
                [cli_path, "-p", prompt, "--output-format", "json"],
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=300,
            )

            if result.returncode != 0:
                stderr = result.stderr.strip() or result.stdout.strip()
                raise RuntimeError(f"Gemini CLI failed: {stderr}")

            stdout = result.stdout.strip()
            try:
                payload = json.loads(stdout)
                response_text = payload["response"] if isinstance(payload, dict) and "response" in payload else stdout
                hooks = _parse_hooks_text(response_text)
                return [_normalize_hook(hook, hook_profile) for hook in hooks]
            except Exception as exc:
                last_error = str(exc)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    raise RuntimeError(f"Gemini CLI returned invalid hook JSON. {last_error}")


def transcribe_clip(clip_path: str) -> list[list]:
    """Transcribe one selected clip with word timings using Gemini CLI."""
    cli_path = _find_gemini_cli()
    work_dir, staged_path = _stage_chunk_for_cli(clip_path)
    prompt = (
        f"@{Path(staged_path).name} "
        "Return ONLY a raw JSON object with keys transcript_words and cleaned_transcript. "
        "transcript_words must be an array of [word, second] pairs using seconds from the start of this clip. "
        "Keep Jamaican patois wording instead of translating to standard English. "
        "Make the timestamps as accurate as possible for burned-in subtitles."
    )
    try:
        result = subprocess.run(
            [cli_path, "-p", prompt, "--output-format", "json"],
            capture_output=True,
            text=True,
            cwd=work_dir,
            timeout=300,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"Gemini CLI failed during transcription: {stderr}")

        payload = json.loads(result.stdout.strip())
        response_text = payload["response"] if isinstance(payload, dict) and "response" in payload else result.stdout.strip()
        response_text = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
        response_text = re.sub(r"\s*```$", "", response_text)
        transcript_payload = json.loads(response_text)
        return _transcript_to_pairs(transcript_payload.get("transcript_words"), 0.0, 30.0)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _adjust_timestamps(hooks: list[dict], offset: float) -> list[dict]:
    adjusted = []
    for hook in hooks:
        item = dict(hook)
        item["start"] = round(item.get("start", 0.0) + offset, 2)
        item["end"] = round(item.get("end", 0.0) + offset, 2)
        item["hook_time"] = round(item.get("hook_time", item["start"]) + offset, 2)
        item["thumbnail_time"] = round(item.get("thumbnail_time", item["hook_time"]) + offset, 2)
        item["transcript"] = [
            [word, round(float(ts) + offset, 2)]
            for word, ts in item.get("transcript", [])
            if isinstance(ts, (int, float))
        ]
        adjusted.append(item)
    return adjusted


def _selection_score(hook: dict) -> float:
    return float(hook.get("selection_score", hook.get("virality_score", 0)))


def _is_duplicate_hook(left: dict, right: dict, overlap_ratio: float = 0.6) -> bool:
    """Treat hooks as duplicates when they mostly describe the same time window."""
    left_start = float(left.get("start", 0.0))
    left_end = float(left.get("end", left_start))
    right_start = float(right.get("start", 0.0))
    right_end = float(right.get("end", right_start))

    intersection = min(left_end, right_end) - max(left_start, right_start)
    if intersection <= 0:
        return False

    left_duration = max(1.0, left_end - left_start)
    right_duration = max(1.0, right_end - right_start)
    return (intersection / min(left_duration, right_duration)) >= overlap_ratio


def _deduplicate_hooks(all_hooks: list[dict]) -> list[dict]:
    if not all_hooks:
        return []

    sorted_hooks = sorted(all_hooks, key=lambda item: item.get("start", 0))
    result = []
    for hook in sorted_hooks:
        duplicate = False
        for existing in result:
            if _is_duplicate_hook(hook, existing):
                if _selection_score(hook) > _selection_score(existing):
                    result.remove(existing)
                    result.append(hook)
                duplicate = True
                break
        if not duplicate:
            result.append(hook)
    return sorted(result, key=_selection_score, reverse=True)


def analyze_video(
    video_path: str,
    api_key: str,
    chunks: list[tuple[float, str]],
    n_clips: int = 5,
    focus_prompt: str = "",
    hook_profile: str = "hot",
) -> list[dict]:
    """Analyze all chunks with Gemini CLI and return the top hooks."""
    all_hooks = []
    errors = []

    for index, (offset, chunk_path) in enumerate(chunks, start=1):
        label = f"chunk {index}/{len(chunks)}"
        try:
            print(f"    Analyzing {label} with Gemini CLI ({hook_profile})...")
            hooks = _run_cli_for_chunk(
                chunk_path,
                focus_prompt,
                max(n_clips + 2, 3),
                hook_profile,
            )
            hooks = _adjust_timestamps(hooks, offset)
            all_hooks.extend(hooks)
            print(f"    Found {len(hooks)} hooks in {label}.")
        except Exception as exc:
            errors.append((label, str(exc)))
            print(f"  WARNING: Failed to analyze {label}: {exc}")

    if not all_hooks:
        if errors:
            joined = " | ".join(f"{label}: {message}" for label, message in errors)
            raise RuntimeError(f"Gemini CLI analysis failed. {joined}")
        raise RuntimeError("Gemini CLI found no hooks in the video.")

    merged = _deduplicate_hooks(all_hooks)
    top = merged[:n_clips]
    print(f"  Selected top {len(top)} hooks from {len(merged)} total candidates.")
    return top
