# Viral Hook Extractor

Open source AI video clipper for finding high-retention hooks in long videos. Built for Jamaican drama and lifestyle content, but useful for any talking-head or narrative video where generic transcription-first tools miss the real moment. Instead of transcribing first, it sends the video directly to Gemini AI, then cuts the best hooks as vertical 9:16 clips with burned-in captions.

## What it does

1. Sends your video to Gemini 2.0 Flash (understands Jamaican patois natively)
2. Finds your best hooks: funny moments, dramatic peaks, strong opening lines
3. Cuts each hook as a clip
4. Reframes to vertical 9:16 (for Reels / TikTok / YouTube Shorts)
5. Burns in captions
6. Ranks clips by score and saves them to `output/`

## Prerequisites

### 1. Python 3.10+
Download from [python.org](https://www.python.org/downloads/)

### 2. FFmpeg
Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to your PATH.

Test it works:
```
ffmpeg -version
```

### 3. Free Gemini API Key
1. Go to [https://ai.google.dev](https://ai.google.dev)
2. Click **Get API key** → **Create API key**
3. Copy the key

## Installation

```bash
cd C:\Users\User\clipper

# Install Python dependencies
pip install -r requirements.txt

# Set up your API key
copy .env.example .env
# Open .env and replace "your_api_key_here" with your actual key
```

Your `.env` file should look like:
```
GEMINI_API_KEY=AIzaSy...your_key_here
```

## Usage

```bash
# Basic — extract top 5 hooks
python clipper.py my_video.mp4

# Extract 8 clips, between 15-45 seconds each
python clipper.py my_video.mp4 --clips 8 --min 15 --max 45

# Enable face-tracking for smarter vertical crop (slower)
python clipper.py my_video.mp4 --face-track

# Save clips to a custom folder
python clipper.py my_video.mp4 --output my_clips
```

### All options

| Flag | Default | Description |
|---|---|---|
| `--clips N` | 5 | Number of clips to extract |
| `--min SECS` | 20 | Minimum clip duration in seconds |
| `--max SECS` | 60 | Maximum clip duration in seconds |
| `--face-track` | off | Center crop on face instead of center of frame |
| `--output DIR` | `./output` | Where to save output clips |

## Output

```
output/
  clip_01_score9.2_dramatic.mp4   ← best clip
  clip_02_score8.5_funny.mp4
  clip_03_score7.8_opening.mp4
  ...
  hooks.json                      ← all detected hooks with timestamps + reasoning
```

`hooks.json` contains the full data for each hook:
```json
[
  {
    "start": 142.3,
    "end": 178.1,
    "type": "dramatic",
    "score": 9.2,
    "reason": "Heated confrontation that escalates quickly — strong tension hook",
    "thumbnail_time": 155.4,
    "transcript": [["wah", 142.3], ["yuh", 142.6], ...]
  }
]
```

## Long videos

Videos longer than 45 minutes are automatically split into chunks and processed in segments. No extra setup needed — it handles this transparently.

## Troubleshooting

**`GEMINI_API_KEY not found`**
Make sure you created a `.env` file (not just `.env.example`) with your key.

**`ffmpeg: command not found`**
FFmpeg is not on your PATH. Re-install it and make sure to check "Add to PATH" during setup, or add it manually.

**Gemini returns empty / malformed JSON**
The tool retries up to 3 times automatically. If it keeps failing, the video may be too short or have very little speech.

**Captions not syncing well**
Gemini gives approximate word timestamps. For tighter sync, try shorter clips with `--max 30`.

## How it compares to Opus Clip

| | Opus Clip | This tool |
|---|---|---|
| Jamaican patois | Transcribes poorly | Gemini understands it in context |
| Hook detection | Generic English model | Prompt tuned for drama/lifestyle |
| Transparency | Black box | `hooks.json` shows score + reason |
| Vertical crop | Auto | Center or face-tracked |
| Cost | $20+/mo subscription | Free Gemini API tier |
