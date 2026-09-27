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
from werkzeug.exceptions import RequestEntityTooLarge
from unified_engine import UserVoiceProfile
from dual_mode_manager import UnifiedManager, RealMomentSource, FictionalStorySource
import youtube_connector as yt
from feedback_engine import EngagementLearner
import heygen_connector as hg

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "mp4", "mov", "webm"}
VIDEO_EXTENSIONS = {"mp4", "mov", "webm"}

# Cap uploads at 75MB. Without this, a big video can hang the request until
# the server or browser just gives up and shows a generic connection error,
# instead of a clear, friendly message.
app.config["MAX_CONTENT_LENGTH"] = 75 * 1024 * 1024


@app.errorhandler(RequestEntityTooLarge)
def handle_large_upload(e):
    return render_template(
        "create.html",
        upload_error="That file is too large (max 75MB). Try a shorter clip or a compressed video.",
    ), 413

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

# tracks real performance data from published YouTube videos, so future
# generated drafts get steered toward what actually resonates
engagement_learner = EngagementLearner()

manager = UnifiedManager(
    voice_profile=profile,
    niche="trading, lifestyle and fitness",
    rules="stay authentic, never invent real events that did not happen, always end fictional content clearly marked as fictional",
    engagement_learner=engagement_learner,
)

# in-memory queue of drafts awaiting approval
DRAFTS = []
draft_id_counter = 1

# in-memory YouTube connection (single user for now). Holds tokens once
# they connect their channel, so we do not need them to log in every time.
YOUTUBE_ACCOUNT = {
    "connected": False,
    "access_token": None,
    "refresh_token": None,
    "channel_title": None,
    "channel_id": None,
}

# in-memory digital twin/avatar state (single user for now)
DIGITAL_TWIN = {
    "created": False,
    "twin_id": None,
    "training_clip_filename": None,
}


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
            try:
                media_url, media_type = save_uploaded_file(uploaded)
            except Exception:
                return render_template(
                    "create.html",
                    upload_error="That upload didn't go through. Please check your connection and try again.",
                )
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


def _oauth_redirect_uri():
    """Builds the callback URL Google will send the user back to. Must be
    registered exactly in Google Cloud Console as an authorized redirect URI."""
    return request.url_root.rstrip("/") + "/youtube/callback"


@app.route("/youtube/connect")
def youtube_connect():
    if not yt.is_configured():
        return render_template(
            "settings.html",
            youtube_error="YouTube isn't connected on this server yet (missing Google API credentials). "
                          "This needs to be set up once in Railway before connecting a channel.",
            youtube_account=YOUTUBE_ACCOUNT,
        )
    auth_url = yt.connect_url(_oauth_redirect_uri())
    return redirect(auth_url)


@app.route("/youtube/callback")
def youtube_callback():
    error = request.args.get("error")
    if error:
        return render_template(
            "settings.html",
            youtube_error=f"YouTube connection was not completed ({error}).",
            youtube_account=YOUTUBE_ACCOUNT,
        )

    code = request.args.get("code")
    if not code:
        return render_template(
            "settings.html",
            youtube_error="YouTube did not return an authorization code. Please try connecting again.",
            youtube_account=YOUTUBE_ACCOUNT,
        )

    try:
        tokens = yt.exchange_code(code, _oauth_redirect_uri())
        channel = yt.get_channel_info(tokens["access_token"])
    except Exception:
        return render_template(
            "settings.html",
            youtube_error="Something went wrong connecting to YouTube. Please try again.",
            youtube_account=YOUTUBE_ACCOUNT,
        )

    YOUTUBE_ACCOUNT["connected"] = True
    YOUTUBE_ACCOUNT["access_token"] = tokens.get("access_token")
    YOUTUBE_ACCOUNT["refresh_token"] = tokens.get("refresh_token", YOUTUBE_ACCOUNT.get("refresh_token"))
    YOUTUBE_ACCOUNT["channel_title"] = channel["title"] if channel else "Connected channel"
    YOUTUBE_ACCOUNT["channel_id"] = channel["channel_id"] if channel else None
    return redirect(url_for("settings"))


@app.route("/youtube/disconnect", methods=["POST"])
def youtube_disconnect():
    YOUTUBE_ACCOUNT["connected"] = False
    YOUTUBE_ACCOUNT["access_token"] = None
    YOUTUBE_ACCOUNT["refresh_token"] = None
    YOUTUBE_ACCOUNT["channel_title"] = None
    YOUTUBE_ACCOUNT["channel_id"] = None
    return redirect(url_for("settings"))


@app.route("/settings")
def settings():
    return render_template("settings.html", youtube_account=YOUTUBE_ACCOUNT, youtube_configured=yt.is_configured())


@app.route("/publish/<int:draft_id>", methods=["POST"])
def publish_to_youtube(draft_id):
    draft = next((d for d in DRAFTS if d["id"] == draft_id), None)
    if draft is None:
        return redirect(url_for("history"))

    if not YOUTUBE_ACCOUNT["connected"]:
        draft["publish_error"] = "Connect your YouTube channel in Settings before publishing."
        return redirect(url_for("history"))

    if not draft.get("media_url") or draft.get("media_type") != "video":
        draft["publish_error"] = "Only video posts can be published to YouTube. This draft has no video attached."
        return redirect(url_for("history"))

    filename = draft["media_url"].rsplit("/", 1)[-1]
    video_path = os.path.join(UPLOAD_FOLDER, filename)

    try:
        access_token = YOUTUBE_ACCOUNT["access_token"]
        try:
            video_id = yt.publish_video(
                access_token,
                video_path,
                title=draft.get("caption_or_script", "New video")[:90],
                description=draft.get("caption_or_script", "") + "\n\n" + " ".join(draft.get("hashtags", [])),
                tags=[t.lstrip("#") for t in draft.get("hashtags", [])],
            )
        except Exception:
            refreshed = yt.refresh_access_token(YOUTUBE_ACCOUNT["refresh_token"])
            YOUTUBE_ACCOUNT["access_token"] = refreshed["access_token"]
            video_id = yt.publish_video(
                YOUTUBE_ACCOUNT["access_token"],
                video_path,
                title=draft.get("caption_or_script", "New video")[:90],
                description=draft.get("caption_or_script", "") + "\n\n" + " ".join(draft.get("hashtags", [])),
                tags=[t.lstrip("#") for t in draft.get("hashtags", [])],
            )
        draft["youtube_video_id"] = video_id
        draft["published"] = True
        draft.pop("publish_error", None)
    except Exception:
        draft["publish_error"] = "Publishing to YouTube failed. Please try again shortly."

    return redirect(url_for("history"))


