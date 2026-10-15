import logging
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from src.config import (
    YOUTUBE_TOKEN_URI,
    YOUTUBE_UPLOAD_SCOPE,
    get_youtube_credentials_config,
)

logger = logging.getLogger(__name__)


def publish_to_youtube(
    video_path: Path,
    title: str,
    description: str,
) -> str:
    """
    Authenticate headlessly via OAuth2 refresh token and upload `output/final_short.mp4`
    to YouTube Shorts using YouTube Data API v3.
    Returns the uploaded YouTube video ID.
    """
    creds_cfg = get_youtube_credentials_config()
    if not all([creds_cfg["client_id"], creds_cfg["client_secret"], creds_cfg["refresh_token"]]):
        raise EnvironmentError(
            "Missing YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, or YOUTUBE_REFRESH_TOKEN."
        )

    credentials = Credentials(
        token=None,
        refresh_token=creds_cfg["refresh_token"],
        token_uri=YOUTUBE_TOKEN_URI,
        client_id=creds_cfg["client_id"],
        client_secret=creds_cfg["client_secret"],
        scopes=YOUTUBE_UPLOAD_SCOPE,
    )
    credentials.refresh(Request())

    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "categoryId": "27",  # Education
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=1024 * 1024 * 4,
        resumable=True,
    )

    logger.info("Starting resumable upload to YouTube Shorts: '%s'...", title)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info("YouTube upload progress: %d%%", int(status.progress() * 100))

    video_id = response.get("id", "")
    logger.info("Successfully published to YouTube Shorts! Video ID: %s (https://youtube.com/shorts/%s)", video_id, video_id)
    return video_id


def publish_to_instagram(
    video_path: Path,
    caption: str,
) -> Optional[str]:
    """Non-blocking placeholder for future Instagram Reels publishing."""
    logger.info("Instagram publishing not configured yet — skipping")
    return None
