"""Local web UI for Viral Hook Extractor."""
import os
import shutil
import uuid
from pathlib import Path

from flask import Flask, abort, render_template, request, send_from_directory, url_for

from clipper import run_pipeline
from utils import ensure_dir


BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = Path(ensure_dir(str(BASE_DIR / "web_runs")))
UPLOADS_DIR = Path(ensure_dir(str(BASE_DIR / "web_uploads")))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024


def _allowed_file(filename: str, allowed: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/run")
def run_job():
    video = request.files.get("video")
    captions = request.files.get("captions_srt")

    if not video or not video.filename:
        return render_template("index.html", error="Upload an MP4 video first."), 400
    if not _allowed_file(video.filename, {"mp4", "mov", "mkv"}):
        return render_template("index.html", error="Video must be MP4, MOV, or MKV."), 400
    if captions and captions.filename and not _allowed_file(captions.filename, {"srt"}):
        return render_template("index.html", error="Caption file must be an SRT."), 400

    run_id = uuid.uuid4().hex[:10]
    run_dir = RUNS_DIR / run_id
    upload_dir = UPLOADS_DIR / run_id
    ensure_dir(str(run_dir))
    ensure_dir(str(upload_dir))

    video_path = upload_dir / video.filename
    video.save(video_path)

    captions_path = ""
    if captions and captions.filename:
        saved_srt = upload_dir / captions.filename
        captions.save(saved_srt)
        captions_path = str(saved_srt)

    try:
        result = run_pipeline(
            video_path=str(video_path),
            clips=int(request.form.get("clips", 5)),
            min_duration=float(request.form.get("min_duration", 20)),
            max_duration=float(request.form.get("max_duration", 60)),
            face_track=bool(request.form.get("face_track")),
            output_dir=str(run_dir),
            captions_srt_path=captions_path,
            save_thumbnails=bool(request.form.get("save_thumbnails")),
        )
    except Exception as exc:
        shutil.rmtree(run_dir, ignore_errors=True)
        return render_template("index.html", error=str(exc)), 500

    clips = [Path(path).name for path in result["clips"]]
    thumbnails = []
    if result.get("thumbnails_dir"):
        thumb_dir = Path(result["thumbnails_dir"])
        if thumb_dir.exists():
            thumbnails = sorted(item.name for item in thumb_dir.iterdir() if item.is_file())

    return render_template(
        "result.html",
        run_id=run_id,
        clips=clips,
        thumbnails=thumbnails,
        hooks=result["hooks"],
        hooks_path=Path(result["hooks_path"]).name,
    )


@app.get("/files/<run_id>/<path:filename>")
def serve_run_file(run_id: str, filename: str):
    base_dir = RUNS_DIR / run_id
    target = base_dir / filename
    if not target.exists():
        abort(404)
    return send_from_directory(base_dir, filename, as_attachment=False)


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
