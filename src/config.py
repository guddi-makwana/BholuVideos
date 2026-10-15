import os
import re
from pathlib import Path
from typing import List
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"
USED_TOPICS_FILE = BASE_DIR / "used_topics.json"

BGM_PATH = ASSETS_DIR / "bgm.mp3"
BHOLU_IMAGE_PATH = ASSETS_DIR / "bholu.jpg"
FINAL_VIDEO_PATH = OUTPUT_DIR / "final_short.mp4"

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
BGM_VOLUME = 0.12

TTS_VOICE = "en-US-ChristopherNeural"
TTS_RATE = "+5%"

CARTOON_STYLE_PREFIX = (
    "2D western animated cartoon style, bold black ink outlines, "
    "vibrant flat cel-shaded colors, expressive character design, "
    "dramatic lighting, vertical 9:16 composition, no text, no watermarks: "
)

BHOLU_CHARACTER_PROMPT = (
    "Featuring BHOLU (an adorable fluffy bubblegum-pink teddy bear character with round ears "
    "that have red inner ear pads with white polka dots, a white muzzle with a cute pink oval nose "
    "and warm smile, expressive black button eyes, and a bright red bow tie with white hearts) "
)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"

YOUTUBE_TOKEN_URI = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]


def ensure_directories() -> None:
    """Ensure required working directories exist."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    if not USED_TOPICS_FILE.exists():
        USED_TOPICS_FILE.write_text("[]\n", encoding="utf-8")


def get_gemini_api_keys() -> List[str]:
    """Return a list of configured Gemini API keys (supports single key or comma/whitespace-separated list)."""
    raw = os.getenv("GEMINI_API_KEY", "").strip()
    if not raw:
        return []
    keys = [k.strip() for k in re.split(r"[,\s]+", raw) if k.strip()]
    return keys


def get_youtube_credentials_config() -> dict:
    """Return YouTube OAuth2 credential values from environment variables."""
    return {
        "client_id": os.getenv("YOUTUBE_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET", "").strip(),
        "refresh_token": os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip(),
    }


def validate_environment(dry_run: bool = False, mock_llm: bool = False) -> None:
    """Validate required environment variables for the selected run mode."""
    missing = []
    if not mock_llm and not get_gemini_api_keys():
        missing.append("GEMINI_API_KEY")

    if not dry_run:
        yt_creds = get_youtube_credentials_config()
        if not yt_creds["client_id"]:
            missing.append("YOUTUBE_CLIENT_ID")
        if not yt_creds["client_secret"]:
            missing.append("YOUTUBE_CLIENT_SECRET")
        if not yt_creds["refresh_token"]:
            missing.append("YOUTUBE_REFRESH_TOKEN")

    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Set them in your environment or .env file, or run with --dry-run / --mock-llm."
        )
