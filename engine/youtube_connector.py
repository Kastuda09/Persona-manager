"""
YOUTUBE CONNECTOR
Handles connecting a user's YouTube channel via Google login (OAuth), and
publishing an approved draft as a real video upload to that channel.

This is intentionally self-contained: everything else in the app (the
approval queue, the drafts, the manager) does not need to know HOW YouTube
works, it just calls connect_url(), exchange_code(), and publish_video().
"""

import os
import json
import requests

# --- Google OAuth endpoints (fixed, never change) ---
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_CHANNEL_URL = "https://www.googleapis.com/youtube/v3/channels"

# The permissions we ask the user to grant. youtube.upload lets us publish
# videos on their behalf. youtube.readonly lets us pull their channel stats
# and video performance later for the feedback-loop layer.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


class YouTubeNotConfigured(Exception):
    """Raised when the app's own Google API credentials are not set yet."""
    pass


def _client_id():
    return os.environ.get("GOOGLE_CLIENT_ID")


def _client_secret():
    return os.environ.get("GOOGLE_CLIENT_SECRET")


def is_configured():
    """True once Joy has created a Google Cloud project and set the two
    environment variables. Everything else in the app checks this first so
    it can show a friendly 'not connected yet' message instead of crashing."""
    return bool(_client_id() and _client_secret())


def connect_url(redirect_uri):
    """Builds the URL to send the user to, so they can log in with Google
    and grant permission. This is what the 'Connect YouTube' button links to."""
    if not is_configured():
        raise YouTubeNotConfigured(
            "Google API credentials are not set up yet (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)."
        )
    params = {
        "client_id": _client_id(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",   # needed to get a refresh_token, so we
                                     # can post later without asking them to
                                     # log in again every time
        "prompt": "consent",
    }
    query = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URL}?{query}"


def exchange_code(code, redirect_uri):
    """After Google redirects back to us with a one-time code, trade it for
    real access_token + refresh_token we can store and reuse."""
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        "code": code,
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()  # contains access_token, refresh_token, expires_in


def refresh_access_token(refresh_token):
    """Access tokens expire in about an hour. Use the long-lived refresh
    token to get a fresh one, silently, no user interaction needed."""
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()  # contains a new access_token


def get_channel_info(access_token):
    """Pulls the connected channel's basic info, so we can show 'Connected
    as: <channel name>' rather than just a blank confirmation."""
    resp = requests.get(YOUTUBE_CHANNEL_URL, params={
        "part": "snippet,statistics",
        "mine": "true",
    }, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items", [])
    if not items:
        return None
    channel = items[0]
    return {
        "channel_id": channel["id"],
        "title": channel["snippet"]["title"],
        "subscriber_count": channel.get("statistics", {}).get("subscriberCount"),
        "view_count": channel.get("statistics", {}).get("viewCount"),
    }


def publish_video(access_token, video_path, title, description, tags=None, privacy_status="public"):
    """Uploads a real video file to the connected YouTube channel.
    video_path must point to an actual video file already saved on disk
    (e.g. the file the user uploaded in Create Post).
    Returns the new YouTube video ID on success."""
    metadata = {
        "snippet": {
            "title": title[:100],  # YouTube's own title length limit
            "description": description[:5000],
            "tags": tags or [],
            "categoryId": "22",  # "People & Blogs", a safe general default
        },
        "status": {
            "privacyStatus": privacy_status,  # "public", "unlisted", or "private"
            "selfDeclaredMadeForKids": False,
        },
    }

    with open(video_path, "rb") as video_file:
        files = {
            "data": ("metadata.json", json.dumps(metadata), "application/json"),
            "video": ("video.mp4", video_file, "video/*"),
        }
        resp = requests.post(
            YOUTUBE_UPLOAD_URL,
            params={"part": "snippet,status", "uploadType": "multipart"},
            headers={"Authorization": f"Bearer {access_token}"},
            files=files,
            timeout=120,  # video uploads are slow, give this one plenty of room
        )
    resp.raise_for_status()
    result = resp.json()
    return result.get("id")
