"""Upload video chunks to Gemini and extract hooks with timestamps."""
import json
import time
import re
from google import genai
from google.genai import types

HOOK_PROMPT = """You are an expert short-form video editor analyzing a Jamaican drama or lifestyle video.

Your job: find the moments that would make someone STOP scrolling and watch the full clip.

IMPORTANT: This is Jamaican content. Speakers use Jamaican patois, creole, or mixed English/patois. Transcribe exactly what is said including patois words and phrases — do not translate or substitute standard English.

For each hook candidate, score it on FOUR dimensions (each 0-25 points):

1. HOOK (0-25): How strong is the opening moment? Does the first 2-3 seconds immediately grab attention?
   - 20-25: Pattern interrupt, shocking statement, direct question, unexpected action
   - 10-19: Interesting but takes a moment to pull you in
   - 0-9: Slow start, needs context to understand

2. FLOW (0-25): Is this a complete, self-contained moment? Can someone understand it without seeing the rest of the video?
   - 20-25: Complete setup + payoff, clear beginning and end, no missing context
   - 10-19: Mostly self-contained, minor context needed
   - 0-9: Cut mid-thought, confusing without surrounding context

3. VALUE (0-25): Does this deliver emotional impact — laughter, shock, drama, relatable feeling?
   - 20-25: Strong emotional hit (real laughter, genuine shock, high drama, deep relatability)
   - 10-19: Moderate emotional response
   - 0-9: Low emotional impact

4. TREND (0-25): Does this fit short-form viral content patterns?
   - 20-25: Conflict/drama, unexpected twist, funny reaction, big reveal, emotional moment
   - 10-19: Engaging but niche
   - 0-9: Unlikely to perform well out of context

virality_score = hook + flow + value + trend (total 0-99)

Return ONLY a raw JSON array — no markdown, no explanation.

[
  {
    "start": 12.4,
    "end": 38.1,
    "type": "funny",
    "hook_score": 22,
    "flow_score": 20,
    "value_score": 18,
    "trend_score": 17,
    "virality_score": 77,
    "reason": "One sentence: why this specific moment hooks a viewer",
    "hook_line": "One punchy text overlay for the start of the clip (max 8 words)",
    "transcript": [["word1", 12.4], ["word2", 12.9], ["word3", 13.4]],
    "thumbnail_time": 15.2
  }
]

Rules:
- Return 3 to 8 hooks sorted by virality_score descending
- Timestamps are seconds from the START of this video segment
- type must be one of: "funny", "dramatic", "opening"
- Each clip should be 15-60 seconds long
- transcript is an array of [word, timestamp_seconds] pairs — include every word spoken in the clip
- thumbnail_time is the single best frame for a thumbnail (peak expression, peak action)
- hook_line is a short punchy text shown as overlay at the very start of the clip
"""


def build_hook_prompt(focus_prompt: str = "") -> str:
    """Build the final Gemini prompt with optional user focus guidance."""
    focus_prompt = (focus_prompt or "").strip()
    if not focus_prompt:
        return HOOK_PROMPT
    return (
        HOOK_PROMPT
        + "\n\nAdditional user instructions for this run:\n"
        + focus_prompt
        + "\nPrioritize clips that satisfy these extra instructions if they are present in the video."
    )


def _wait_for_file(client: genai.Client, file_name: str, timeout: int = 180) -> object:
    """Poll until file state is ACTIVE or raise on timeout/failure."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        f = client.files.get(name=file_name)
        state = f.state.name if hasattr(f.state, "name") else str(f.state)
        if state == "ACTIVE":
            return f
        if state == "FAILED":
            raise RuntimeError(f"Gemini file processing failed for {file_name}")
        time.sleep(5)
    raise TimeoutError(f"Timed out waiting for Gemini to process file {file_name}")


def _parse_hooks(text: str) -> list[dict]:
    """Extract JSON array from Gemini's response text."""
    # Strip markdown code fences if present
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        hooks = json.loads(text)
        if not isinstance(hooks, list):
            raise ValueError("Expected a JSON array")
        return hooks
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Could not parse Gemini response as JSON: {e}\nResponse was:\n{text[:500]}")


