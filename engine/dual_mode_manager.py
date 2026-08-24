"""
DUAL-MODE INPUT LAYER
Two different content sources feed into the SAME management pipeline
(approval, scheduling, posting) we already built.

Mode A: REAL - user's own real photos/videos, managed and captioned.
Mode B: FICTIONAL - fully AI generated character/story, from just a
        script idea or concept, no real footage needed.

Both modes produce the SAME shaped output so the manager, approval
queue, and posting system don't care which mode it came from.
"""

import os
import json
import requests
from datetime import datetime, timedelta

GEMINI_MODEL = "gemini-flash-latest"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


class ContentSource:
    """ Base shape both modes must produce, so the manager stays universal. """
    def to_draft(self):
        raise NotImplementedError


class RealMomentSource(ContentSource):
    def __init__(self, file_reference, moment_description):
        self.file_reference = file_reference
        self.moment_description = moment_description
        self.mode = "real"

    def to_draft(self):
        return {
            "mode": self.mode,
            "file_reference": self.file_reference,
            "seed_content": self.moment_description,
        }


class FictionalStorySource(ContentSource):
    """ e.g. a kids' animated story, or a scripted fictional persona. """
    def __init__(self, story_idea, character_name=None, audience="general"):
        self.story_idea = story_idea
        self.character_name = character_name or "Unnamed Character"
        self.audience = audience
        self.mode = "fictional"

    def to_draft(self):
        return {
            "mode": self.mode,
            "character_name": self.character_name,
            "audience": self.audience,
            "seed_content": self.story_idea,
        }


class UnifiedManager:
    """ Same manager, handles either source type identically from here on. """
    def __init__(self, voice_profile, niche, rules, api_key=None):
        self.voice_profile = voice_profile
        self.niche = niche
        self.rules = rules
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

    def process(self, source: ContentSource):
        base = source.to_draft()
        fingerprint = self.voice_profile.build_voice_fingerprint()

        if not self.api_key:
            result = self._fallback(base, reason="no_api_key")
            result["mode"] = base["mode"]
            result["status"] = "awaiting_approval"
            result["suggested_post_time"] = (datetime.now() + timedelta(hours=3)).strftime("%A %I:%M %p")
            return result

        if base["mode"] == "real":
            instruction = (
                f"This is a REAL photo/video the user actually captured. Their rough, unpolished "
                f"note about it is: '{base['seed_content']}'. Do NOT just repeat or lightly rephrase "
                f"this note. Instead, transform it into a genuinely well-written, scroll-stopping "
                f"social media caption in their authentic voice: add a strong hook line, texture, "
                f"personality and rhythm, the way a skilled ghostwriter would elevate a rough voice "
                f"memo into a finished post. Never invent events, people, places or details that "
                f"were not implied by their note."
            )
        else:
            instruction = (
                f"This is a FULLY FICTIONAL story for a character named {base['character_name']}, "
                f"aimed at audience: {base['audience']}. Build a short, vivid, well-crafted script or "
                f"story beat from this raw idea: '{base['seed_content']}'. Do not just restate the "
                f"idea, actually develop it with scene detail, character voice and a clear beginning "
                f"and turn, appropriate for the stated audience. It is understood to be fictional, "
                f"not a real event."
            )

        system_prompt = (
            f"You are an elite ghostwriter and social media content manager for "
            f"{fingerprint['username']}. Niche: {self.niche}. Rules: {self.rules}. "
            f"Voice reference lines from their own best performing past posts: "
            f"{fingerprint['example_lines']}. Match that tone, rhythm and personality closely. "
            f"{instruction} "
            f"Output ONLY valid JSON with keys: caption_or_script, hashtags, presenter_note, "
            f"flagged_for_review. presenter_note should be a short, specific note about what you "
            f"changed or emphasized, not a generic phrase. No markdown, no code fences, just raw JSON."
        )

        try:
            resp = requests.post(
                GEMINI_URL,
                params={"key": self.api_key},
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": base["seed_content"]}]}],
                    "generationConfig": {"temperature": 0.9, "maxOutputTokens": 500},
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            raw = raw.strip().replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)
        except Exception as e:
            result = self._fallback(base, reason=str(e))

        result["mode"] = base["mode"]
        result["status"] = "awaiting_approval"
        result["suggested_post_time"] = (datetime.now() + timedelta(hours=3)).strftime("%A %I:%M %p")
        return result

    def _fallback(self, base, reason="unknown"):
        return {
            "caption_or_script": f"Draft based on: {base['seed_content']}",
            "hashtags": ["#" + self.niche.replace(" ", "").replace(",", "")],
            "presenter_note": f"AI generation unavailable right now (reason: {reason}), showing a basic placeholder instead.",
            "flagged_for_review": True,
        }


if __name__ == "__main__":
    from unified_engine import UserVoiceProfile

    profile = UserVoiceProfile(username="joy", background_notes="Architect, trader, gym daily")
    profile.ingest_past_posts([
        {"caption": "Gym was empty today, felt like I owned the place.", "likes": 1100, "comments": 75, "date": "2026-08-12"},
    ])

    manager = UnifiedManager(voice_profile=profile, niche="lifestyle", rules="stay authentic, no fabricated real events")

    real_source = RealMomentSource(
        file_reference="gym_photo_aug23.jpg",
        moment_description="back at the gym after a week off"
    )
    fictional_source = FictionalStorySource(
        story_idea="a curious fox who is scared of the dark learns to make his own light",
        character_name="Finn the Fox",
        audience="children"
    )

    print("--- REAL MODE ---")
    print(json.dumps(manager.process(real_source), indent=2))
    print("--- FICTIONAL MODE ---")
    print(json.dumps(manager.process(fictional_source), indent=2))
