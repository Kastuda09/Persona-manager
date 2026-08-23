"""
MAIN WEB APP
A simple Flask site with:
- A home page
- A "create post" form (real moment or fictional story)
- An approval queue (drafts sit here until Joy approves or rejects)
- Everything stored in memory for now (upgrade to a real database later)
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "engine"))

from flask import Flask, render_template, request, redirect, url_for
from unified_engine import UserVoiceProfile
from dual_mode_manager import UnifiedManager, RealMomentSource, FictionalStorySource

app = Flask(__name__)

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


@app.route("/")
def home():
    return render_template("home.html", pending_count=len([d for d in DRAFTS if d["approved"] is None]))


@app.route("/create", methods=["GET", "POST"])
def create():
    global draft_id_counter
    if request.method == "POST":
        mode = request.form.get("mode")
        if mode == "real":
            source = RealMomentSource(
                file_reference=request.form.get("file_reference", "no_file_provided"),
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