def _analyze_chunk(
    client: genai.Client,
    chunk_path: str,
    chunk_label: str,
    prompt: str,
) -> list[dict]:
    """Upload one video chunk and ask Gemini to find hooks. Returns raw hook list."""
    print(f"    Uploading {chunk_label}...")
    uploaded = client.files.upload(
        file=chunk_path,
        config=types.UploadFileConfig(mime_type="video/mp4")
    )

    print(f"    Waiting for Gemini to process {chunk_label}...")
    uploaded = _wait_for_file(client, uploaded.name)

    print(f"    Analyzing {chunk_label}...")

    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[uploaded, prompt]
            )
            hooks = _parse_hooks(response.text)
            print(f"    Found {len(hooks)} hooks in {chunk_label}.")
            return hooks
        except ValueError as e:
            if attempt == 3:
                raise
            print(f"    Parse error (attempt {attempt}/3), retrying... {e}")
            time.sleep(2)

    return []


def _adjust_timestamps(hooks: list[dict], offset: float) -> list[dict]:
    """Convert chunk-relative timestamps to absolute video timestamps."""
    adjusted = []
    for h in hooks:
        h = dict(h)
        h["start"] = round(h.get("start", 0) + offset, 2)
        h["end"] = round(h.get("end", 0) + offset, 2)
        h["thumbnail_time"] = round(h.get("thumbnail_time", h["start"]) + offset, 2)
        # Adjust transcript timestamps
        transcript = h.get("transcript", [])
        if isinstance(transcript, list):
            h["transcript"] = [[w, round(t + offset, 2)] for w, t in transcript if isinstance(t, (int, float))]
        adjusted.append(h)
    return adjusted


def _virality(hook: dict) -> float:
    """Return the virality score, falling back to legacy 'score' field * 10 for old responses."""
    return hook.get("virality_score") or hook.get("score", 0) * 10


def _deduplicate_hooks(all_hooks: list[dict], overlap: float = 90.0) -> list[dict]:
    """
    Remove duplicate hooks from overlapping chunk regions.
    Two hooks are duplicates if they start within `overlap` seconds of each other.
    Keep the one with the higher score.
    """
    if not all_hooks:
        return []

    sorted_hooks = sorted(all_hooks, key=lambda h: h.get("start", 0))
    result = []

    for hook in sorted_hooks:
        duplicate = False
        for existing in result:
            if abs(hook.get("start", 0) - existing.get("start", 0)) < overlap:
                if _virality(hook) > _virality(existing):
                    result.remove(existing)
                    result.append(hook)
                duplicate = True
                break
        if not duplicate:
            result.append(hook)

    return sorted(result, key=_virality, reverse=True)


def analyze_video(
    video_path: str,
    api_key: str,
    chunks: list[tuple[float, str]],
    n_clips: int = 5,
    focus_prompt: str = "",
) -> list[dict]:
    """
    Analyze all video chunks with Gemini and return the top N hooks.

    chunks: list of (start_offset_seconds, chunk_path) from chunker.py
    Returns hooks sorted by score descending.
    """
    client = genai.Client(api_key=api_key)
    all_hooks = []
    prompt = build_hook_prompt(focus_prompt)
    errors = []

    for i, (offset, chunk_path) in enumerate(chunks):
        label = f"chunk {i+1}/{len(chunks)}"
        try:
            hooks = _analyze_chunk(client, chunk_path, label, prompt)
            hooks = _adjust_timestamps(hooks, offset)
            all_hooks.extend(hooks)
        except Exception as e:
            errors.append((label, str(e)))
            print(f"  WARNING: Failed to analyze {label}: {e}")

    if not all_hooks:
        if errors:
            joined = " | ".join(f"{label}: {message}" for label, message in errors)
            raise RuntimeError(f"Gemini analysis failed. {joined}")
        raise RuntimeError("Gemini found no hooks in the video. Try a different video or check your API key.")

    merged = _deduplicate_hooks(all_hooks)
    top = merged[:n_clips]
    print(f"  Selected top {len(top)} hooks from {len(merged)} total candidates.")
    return top
