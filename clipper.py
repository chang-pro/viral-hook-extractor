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

from dotenv import load_dotenv

from chunker import chunk_video, get_duration
from analyzer import analyze_video
from cutter import cut_clip
from reframer import reframe_clip
from captioner import generate_ass, burn_captions
from utils import ensure_dir, cleanup_files


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract viral hooks from Jamaican video content using Gemini AI."
    )
    parser.add_argument("video", help="Path to input video file (MP4)")
    parser.add_argument("--clips", type=int, default=5,
                        help="Number of clips to extract (default: 5)")
    parser.add_argument("--min", type=float, default=20, dest="min_duration",
                        help="Minimum clip duration in seconds (default: 20)")
    parser.add_argument("--max", type=float, default=60, dest="max_duration",
                        help="Maximum clip duration in seconds (default: 60)")
    parser.add_argument("--face-track", action="store_true",
                        help="Use face detection for smarter 9:16 reframing (slower)")
    parser.add_argument("--output", default="output",
                        help="Output directory (default: ./output)")
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


def main():
    args = parse_args()

    # Load API key
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found.")
        print("Create a .env file with: GEMINI_API_KEY=your_key_here")
        print("Get a free key at: https://ai.google.dev")
        sys.exit(1)

    video_path = os.path.abspath(args.video)
    if not os.path.isfile(video_path):
        print(f"ERROR: Video file not found: {video_path}")
        sys.exit(1)

    output_dir = ensure_dir(args.output)
    temp_dir = tempfile.mkdtemp(prefix="clipper_")
    temp_files_to_clean = [temp_dir]

    print(f"\nJamaican Video Clip Extractor")
    print(f"{'='*40}")
    print(f"Input:   {os.path.basename(video_path)}")
    print(f"Clips:   {args.clips}")
    print(f"Output:  {output_dir}/")
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
        hooks = analyze_video(video_path, api_key, chunks, n_clips=args.clips)

        # Validate and clamp durations
        hooks = [validate_hook_duration(h, args.min_duration, args.max_duration) for h in hooks]

        # Save hooks.json
        hooks_path = os.path.join(output_dir, "hooks.json")
        with open(hooks_path, "w", encoding="utf-8") as f:
            json.dump(hooks, f, indent=2, ensure_ascii=False)
        print(f"  Saved hook data → {hooks_path}")

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
            htype = hook.get("type", "unknown")
            print(f"  Clip {i+1}: virality={vscore} type={htype} "
                  f"({hook['start']:.1f}s – {hook['end']:.1f}s)")

        print(f"\nStep 5/5: Reframing to 9:16 and burning captions...")
        final_clips = []
        for i, hook, raw_path in raw_clips:
            vscore = hook.get("virality_score") or round((hook.get("score", 0)) * 10)
            htype = hook.get("type", "unknown")

            # Reframe to 9:16
            reframed_path = os.path.join(temp_dir, f"reframed_{i:02d}.mp4")
            reframe_clip(raw_path, reframed_path, face_track=args.face_track)

            # Generate karaoke captions (.ass format)
            clip_start_abs = max(0.0, hook["start"] - 1.5)  # account for pad_start
            ass = generate_ass(hook.get("transcript", []), clip_start_abs)

            # Burn captions
            final_name = f"clip_{i+1:02d}_virality{vscore}_{htype}.mp4"
            final_path = os.path.join(output_dir, final_name)
            burn_captions(reframed_path, ass, final_path)

            final_clips.append(final_path)
            print(f"  → {final_name}")

        # Print summary
        print(f"\n{'='*40}")
        print(f"Done! {len(final_clips)} clips saved to: {output_dir}/")
        print()
        for i, (_, hook, _) in enumerate(raw_clips):
            vscore = hook.get("virality_score") or round((hook.get("score", 0)) * 10)
            htype = hook.get("type", "?")
            reason = hook.get("reason", "")
            hook_line = hook.get("hook_line", "")
            h = hook.get("hook_score", "-")
            f_ = hook.get("flow_score", "-")
            v = hook.get("value_score", "-")
            t = hook.get("trend_score", "-")
            print(f"  #{i+1} virality={vscore} [{htype}] H:{h} F:{f_} V:{v} T:{t}")
            if hook_line:
                print(f"      hook line: \"{hook_line}\"")
            if reason:
                print(f"      reason:    {reason}")
        print()

    except KeyboardInterrupt:
        print("\nCancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
    finally:
        print("Cleaning up temp files...")
        cleanup_files(temp_files_to_clean)


if __name__ == "__main__":
    main()
