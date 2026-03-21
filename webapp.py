"""Local web UI for Viral Hook Extractor."""
import shutil
import uuid
from pathlib import Path

from flask import Flask, abort, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

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

    video_name = secure_filename(video.filename)
    if not video_name:
        return render_template("index.html", error="Video filename is invalid."), 400
    video_path = upload_dir / video_name
    video.save(video_path)

    captions_path = ""
    if captions and captions.filename:
        srt_name = secure_filename(captions.filename)
        if not srt_name:
            return render_template("index.html", error="SRT filename is invalid."), 400
        saved_srt = upload_dir / srt_name
        captions.save(saved_srt)
        captions_path = str(saved_srt)

    try:
        clips = int(request.form.get("clips", 5))
        min_duration = float(request.form.get("min_duration", 20))
        max_duration = float(request.form.get("max_duration", 60))
        result = run_pipeline(
            video_path=str(video_path),
            clips=clips,
            length_preset=request.form.get("length_preset", "short"),
            min_duration=min_duration,
            max_duration=max_duration,
            face_track=bool(request.form.get("face_track")),
            output_dir=str(run_dir),
            captions_srt_path=captions_path,
            focus_prompt=request.form.get("focus_prompt", "").strip(),
            hook_profile=request.form.get("hook_profile", "hot").strip() or "hot",
            analyze_only=bool(request.form.get("analyze_only")),
            save_thumbnails=bool(request.form.get("save_thumbnails")),
        )
    except ValueError as exc:
        shutil.rmtree(run_dir, ignore_errors=True)
        shutil.rmtree(upload_dir, ignore_errors=True)
        return render_template("index.html", error=str(exc)), 400
    except Exception as exc:
        shutil.rmtree(run_dir, ignore_errors=True)
        shutil.rmtree(upload_dir, ignore_errors=True)
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
        analyze_only=result.get("analyze_only", False),
    )


@app.get("/files/<run_id>/<path:filename>")
def serve_run_file(run_id: str, filename: str):
    base_dir = (RUNS_DIR / run_id).resolve()
    target = (base_dir / filename).resolve()
    if base_dir not in target.parents and target != base_dir:
        abort(404)
    if not target.exists() or not target.is_file():
        abort(404)
    return send_from_directory(target.parent, target.name, as_attachment=False)


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
