"""
Persona Learning Layer - makes the engine learn the REAL user's voice
instead of using a generic templated persona.

The idea: when someone connects their Instagram, we pull their past
posts and which ones performed best (likes/comments/shares), and use
that as the "personality fingerprint" that guides every future post.
This fingerprint grows and updates over time as new posts perform.
"""

import json
from datetime import datetime


class UserVoiceProfile:
    def __init__(self, username):
        self.username = username
        self.sample_posts = []
        self.high_performing = []
        self.tone_notes = []
        self.last_updated = None

    def ingest_past_posts(self, posts):
        self.sample_posts.extend(posts)
        if not posts:
            return
        avg_likes = sum(p["likes"] for p in posts) / len(posts)
        self.high_performing = [p for p in posts if p["likes"] > avg_likes * 1.3]
        self.last_updated = datetime.now().isoformat()

    def build_voice_fingerprint(self):
        if not self.high_performing:
            return {
                "username": self.username,
                "fingerprint": "Not enough data yet - using neutral starter tone.",
                "sample_lines": [],
            }

        example_lines = [p["caption"] for p in self.high_performing[:5]]
        return {
            "username": self.username,
            "fingerprint": (
                f"Based on {len(self.high_performing)} of this user's best performing posts, "
                f"match their real sentence rhythm, humor, and word choice. Do not sound generic "
                f"or like a template. Sound like THEM specifically."
            ),
            "sample_lines": example_lines,
        }

    def update_after_new_post(self, post):
        self.sample_posts.append(post)
        avg_likes = sum(p["likes"] for p in self.sample_posts) / len(self.sample_posts)
        if post["likes"] > avg_likes * 1.3:
            self.high_performing.append(post)
        self.last_updated = datetime.now().isoformat()


if __name__ == "__main__":
    profile = UserVoiceProfile(username="joy_the_trader")

    past_posts = [
        {"caption": "Markets do not care about your feelings. Neither do I. Bitcoin is up, act accordingly.", "likes": 900, "comments": 40, "date": "2026-08-01"},
        {"caption": "Gold is at record highs and nobody is talking about why.", "likes": 1200, "comments": 88, "date": "2026-08-10"},
        {"caption": "Just a normal Tuesday update on rates.", "likes": 150, "comments": 3, "date": "2026-08-15"},
        {"caption": "Everyone is scared of a crash. I am scared of missing the bounce.", "likes": 1400, "comments": 120, "date": "2026-08-20"},
    ]

    profile.ingest_past_posts(past_posts)
    fingerprint = profile.build_voice_fingerprint()
    print(json.dumps(fingerprint, indent=2))