@app.route("/sync/<int:draft_id>", methods=["POST"])
def sync_performance(draft_id):
    """Pulls the latest real view/like/comment data for a published video
    and feeds it into the engagement learner, so the NEXT generated draft
    is informed by how this one actually performed."""
    draft = next((d for d in DRAFTS if d["id"] == draft_id), None)
    if draft is None or not draft.get("published") or not draft.get("youtube_video_id"):
        return redirect(url_for("history"))

    if not YOUTUBE_ACCOUNT["connected"]:
        draft["sync_error"] = "YouTube is not connected."
        return redirect(url_for("history"))

    try:
        access_token = YOUTUBE_ACCOUNT["access_token"]
        try:
            entry = engagement_learner.sync_video(access_token, draft["youtube_video_id"])
        except Exception:
            refreshed = yt.refresh_access_token(YOUTUBE_ACCOUNT["refresh_token"])
            YOUTUBE_ACCOUNT["access_token"] = refreshed["access_token"]
            entry = engagement_learner.sync_video(YOUTUBE_ACCOUNT["access_token"], draft["youtube_video_id"])

        if entry:
            draft["performance"] = entry
            draft.pop("sync_error", None)
        else:
            draft["sync_error"] = "Could not find performance data for this video yet."
    except Exception:
        draft["sync_error"] = "Could not fetch performance data right now. Please try again shortly."

    return redirect(url_for("history"))


@app.route("/avatar/setup", methods=["GET", "POST"])
def avatar_setup():
    if request.method == "GET":
        return render_template(
            "avatar.html",
            digital_twin=DIGITAL_TWIN,
            heygen_configured=hg.is_configured(),
        )

    if not hg.is_configured():
        return render_template(
            "avatar.html",
            digital_twin=DIGITAL_TWIN,
            heygen_configured=False,
            avatar_error="HeyGen isn't connected on this server yet (missing API key).",
        )

    uploaded = request.files.get("training_clip")
    if not uploaded or uploaded.filename == "":
        return render_template(
            "avatar.html",
            digital_twin=DIGITAL_TWIN,
            heygen_configured=True,
            avatar_error="Please choose a short video clip of yourself speaking clearly first.",
        )

    try:
        media_url, media_type = save_uploaded_file(uploaded)
        if not media_url:
            raise ValueError("unsupported file type")
        filename = media_url.rsplit("/", 1)[-1]
        clip_path = os.path.join(UPLOAD_FOLDER, filename)

        asset_reference = hg.upload_training_clip(clip_path)
        twin_id = hg.create_digital_twin(asset_reference, twin_name="Joy Digital Twin")

        DIGITAL_TWIN["created"] = True
        DIGITAL_TWIN["twin_id"] = twin_id
        DIGITAL_TWIN["training_clip_filename"] = filename
        return redirect(url_for("avatar_setup"))
    except Exception:
        return render_template(
            "avatar.html",
            digital_twin=DIGITAL_TWIN,
            heygen_configured=True,
            avatar_error="Something went wrong creating your digital twin. Please try again with a clear, short clip.",
        )


@app.route("/generate_avatar_video/<int:draft_id>", methods=["POST"])
def generate_avatar_video_route(draft_id):
    """Takes an approved draft's script/caption and generates a brand new
    video of the user's digital twin delivering it, no filming needed."""
    draft = next((d for d in DRAFTS if d["id"] == draft_id), None)
    if draft is None:
        return redirect(url_for("history"))

    if not DIGITAL_TWIN["created"]:
        draft["avatar_error"] = "Set up your digital twin in Settings before generating avatar videos."
        return redirect(url_for("history"))

    try:
        script = draft.get("caption_or_script", "")
        video_id = hg.generate_avatar_video(DIGITAL_TWIN["twin_id"], script, title=f"Persona video {draft_id}")
        draft["heygen_video_id"] = video_id
        draft["avatar_video_status"] = "processing"
        draft.pop("avatar_error", None)
    except Exception:
        draft["avatar_error"] = "Could not start avatar video generation. Please try again shortly."

    return redirect(url_for("history"))


@app.route("/check_avatar_video/<int:draft_id>", methods=["POST"])
def check_avatar_video_route(draft_id):
    """Polls HeyGen once for whether the avatar video is ready yet, and
    stores the finished video URL on the draft once it is."""
    draft = next((d for d in DRAFTS if d["id"] == draft_id), None)
    if draft is None or not draft.get("heygen_video_id"):
        return redirect(url_for("history"))

    try:
        result = hg.check_video_status(draft["heygen_video_id"])
        draft["avatar_video_status"] = result["status"]
        if result["status"] == "completed":
            draft["avatar_video_url"] = result["video_url"]
        draft.pop("avatar_error", None)
    except Exception:
        draft["avatar_error"] = "Could not check video status right now. Please try again shortly."

    return redirect(url_for("history"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False) 
