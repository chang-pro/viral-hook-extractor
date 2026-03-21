"""
Jamaican Video Clip Extractor
Replaces Opus Clip with Gemini-powered hook detection that understands Jamaican content.

Usage:
    python clipper.py video.mp4
    python clipper.py video.mp4 --clips 8 --min 15 --max 45 --face-track
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from chunker import chunk_video, get_duration
from analyzer import analyze_video, transcribe_clip
from cutter import cut_clip
from reframer import reframe_clip
from captioner import generate_ass, generate_ass_from_srt, burn_captions
from thumbnailer import extract_thumbnail
from utils import ensure_dir, cleanup_files


BASE_DIR = Path(__file__).resolve().parent
DURATION_PRESETS = {
    "short": (30.0, 60.0),
    "medium": (60.0, 180.0),
    "long": (180.0, 300.0),
    "custom": None,
}
HOOK_PROFILE_CHOICES = ("hot", "balanced", "story")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract viral hooks from Jamaican video content using Gemini AI."
    )
    parser.add_argument("video", help="Path to input video file (MP4)")
    parser.add_argument("--clips", type=int, default=5,
                        help="Number of clips to extract (default: 5)")
    parser.add_argument("--length-preset", default="short", choices=sorted(DURATION_PRESETS.keys()),
                        help="Clip length preset: short=30-60s, medium=1-3m, long=3-5m, custom=use --min/--max")
    parser.add_argument("--min", type=float, default=20, dest="min_duration",
                        help="Minimum clip duration in seconds (default: 20)")
    parser.add_argument("--max", type=float, default=60, dest="max_duration",
                        help="Maximum clip duration in seconds (default: 60)")
    parser.add_argument("--face-track", action="store_true",
                        help="Use face detection for smarter 9:16 reframing (slower)")
    parser.add_argument("--output", default="output",
                        help="Output directory (default: ./output)")
    parser.add_argument("--captions-srt", default="",
                        help="Optional source-video SRT file to use for captions instead of Gemini transcript")
    parser.add_argument("--focus-prompt", default="",
                        help="Extra instructions for hook selection, similar to Opus ClipAnything")
    parser.add_argument("--hook-profile", default="hot", choices=HOOK_PROFILE_CHOICES,
                        help="Hook ranking profile: hot=maximum drama/reaction, balanced=general viral, story=cleaner arcs")
    parser.add_argument("--analyze-only", action="store_true",
                        help="Only score and rank hook candidates without exporting clips")
    parser.add_argument("--save-thumbnails", action="store_true",
                        help="Export thumbnail JPGs at Gemini's suggested timestamps")
    return parser.parse_args()


def validate_hook_duration(hook: dict, min_dur: float, max_dur: float) -> dict:
    """Clamp hook duration to min/max range."""
    start = hook.get("start", 0)
    end = hook.get("end", start + 30)
    duration = end - start

    if duration < min_dur:
        # Extend end to meet minimum
        end = start + min_dur
    elif duration > max_dur:
        # Trim end to meet maximum
        end = start + max_dur

    return {**hook, "end": round(end, 2)}


def anchor_hook_to_opening(
    hook: dict,
    target_hook_delay: float = 1.5,
    max_hook_delay: float = 3.0,
) -> dict:
    """Shift clip start closer to the hook so the opening lands faster."""
    hook_time = hook.get("hook_time")
    start = hook.get("start", 0.0)
    end = hook.get("end", start + 30.0)

    if not isinstance(hook_time, (int, float)):
        return hook

    duration = max(1.0, end - start)
    latest_start = max(0.0, float(hook_time) - max_hook_delay)
    ideal_start = max(0.0, float(hook_time) - target_hook_delay)

    if start < latest_start or start > hook_time:
        start = ideal_start
        end = start + duration

    return {**hook, "start": round(start, 2), "end": round(end, 2)}


def resolve_duration_settings(length_preset: str, min_duration: float, max_duration: float) -> tuple[str, float, float]:
    """Resolve UI/CLI duration preset into concrete min/max values."""
    preset = (length_preset or "short").strip().lower()
    if preset not in DURATION_PRESETS:
        raise ValueError(f"Unknown length preset: {preset}")
    preset_range = DURATION_PRESETS[preset]
    if preset_range is None:
        return preset, min_duration, max_duration
    return preset, preset_range[0], preset_range[1]


def run_pipeline(
    video_path: str,
    clips: int = 5,
    length_preset: str = "short",
    min_duration: float = 20.0,
    max_duration: float = 60.0,
    face_track: bool = False,
    output_dir: str = "output",
    captions_srt_path: str = "",
    focus_prompt: str = "",
    hook_profile: str = "hot",
    analyze_only: bool = False,
    save_thumbnails: bool = False,
) -> dict:
    """Run the full clipping pipeline and return output metadata."""
    if clips < 1:
        raise ValueError("clips must be at least 1")
    length_preset, min_duration, max_duration = resolve_duration_settings(
        length_preset,
        min_duration,
        max_duration,
    )
    if min_duration <= 0 or max_duration <= 0:
        raise ValueError("Clip durations must be positive.")
    if min_duration > max_duration:
        raise ValueError("min_duration cannot be greater than max_duration.")

    video_path = os.path.abspath(video_path)
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    output_dir = ensure_dir(output_dir)
    thumbnails_dir = ensure_dir(os.path.join(output_dir, "thumbnails")) if save_thumbnails else ""
    temp_dir = tempfile.mkdtemp(prefix="clipper_")
    temp_files_to_clean = [temp_dir]
    captions_srt_content = ""

    if captions_srt_path:
        srt_path = os.path.abspath(captions_srt_path)
        if not os.path.isfile(srt_path):
            raise FileNotFoundError(f"SRT file not found: {srt_path}")
        with open(srt_path, "r", encoding="utf-8-sig") as handle:
            captions_srt_content = handle.read()

    print(f"\nJamaican Video Clip Extractor")
    print(f"{'='*40}")
    print(f"Input:   {os.path.basename(video_path)}")
    print(f"Clips:   {clips}")
    print(f"Preset:  {length_preset} ({int(min_duration)}s to {int(max_duration)}s)")
    print(f"Output:  {output_dir}/")
    if captions_srt_content:
        print(f"Captions: external SRT ({os.path.basename(captions_srt_path)})")
    print(f"Profile: {hook_profile}")
    if focus_prompt.strip():
        print(f"Focus:   {focus_prompt.strip()}")
    print()

    try:
        # Step 1: Get video duration
        print("Step 1/5: Reading video...")
        video_duration = get_duration(video_path)
        print(f"  Duration: {video_duration/60:.1f} minutes")

        # Step 2: Chunk if needed
        print("\nStep 2/5: Preparing video chunks...")
        chunks = chunk_video(video_path, os.path.join(temp_dir, "chunks"))
        print(f"  {len(chunks)} segment(s) ready for analysis.")

        # Step 3: Analyze with Gemini
        print(f"\nStep 3/5: Analyzing with Gemini AI (this may take a few minutes)...")
        hooks = analyze_video(
            video_path,
            "",
            chunks,
            n_clips=clips,
            focus_prompt=focus_prompt,
            hook_profile=hook_profile,
        )

        # Validate and clamp durations
        hooks = [
            validate_hook_duration(
                anchor_hook_to_opening(h),
                min_duration,
                max_duration,
            )
            for h in hooks
        ]

        # Save hooks.json
        hooks_path = os.path.join(output_dir, "hooks.json")
        with open(hooks_path, "w", encoding="utf-8") as f:
            json.dump(hooks, f, indent=2, ensure_ascii=False)
        print(f"  Saved hook data -> {hooks_path}")

        if analyze_only:
            print("\nAnalysis only mode: skipping clip cutting and export.")
            return {
                "output_dir": os.path.abspath(output_dir),
                "hooks_path": os.path.abspath(hooks_path),
                "clips": [],
                "hooks": hooks,
                "thumbnails_dir": "",
                "analyze_only": True,
            }

        # Steps 4 & 5: Cut, reframe, caption
        print(f"\nStep 4/5: Cutting clips...")
        raw_clips = []
        for i, hook in enumerate(hooks):
            raw_path = os.path.join(temp_dir, f"raw_{i:02d}.mp4")
            cut_clip(
                source_path=video_path,
                start=hook["start"],
                end=hook["end"],
                output_path=raw_path,
                video_duration=video_duration
            )
            raw_clips.append((i, hook, raw_path))
            vscore = hook.get("virality_score") or hook.get("score", "?")
            selection = hook.get("selection_score", vscore)
            htype = hook.get("type", "unknown")
            print(f"  Clip {i+1}: pick={selection} virality={vscore} type={htype} "
                  f"({hook['start']:.1f}s - {hook['end']:.1f}s)")

        print(f"\nStep 5/5: Reframing to 9:16 and burning captions...")
        final_clips = []
        for i, hook, raw_path in raw_clips:
            vscore = hook.get("virality_score") or round((hook.get("score", 0)) * 10)
            htype = hook.get("type", "unknown")
            hook_line = hook.get("hook_line", "")

            # Reframe to 9:16
            reframed_path = os.path.join(temp_dir, f"reframed_{i:02d}.mp4")
            reframe_clip(raw_path, reframed_path, face_track=face_track)

            # Generate karaoke captions (.ass format)
            clip_start_abs = max(0.0, hook["start"] - 1.5)  # account for pad_start
            clip_end_abs = min(video_duration, hook["end"] + 1.0)
            if captions_srt_content:
                ass = generate_ass_from_srt(
                    captions_srt_content,
                    clip_start=clip_start_abs,
                    clip_end=clip_end_abs,
                    hook_line=hook_line,
                )
            else:
                transcript = hook.get("transcript", [])
                if not transcript:
                    print(f"    Transcribing selected clip {i+1} for subtitles...")
                    transcript = transcribe_clip(raw_path)
                    hook["transcript"] = transcript
                ass = generate_ass(
                    transcript,
                    clip_start=clip_start_abs,
                    hook_line=hook_line,
                )

            # Burn captions
            final_name = f"clip_{i+1:02d}_virality{vscore}_{htype}.mp4"
            final_path = os.path.join(output_dir, final_name)
            burn_captions(reframed_path, ass, final_path)
            if save_thumbnails:
                thumb_name = f"clip_{i+1:02d}_thumb.jpg"
                thumb_path = os.path.join(thumbnails_dir, thumb_name)
                extract_thumbnail(
                    video_path,
                    hook.get("thumbnail_time", hook["start"]),
                    thumb_path,
                )

            final_clips.append(final_path)
            print(f"  -> {final_name}")

        # Print summary
        print(f"\n{'='*40}")
        print(f"Done! {len(final_clips)} clips saved to: {output_dir}/")
        print()
        for i, (_, hook, _) in enumerate(raw_clips):
            vscore = hook.get("virality_score") or round((hook.get("score", 0)) * 10)
            selection = hook.get("selection_score", vscore)
            htype = hook.get("type", "?")
            reason = hook.get("reason", "")
            hook_line = hook.get("hook_line", "")
            h = hook.get("hook_score", "-")
            f_ = hook.get("flow_score", "-")
            v = hook.get("value_score", "-")
            t = hook.get("trend_score", "-")
            c = hook.get("conflict_score", "-")
            s = hook.get("surprise_score", "-")
            r = hook.get("reaction_score", "-")
            p = hook.get("payoff_score", "-")
            cp = hook.get("context_penalty", "-")
            print(f"  #{i+1} pick={selection} virality={vscore} [{htype}] H:{h} F:{f_} V:{v} T:{t}")
            print(f"      hot metrics: conflict={c} surprise={s} reaction={r} payoff={p} context_penalty={cp}")
            if hook_line:
                print(f"      hook line: \"{hook_line}\"")
            if reason:
                print(f"      reason:    {reason}")
        print()
        return {
            "output_dir": os.path.abspath(output_dir),
            "hooks_path": os.path.abspath(hooks_path),
            "clips": final_clips,
            "hooks": hooks,
            "thumbnails_dir": os.path.abspath(thumbnails_dir) if save_thumbnails else "",
            "analyze_only": False,
        }

    except KeyboardInterrupt:
        print("\nCancelled by user.")
        raise RuntimeError("Cancelled by user.")
    finally:
        print("Cleaning up temp files...")
        cleanup_files(temp_files_to_clean)


def main():
    args = parse_args()
    try:
        run_pipeline(
            video_path=args.video,
            clips=args.clips,
            length_preset=args.length_preset,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            face_track=args.face_track,
            output_dir=args.output,
            captions_srt_path=args.captions_srt,
            focus_prompt=args.focus_prompt,
            hook_profile=args.hook_profile,
            analyze_only=args.analyze_only,
            save_thumbnails=args.save_thumbnails,
        )
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
