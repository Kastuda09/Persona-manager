"""
MAIN WEB APP
A simple Flask site with:
- A home page
- A "create post" form (real moment or fictional story), including real
  photo/video upload for Real Moment mode
- An approval queue (drafts sit here until Joy approves or rejects)
- Everything stored in memory for now (upgrade to a real database later)
"""

import os
import sys
import uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "engine"))

from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from unified_engine import UserVoiceProfile
from dual_mode_manager import UnifiedManager, RealMomentSource, FictionalStorySource

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "mp4", "mov", "webm"}
VIDEO_EXTENSIONS = {"mp4", "mov", "webm"}

# --- one demo profile for now, this becomes per-user accounts later ---
profile = UserVoiceProfile(
    username="joy",
    background_notes="Architect by training, builds direct-to-owner rental platforms, "
                      "trades crypto and forex, follows global politics closely, gym daily."
)
profile.ingest_past_posts([
    {"caption": "Gold is at record highs and nobody is talking about why.", "likes": 1200, "comments": 88, "date": "2026-08-10"},
    {"caption": "Everyone is scared of a crash. I am scared of missing the bounce.", "likes": 1400, "comments": 120, "date": "2026-08-20"},
])

manager = UnifiedManager(
    voice_profile=profile,
    niche="trading, lifestyle and fitness",
    rules="stay authentic, never invent real events that did not happen, always end fictional content clearly marked as fictional",
)

# in-memory queue of drafts awaiting approval
DRAFTS = []
draft_id_counter = 1


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_file(file_storage):
    """Saves the uploaded file to disk and returns (media_url, media_type), or (None, None)."""
    if not file_storage or file_storage.filename == "":
        return None, None
    if not allowed_file(file_storage.filename):
        return None, None

    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(UPLOAD_FOLDER, unique_name))

    media_type = "video" if ext in VIDEO_EXTENSIONS else "image"
    media_url = url_for("uploaded_file", filename=unique_name)
    return media_url, media_type


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/")
def home():
    return render_template("home.html", pending_count=len([d for d in DRAFTS if d["approved"] is None]))


@app.route("/create", methods=["GET", "POST"])
def create():
    global draft_id_counter
    if request.method == "POST":
        mode = request.form.get("mode")
        media_url, media_type = None, None

        if mode == "real":
            uploaded = request.files.get("media_file")
            media_url, media_type = save_uploaded_file(uploaded)
            file_reference = uploaded.filename if uploaded and uploaded.filename else "no_file_provided"
            source = RealMomentSource(
                file_reference=file_reference,
                moment_description=request.form.get("description", ""),
            )
        else:
            source = FictionalStorySource(
                story_idea=request.form.get("description", ""),
                character_name=request.form.get("character_name", "Unnamed Character"),
                audience=request.form.get("audience", "general"),
            )

        result = manager.process(source)
        result["id"] = draft_id_counter
        result["approved"] = None
        result["media_url"] = media_url
        result["media_type"] = media_type
        draft_id_counter += 1
        DRAFTS.append(result)
        return redirect(url_for("queue"))

    return render_template("create.html")


@app.route("/queue")
def queue():
    pending = [d for d in DRAFTS if d["approved"] is None]
    return render_template("queue.html", drafts=pending)


@app.route("/approve/<int:draft_id>", methods=["POST"])
def approve(draft_id):
    for d in DRAFTS:
        if d["id"] == draft_id:
            d["approved"] = True
    return redirect(url_for("queue"))


@app.route("/reject/<int:draft_id>", methods=["POST"])
def reject(draft_id):
    for d in DRAFTS:
        if d["id"] == draft_id:
            d["approved"] = False
    return redirect(url_for("queue"))


@app.route("/history")
def history():
    decided = [d for d in DRAFTS if d["approved"] is not None]
    return render_template("history.html", drafts=decided)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
