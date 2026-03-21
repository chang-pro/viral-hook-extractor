# Viral Hook Extractor

Open source AI video clipper for finding high-retention hooks in long videos.

This project is aimed at Jamaican drama, lifestyle, and patois-heavy content where transcription-first clipping tools often miss the real moment. It uses Gemini CLI with your signed-in Google account to rank hooks, then cuts, reframes, captions, and optionally exports thumbnails.

## Current features

1. Analyze local MP4 files with Gemini CLI.
2. Score hooks across `hook`, `flow`, `value`, `trend`, plus hot-hook metrics like `conflict`, `surprise`, `reaction`, and `payoff`.
3. Cut top clips with FFmpeg.
4. Reframe to vertical 9:16.
5. Burn in ASS captions.
6. Use a two-pass flow: pick candidates first, then transcribe only the winning clip(s) for subtitles.
7. Use Gemini word timings or an external source-video SRT.
8. Export JPG thumbnails from the best frame per hook.
9. Save full metadata to `hooks.json`.

## Why this exists

Opus Clip is strong on automated clipping, but the weak point for this use case is transcription quality on Jamaican speech. If the transcript is wrong, the hook ranking and captions drift. This repo keeps the ranking stage video-first and adds an external-SRT path so captions can come from a better transcript when needed.

## Installation

### Requirements

1. Python 3.10+
2. FFmpeg on PATH
3. Gemini CLI installed and signed in with Google

### Install

```powershell
cd C:\Users\User\code\viral-hook-extractor
pip install -r requirements.txt
gemini
```
When Gemini CLI opens, choose **Sign in with Google**. If you have Google AI Pro or Google AI Ultra, sign in with that same Google account.

## Usage

```powershell
python clipper.py my_video.mp4
python clipper.py my_video.mp4 --clips 8 --length-preset medium --face-track
python clipper.py my_video.mp4 --captions-srt full_video.srt --save-thumbnails
python clipper.py my_video.mp4 --focus-prompt "prioritize arguments, reveals, and funny reactions"
python clipper.py my_video.mp4 --hook-profile hot
```

## Web UI

```powershell
pip install -r requirements.txt
python webapp.py
```

Then open `http://127.0.0.1:5000` in your browser.

The web UI lets you:

1. Upload a video.
2. Upload an optional full-video SRT.
3. Pick clip count and duration range.
4. Add a focus prompt like Opus ClipAnything.
5. Turn face tracking and thumbnail export on or off.
6. Download clips, thumbnails, and `hooks.json` after the run finishes.

## CLI options

| Flag | Default | Description |
|---|---|---|
| `--clips N` | `5` | Number of clips to export |
| `--length-preset` | `short` | `short=30-60s`, `medium=1-3m`, `long=3-5m`, `custom=use min/max` |
| `--min SECS` | `20` | Minimum clip length |
| `--max SECS` | `60` | Maximum clip length |
| `--face-track` | off | Use face detection for crop positioning |
| `--output DIR` | `output` | Output folder |
| `--captions-srt PATH` | none | Use a source-video SRT for captions |
| `--focus-prompt TEXT` | none | Extra instructions for hook selection |
| `--hook-profile` | `hot` | `hot=maximum drama/reaction`, `balanced=general viral`, `story=cleaner arc` |
| `--save-thumbnails` | off | Export a JPG thumbnail per selected clip |

## Output

```text
output/
  clip_01_virality84_dramatic.mp4
  clip_02_virality78_funny.mp4
  hooks.json
  thumbnails/
    clip_01_thumb.jpg
    clip_02_thumb.jpg
```

Each hook in `hooks.json` includes:

```json
{
  "start": 142.3,
  "end": 178.1,
  "type": "dramatic",
  "hook_score": 22,
  "flow_score": 21,
  "value_score": 20,
  "trend_score": 19,
  "conflict_score": 24,
  "surprise_score": 22,
  "reaction_score": 23,
  "payoff_score": 21,
  "context_penalty": 4,
  "virality_score": 82,
  "selection_score": 88,
  "reason": "The confrontation escalates immediately and resolves cleanly.",
  "hook_line": "HIM NEVER EXPECT THIS",
  "thumbnail_time": 155.4,
  "transcript": [["wah", 142.3], ["yuh", 142.6]]
}
```

## How captions work

Default mode uses Gemini CLI in a second pass on the selected clip to build ASS karaoke captions.

If you already have a better transcript, pass `--captions-srt full_video.srt`. The tool will slice that full-video subtitle file to match each exported clip, which is the better path when Jamaican speech recognition quality matters more than convenience.

## Limits

1. Hook scoring is prompt-based, not learned from your own performance history.
2. Thumbnail selection is a still-frame export, not full thumbnail design.
3. Face tracking is simple clip-level positioning, not continuous smart reframing.
4. Gemini word timings are approximate, so external SRT is still the safest caption path.

## Recommended next upgrades

1. Add local ASR fallback with `faster-whisper` or `WhisperX`.
2. Add thumbnail ranking that checks faces, motion, and sharpness.
3. Add optional transcript correction dictionary for recurring patois names and slang.
4. Add a scoring feedback loop from your actual post performance.
