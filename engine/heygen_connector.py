"""
HEYGEN CONNECTOR
Handles creating and using a digital twin avatar of the real user, and
generating new videos of "them" delivering an AI-written script, without
ever filming new footage.

Flow:
  1. ONE-TIME: user uploads a short clip of themselves speaking clearly.
     We send it to HeyGen to train a Digital Twin (their reusable likeness).
  2. ONGOING: the content engine writes a script. We send that script +
     the saved Digital Twin ID to HeyGen, which renders a brand new video
     of the user's likeness delivering it. HeyGen generation is async, so
     we start the job then poll until it's ready.

This mirrors youtube_connector.py in shape: self-contained, so the rest of
the app never needs to know HeyGen's specific API details.
"""

import os
import time
import requests

HEYGEN_BASE = "https://api.heygen.com"
CREATE_DIGITAL_TWIN_URL = f"{HEYGEN_BASE}/v2/photo_avatar/avatar_group/create"  # avatar/twin creation
UPLOAD_ASSET_URL = f"{HEYGEN_BASE}/v1/asset"
GENERATE_VIDEO_URL = f"{HEYGEN_BASE}/v3/videos"
VIDEO_STATUS_URL = f"{HEYGEN_BASE}/v1/video_status.get"


class HeyGenNotConfigured(Exception):
    """Raised when Joy's own HeyGen API key has not been set up yet."""
    pass


def _api_key():
    return os.environ.get("HEYGEN_API_KEY")


def is_configured():
    """True once Joy has a HeyGen account and API key set as an environment
    variable. Everything checks this first to show a friendly message
    instead of crashing when it's not set up yet."""
    return bool(_api_key())


def _headers():
    return {
        "x-api-key": _api_key(),
        "Content-Type": "application/json",
    }


def upload_training_clip(file_path):
    """Uploads the user's short training video/photo to HeyGen so it can be
    used to build their Digital Twin. Returns an asset id/key HeyGen gives
    back, which is then passed into create_digital_twin()."""
    if not is_configured():
        raise HeyGenNotConfigured("HEYGEN_API_KEY is not set yet.")

    with open(file_path, "rb") as f:
        resp = requests.post(
            UPLOAD_ASSET_URL,
            headers={"x-api-key": _api_key()},
            files={"file": f},
            timeout=120,  # training clips can be sizeable, give this room
        )
    resp.raise_for_status()
    data = resp.json()
    # HeyGen returns the uploaded asset's identifying key/url here
    return data.get("data", data)


def create_digital_twin(asset_reference, twin_name="Persona Digital Twin"):
    """Kicks off training of the reusable digital twin from the uploaded
    clip. This only needs to happen ONCE per person; after this, the same
    twin_id is reused for every future generated video."""
    if not is_configured():
        raise HeyGenNotConfigured("HEYGEN_API_KEY is not set yet.")

    payload = {
        "name": twin_name,
        "asset": asset_reference,
    }
    resp = requests.post(CREATE_DIGITAL_TWIN_URL, headers=_headers(), json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("data", data)
    return result.get("id") or result.get("group_id")


def generate_avatar_video(twin_id, script, voice_id=None, title="Persona Manager Video"):
    """Starts generating a brand NEW video of the user's digital twin
    delivering the given script. This is async on HeyGen's side, so this
    function only STARTS the job and returns a video_id to poll."""
    if not is_configured():
        raise HeyGenNotConfigured("HEYGEN_API_KEY is not set yet.")

    payload = {
        "type": "avatar",
        "video_title": title,
        "digital_twin_id": twin_id,
        "script": script,
    }
    if voice_id:
        payload["voice_id"] = voice_id

    resp = requests.post(GENERATE_VIDEO_URL, headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("data", data)
    return result.get("video_id")


def check_video_status(video_id):
    """Polls HeyGen for whether the generated video is ready. Returns a
    dict with at least a 'status' key: 'processing', 'completed', or
    'failed', and a 'video_url' once completed."""
    if not is_configured():
        raise HeyGenNotConfigured("HEYGEN_API_KEY is not set yet.")

    resp = requests.get(
        VIDEO_STATUS_URL,
        headers={"x-api-key": _api_key()},
        params={"video_id": video_id},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    result = data.get("data", data)
    return {
        "status": result.get("status", "unknown"),
        "video_url": result.get("video_url"),
        "thumbnail_url": result.get("thumbnail_url"),
    }


def wait_for_video(video_id, timeout_seconds=180, poll_interval=5):
    """Convenience wrapper: polls until the video is done or the timeout is
    hit. HeyGen renders typically take well under this, but this guards
    against hanging forever on a stuck job."""
    waited = 0
    while waited < timeout_seconds:
        result = check_video_status(video_id)
        if result["status"] == "completed":
            return result
        if result["status"] == "failed":
            raise RuntimeError("HeyGen video generation failed.")
        time.sleep(poll_interval)
        waited += poll_interval
    raise TimeoutError("Timed out waiting for HeyGen video to finish rendering.")
