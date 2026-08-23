"""
MEDIA-AWARE MANAGER LAYER
Handles the real scenario: user uploads their own real photo/video,
the AI turns it into a properly captioned, on-brand post in their voice,
and presents it back for a simple approve/reject, exactly like a manager
would say "check this out, what do you think?"
No fabricated scenes - only real user-submitted media gets used.
"""

import os
import json
import requests
from datetime import datetime, timedelta

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


class MediaSubmission:
    """ One real photo/video the user actually took and uploaded. """
    def __init__(self, file_reference, moment_description, date=None):
        self.file_reference = file_reference          # e.g. path or upload id
        self.moment_description = moment_description  # user's own quick note, e.g. "leg day, tired but did it"
        self.date = date or datetime.now().isoformat()


class ContentManager:
    def __init__(self, voice_profile, niche, rules, api_key=None):
        self.voice_profile = voice_profile
        self.niche = niche
        self.rules = rules
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

    def process_submission(self, submission: MediaSubmission):
        fingerprint = self.voice_profile.build_voice_fingerprint()

        if not self.api_key:
            result = self._fallback(submission)
            result["file_reference"] = submission.file_reference
            result["status"] = "awaiting_approval"
            result["suggested_post_time"] = (datetime.now() + timedelta(hours=3)).strftime("%A %I:%M %p")
            return result

        system_prompt = (
            f"You are the content manager for a real person, username {fingerprint['username']}. "
            f"Their background: {fingerprint['background']}. Niche: {self.niche}. "
            f"Rules: {self.rules}. Match their real humor and voice using these example lines "
            f"from their own best posts: {fingerprint['example_lines']}. "
            f"They just shared a real photo/video with this note: '{submission.moment_description}'. "
            f"Write a caption for it in their exact voice. If they usually joke, make it funny, "
            f"not generic. Output ONLY valid JSON with keys: caption, hashtags, presenter_note "
            f"(a short first-person line like 'here is what I put together, check it out'). "
            f"No markdown, no code fences, just raw JSON."
        )

        try:
            resp = requests.post(
                GEMINI_URL,
                params={"key": self.api_key},
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": submission.moment_description}]}],
                    "generationConfig": {"temperature": 0.9, "maxOutputTokens": 400},
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            raw = raw.strip().replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)
        except Exception:
            result = self._fallback(submission)

        result["file_reference"] = submission.file_reference
        result["status"] = "awaiting_approval"
        result["suggested_post_time"] = (datetime.now() + timedelta(hours=3)).strftime("%A %I:%M %p")
        return result

    def _fallback(self, submission):
        return {
            "caption": f"Real moment: {submission.moment_description}",
            "hashtags": ["#" + self.niche.replace(" ", "")],
            "presenter_note": "Here is what I put together from what you shared, take a look.",
        }


if __name__ == "__main__":
    from unified_engine import UserVoiceProfile

    joy_profile = UserVoiceProfile(
        username="joy",
        background_notes="Architect, trader, gym daily, has a joking easygoing side on lifestyle content."
    )
    joy_profile.ingest_past_posts([
        {"caption": "Skipped leg day and my legs still filed a complaint.", "likes": 980, "comments": 60, "date": "2026-08-05"},
        {"caption": "Gym was empty today, felt like I owned the place.", "likes": 1100, "comments": 75, "date": "2026-08-12"},
    ])

    manager = ContentManager(
        voice_profile=joy_profile,
        niche="lifestyle and fitness",
        rules="only use real submitted media, never invent events that did not happen",
    )

    submission = MediaSubmission(
        file_reference="gym_photo_aug23.jpg",
        moment_description="finally went back to the gym after skipping a week, felt out of shape but pushed through"
    )

    draft = manager.process_submission(submission)
    print(json.dumps(draft, indent=2))
