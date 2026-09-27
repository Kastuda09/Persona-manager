"""
FEEDBACK LOOP ENGINE
Closes the loop: after a video is published to YouTube, this pulls real
performance data (views, likes, comments, watch time signals) and turns it
into plain-language "engagement notes" that get added to the user's voice
fingerprint, so future generated content is steered by what actually
resonated with their real audience, not just their past posting style.

This works alongside UserVoiceProfile (in unified_engine.py) rather than
replacing it: that class handles VOICE (how they sound), this handles
STRATEGY (what topics/formats actually land with their audience).
"""

import requests
from datetime import datetime

YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_COMMENTS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"


def fetch_video_performance(access_token, video_id):
    """Pulls view/like/comment counts for one published video."""
    resp = requests.get(YOUTUBE_VIDEOS_URL, params={
        "part": "statistics,snippet",
        "id": video_id,
    }, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        return None
    stats = items[0]["statistics"]
    return {
        "video_id": video_id,
        "title": items[0]["snippet"]["title"],
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
    }


def fetch_top_comments(access_token, video_id, max_results=20):
    """Pulls the actual text of top comments, so the AI can read real
    audience reactions, not just numbers."""
    resp = requests.get(YOUTUBE_COMMENTS_URL, params={
        "part": "snippet",
        "videoId": video_id,
        "order": "relevance",
        "maxResults": max_results,
        "textFormat": "plainText",
    }, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    comments = []
    for item in items:
        snippet = item["snippet"]["topLevelComment"]["snippet"]
        comments.append({
            "text": snippet["textDisplay"],
            "likes": snippet.get("likeCount", 0),
        })
    return comments


class EngagementLearner:
    """Turns raw performance data + comments into engagement notes the
    content engine can factor into future drafts. Keeps a running history
    per published post so patterns can build up over time."""

    def __init__(self):
        self.history = []  # list of {video_id, title, views, likes, comments, comment_samples, notes}

    def record_performance(self, performance, comments):
        entry = {
            "video_id": performance["video_id"],
            "title": performance["title"],
            "views": performance["views"],
            "likes": performance["likes"],
            "comment_count": performance["comments"],
            "top_comment_samples": [c["text"] for c in comments[:8]],
            "recorded_at": datetime.now().isoformat(),
        }
        self.history.append(entry)
        return entry

    def build_engagement_notes(self):
        """Produces a short, plain-language summary the content engine's
        system prompt can include, e.g. 'audience responds well to X, less
        to Y'. If there is not enough data yet, says so plainly instead of
        guessing."""
        if not self.history:
            return "No published performance data yet. Rely on voice fingerprint only."

        sorted_by_views = sorted(self.history, key=lambda h: h["views"], reverse=True)
        top = sorted_by_views[:3]
        bottom = sorted_by_views[-3:] if len(sorted_by_views) > 3 else []

        top_titles = [h["title"] for h in top]
        top_comment_flavor = [c for h in top for c in h["top_comment_samples"]][:10]

        notes = (
            f"Based on {len(self.history)} published videos so far, the best performing titles/topics were: "
            f"{top_titles}. Real audience comments on the best performers included: {top_comment_flavor}. "
        )
        if bottom:
            notes += f"Lower performing topics were: {[h['title'] for h in bottom]}. "
        notes += (
            "Use this to lean toward the topics, tone and format that actually resonated, and be "
            "cautious about repeating the lower performing angle, without abandoning the user's "
            "authentic voice."
        )
        return notes

    def sync_video(self, access_token, video_id):
        """Convenience: pulls both stats and comments for one video and
        records them in one call. This is what gets triggered periodically
        (e.g. a day after posting) for every published draft."""
        performance = fetch_video_performance(access_token, video_id)
        if performance is None:
            return None
        comments = []
        try:
            comments = fetch_top_comments(access_token, video_id)
        except Exception:
            pass  # comments may be disabled on the video, that is fine
        return self.record_performance(performance, comments)
