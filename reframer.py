"""Reframe clips to 9:16 vertical format using FFmpeg."""
import os
from utils import run_ffmpeg


def _get_face_x_offset(video_path: str, output_width: int, output_height: int) -> int:
    """
    Detect face position in first few frames and return best crop x-offset.
    Falls back to center crop if no face is detected.
    """
    try:
        import cv2
        import mediapipe as mp

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        face_detector = mp.solutions.face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=0.5
        )

        face_x_positions = []
        frames_checked = 0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        # Sample frames from the first 10 seconds
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        sample_frames = [int(i * fps) for i in range(0, min(10, int(total_frames / fps)))]

        for frame_num in sample_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if not ret:
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_detector.process(rgb)

            if results.detections:
                for det in results.detections:
                    bbox = det.location_data.relative_bounding_box
                    face_center_x = (bbox.xmin + bbox.width / 2) * frame_width
                    face_x_positions.append(face_center_x)

            frames_checked += 1
            if frames_checked >= 5:
                break

        cap.release()
        face_detector.close()

        if not face_x_positions:
            return None

        avg_face_x = sum(face_x_positions) / len(face_x_positions)

        # Calculate x offset to center the crop on the face
        x_offset = int(avg_face_x - output_width / 2)
        # Clamp to valid range
        x_offset = max(0, min(x_offset, frame_width - output_width))
        return x_offset

    except Exception as e:
        print(f"    Face detection failed, using center crop: {e}")
        return None


def reframe_clip(
    input_path: str,
    output_path: str,
    face_track: bool = False,
    target_width: int = 1080,
    target_height: int = 1920,
) -> str:
    """
    Reframe a clip to 9:16 vertical format.
    If face_track=True, tries to center crop on detected face.
    Returns output_path.
    """
    x_offset = None

    if face_track:
        # Calculate intermediate crop dimensions based on source
        # We need to know source dimensions first
        try:
            import subprocess
            result = subprocess.run([
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0",
                input_path
            ], capture_output=True, text=True)
            w, h = map(int, result.stdout.strip().split(","))
            crop_w = int(h * 9 / 16)
            x_offset = _get_face_x_offset(input_path, crop_w, h)
        except Exception:
            pass

    if x_offset is not None:
        # Use face-tracked x position for crop
        try:
            result = __import__("subprocess").run([
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0",
                input_path
            ], capture_output=True, text=True)
            w, h = map(int, result.stdout.strip().split(","))
            crop_w = int(h * 9 / 16)
            vf = f"crop={crop_w}:{h}:{x_offset}:0,scale={target_width}:{target_height}:flags=lanczos"
        except Exception:
            x_offset = None  # fall through to center crop

    if x_offset is None:
        # Center crop: take full height, width = height * 9/16
        vf = (
            f"crop=in_h*9/16:in_h:(in_w-in_h*9/16)/2:0,"
            f"scale={target_width}:{target_height}:flags=lanczos"
        )

    run_ffmpeg([
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        "-crf", "23",
        output_path
    ], f"reframe {os.path.basename(output_path)}")

    return output_path
