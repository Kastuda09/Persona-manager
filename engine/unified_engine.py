"""
UNIFIED ENGINE - v2
Combines: Persona Learning (learns the real person's voice over time)
+ Content Writer (AI writes in that learned voice) + Packager
This is the "one finished product" version - each user gets their own
PersonaProfile that makes their output genuinely theirs, not a template.
"""

import os
import json
import requests
from datetime import datetime, timedelta

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


class UserVoiceProfile:
    """ Learns and stores ONE specific person's real voice over time. """

    def __init__(self, username, background_notes=""):
        self.username = username
        self.background_notes = background_notes  # e.g. "Nigerian-born architect, trader, gym daily"
        self.sample_posts = []
        self.high_performing = []
        self.last_updated = None

    def ingest_past_posts(self, posts):
        self.sample_posts.extend(posts)
        if not posts:
            return
        avg_likes = sum(p["likes"] for p in posts) / len(posts)
        self.high_performing = [p for p in posts if p["likes"] > avg_likes * 1.3]
        self.last_updated = datetime.now().isoformat()

    def update_after_new_post(self, post):
        self.sample_posts.append(post)
        avg_likes = sum(p["likes"] for p in self.sample_posts) / len(self.sample_posts)
        if post["likes"] > avg_likes * 1.3:
            self.high_performing.append(post)
        self.last_updated = datetime.now().isoformat()

    def build_voice_fingerprint(self):
        example_lines = [p["caption"] for p in self.high_performing[:5]]
        return {
            "username": self.username,
            "background": self.background_notes,
            "example_lines": example_lines,
            "data_points": len(self.sample_posts),
        }


class PersonalizedContentEngine:
    """ One user = one instance of this. Their own learned voice, their own output. """

    def __init__(self, voice_profile, niche, rules, api_key=None):
        self.voice_profile = voice_profile
        self.niche = niche
        self.rules = rules
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

    def collect_input(self, trigger_type, trigger_content):
        fingerprint = self.voice_profile.build_voice_fingerprint()
        return {
            "fingerprint": fingerprint,
            "niche": self.niche,
            "rules": self.rules,
            "trigger_type": trigger_type,
            "trigger_content": trigger_content,
        }

    def write(self, collected_input):
        if not self.api_key:
            return self._fallback_template(collected_input)

        fp = collected_input["fingerprint"]
        system_prompt = (
            f"You write social content as a specific real person, username {fp['username']}. "
            f"Their background: {fp['background']}. "
            f"Niche: {collected_input['niche']}. Rules: {collected_input['rules']}. "
            f"Here are examples of their own best performing past posts, match this exact "
            f"voice, rhythm and personality, do not sound generic: {fp['example_lines']}. "
            f"Output ONLY valid JSON with keys: hook, body, closing_question, hashtags, flagged_for_review. "
            f"No markdown, no code fences, just raw JSON."
        )
        user_prompt = f"Trigger ({collected_input['trigger_type']}): {collected_input['trigger_content']}"

        try:
            resp = requests.post(
                GEMINI_URL,
                params={"key": self.api_key},
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                    "generationConfig": {"temperature": 0.9, "maxOutputTokens": 500},
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            raw = raw.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(raw)
        except Exception:
            return self._fallback_template(collected_input)

    def _fallback_template(self, collected_input):
        headline = collected_input["trigger_content"]
        return {
            "hook": f"On my mind today: {headline}.",
            "body": f"Speaking as someone who lives this in {collected_input['niche']}, here is my honest read.",
            "closing_question": "What is your take on this?",
            "hashtags": ["#" + collected_input["niche"].replace(" ", "")],
            "flagged_for_review": False,
        }

    def package(self, draft):
        best_time = (datetime.now() + timedelta(hours=6)).strftime("%A %I:%M %p")
        return {
            "caption": draft["hook"] + " " + draft["body"] + " " + draft["closing_question"],
            "hashtags": draft["hashtags"],
            "suggested_post_time": best_time,
            "flagged_for_review": draft.get("flagged_for_review", False),
            "status": "awaiting_approval",
        }

    def run(self, trigger_type, trigger_content):
        collected = self.collect_input(trigger_type, trigger_content)
        draft = self.write(collected)
        return self.package(draft)


if __name__ == "__main__":
    joy_profile = UserVoiceProfile(
        username="joy",
        background_notes="Architect by training, builds direct-to-owner rental platforms, "
                          "trades crypto and forex, follows global politics closely, gym daily."
    )
    joy_profile.ingest_past_posts([
        {"caption": "Gold is at record highs and nobody is talking about why.", "likes": 1200, "comments": 88, "date": "2026-08-10"},
        {"caption": "Everyone is scared of a crash. I am scared of missing the bounce.", "likes": 1400, "comments": 120, "date": "2026-08-20"},
    ])

    engine = PersonalizedContentEngine(
        voice_profile=joy_profile,
        niche="trading and macro",
        rules="no buy or sell signals, always end with a question",
    )

    result = engine.run("headline", "Bitcoin surges past $77,000 while gold hits record highs")
    print(json.dumps(result, indent=2))
