import argparse
import logging
import shutil
import sys

from src.config import (
    FINAL_VIDEO_PATH,
    TEMP_DIR,
    ensure_directories,
    get_gemini_api_keys,
    validate_environment,
)
from src.media_generator import generate_all_scene_media
from src.publishers import publish_to_instagram, publish_to_youtube
from src.script_generator import generate_history_script, record_used_topic
from src.video_renderer import render_final_video

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Zero-Touch Automated Ancient History Cartoon Bot (YouTube Shorts)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate the full MP4 locally without uploading to YouTube.",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use the built-in 5-scene Ancient Rome script instead of calling Gemini API.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep intermediate scene files in temp/ after rendering.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_directories()

    use_mock_llm = args.mock_llm
    if not use_mock_llm and args.dry_run and not get_gemini_api_keys():
        logger.warning(
            "GEMINI_API_KEY not found in environment during --dry-run; "
            "automatically falling back to --mock-llm sample script."
        )
        use_mock_llm = True

    validate_environment(dry_run=args.dry_run, mock_llm=use_mock_llm)

    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    try:
        script = generate_history_script(mock_llm=use_mock_llm)
    except Exception as exc:
        if args.dry_run and not use_mock_llm:
            logger.warning(
                "Gemini API call failed during --dry-run (%s); falling back to --mock-llm sample script.",
                exc,
            )
            script = generate_history_script(mock_llm=True)
        else:
            raise

    topic = script["topic"]
    youtube_title = script["youtube_title"]
    youtube_description = script["youtube_description"]

    logger.info("Selected Topic: %s", topic)
    logger.info("YouTube Title: %s", youtube_title)
    logger.info("Scene Count: %d", len(script["scenes"]))

    media_bundle = generate_all_scene_media(script)
    final_video = render_final_video(media_bundle, output_path=FINAL_VIDEO_PATH)

    if args.dry_run:
        logger.info(
            "Dry run complete! Video rendered at: %s (skipping YouTube upload).",
            final_video,
        )
        publish_to_instagram(final_video, youtube_description)
        record_used_topic(topic)
    else:
        video_id = publish_to_youtube(
            video_path=final_video,
            title=youtube_title,
            description=youtube_description,
        )
        publish_to_instagram(final_video, youtube_description)
        if video_id:
            record_used_topic(topic)

    if not args.keep_temp and TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
