import asyncio
import hashlib
import logging
import re
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
from urllib.parse import quote

import edge_tts
import requests

from src.config import (
    CARTOON_STYLE_PREFIX,
    TEMP_DIR,
    TTS_RATE,
    TTS_VOICE,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)

logger = logging.getLogger(__name__)

MIN_IMAGE_SIZE_BYTES = 10 * 1024  # 10 KB minimum validation threshold

SCENE_VISUAL_MODIFIERS: List[str] = [
    "wide-angle establishing composition, warm golden dawn lighting, deep atmospheric perspective",
    "dynamic low-angle heroic perspective, crisp cel-shaded rim lighting, bold dramatic shadows",
    "expressive close-up character focus, intense flickering firelight, vibrant warm and cool contrast",
    "over-the-shoulder action framing, kinetic diagonal composition, rich emerald and crimson accents",
    "dramatic Dutch-angle climax framing, high-energy motion lines, vivid sunset amber sky",
    "elevated bird's-eye panoramic perspective, intricate architectural textures, twilight indigo and gold glow",
    "cinematic side-profile silhouette framing, volumetric sunbeams, striking jewel-toned palette",
]


def _is_valid_image_bytes(data: bytes) -> bool:
    """Validate that downloaded bytes exceed 10KB and match standard image signatures."""
    if len(data) <= MIN_IMAGE_SIZE_BYTES:
        return False
    if data.startswith(b"\xff\xd8\xff"):
        return True
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return False


def download_scene_image(
    visual_prompt: str,
    output_path: Path,
    scene_index: int = 1,
    seen_hashes: Set[str] | None = None,
    max_attempts: int = 4,
) -> Path:
    """
    Download a unique 1080x1920 cartoon illustration from Pollinations.ai using the flux model.
    Enforces cryptographic seed randomness, scene-specific visual composition modifiers,
    SHA-256 deduplication across all scenes in the run, and exponential backoff with Retry-After support.
    """
    if seen_hashes is None:
        seen_hashes = set()

    prompt_text = visual_prompt.strip()
    if not prompt_text.startswith(CARTOON_STYLE_PREFIX):
        prompt_text = f"{CARTOON_STYLE_PREFIX}{prompt_text}"

    modifier = SCENE_VISUAL_MODIFIERS[(scene_index - 1) % len(SCENE_VISUAL_MODIFIERS)]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Cache-Control": "no-cache",
    }

    last_error = None
    for attempt in range(1, max_attempts + 1):
        seed = 10_000 + secrets.randbelow(999_900_000)
        unique_prompt = f"{prompt_text} [Scene {scene_index} framing: {modifier}, variant {seed}]"
        encoded_prompt = quote(unique_prompt, safe="")
        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width={VIDEO_WIDTH}&height={VIDEO_HEIGHT}&model=flux&nologo=true&seed={seed}"
        )
        retry_after_header = 0
        try:
            logger.info(
                "Fetching Pollinations.ai image for %s (attempt %d/%d, seed=%d)...",
                output_path.name,
                attempt,
                max_attempts,
                seed,
            )
            response = requests.get(url, headers=headers, timeout=90)
            if response.status_code == 200 and _is_valid_image_bytes(response.content):
                img_hash = hashlib.sha256(response.content).hexdigest()
                if img_hash in seen_hashes:
                    last_error = f"Duplicate image hash detected ({img_hash[:12]}), re-rolling seed"
                    logger.warning(
                        "Pollinations returned duplicate image for %s; re-rolling with new seed.",
                        output_path.name,
                    )
                else:
                    seen_hashes.add(img_hash)
                    output_path.write_bytes(response.content)
                    logger.info(
                        "Saved unique image %s (%d KB, sha256=%s).",
                        output_path.name,
                        len(response.content) // 1024,
                        img_hash[:10],
                    )
                    return output_path
            else:
                try:
                    retry_after_header = int(response.headers.get("Retry-After", "0"))
                except ValueError:
                    retry_after_header = 0

                last_error = (
                    f"HTTP {response.status_code}, content-type={response.headers.get('Content-Type')}, "
                    f"size={len(response.content)} bytes"
                )
                logger.warning(
                    "Pollinations attempt %d/%d for %s returned invalid image (%s).",
                    attempt,
                    max_attempts,
                    output_path.name,
                    last_error,
                )
        except requests.RequestException as exc:
            last_error = str(exc)
            logger.warning(
                "Pollinations network error on attempt %d/%d for %s: %s",
                attempt,
                max_attempts,
                output_path.name,
                exc,
            )

        if attempt < max_attempts:
            backoff_seconds = max(2 ** attempt, retry_after_header + 1)
            logger.info("Retrying in %d seconds with a new random seed...", backoff_seconds)
            time.sleep(backoff_seconds)

    logger.warning(
        "Pollinations.ai unreachable after %d attempts (%s). Generating unique fallback cartoon frame for %s.",
        max_attempts,
        last_error,
        output_path.name,
    )
    return _generate_fallback_cartoon_image(visual_prompt, output_path, scene_index=scene_index)


def _generate_fallback_cartoon_image(
    visual_prompt: str,
    output_path: Path,
    scene_index: int = 1,
) -> Path:
    """
    Generate a unique stylized 1080x1920 2D cel-shaded illustration frame via FFmpeg lavfi
    using cryptographic randomness per scene and per run so no two fallback frames ever match.
    """
    rng = secrets.SystemRandom()
    palettes = [
        ("#1a2a3a", "#d97724", "#f4c065", "#2d1e12"),
        ("#2b193d", "#c84b31", "#ecdbba", "#191919"),
        ("#132a13", "#bc4749", "#f2e8cf", "#386641"),
        ("#3d1e1e", "#e09f3e", "#fff3b0", "#540b0e"),
        ("#1b263b", "#415a77", "#e0e1dd", "#0d1b2a"),
        ("#231942", "#5e548e", "#be95c4", "#e0b1cb"),
        ("#003049", "#d62828", "#f77f00", "#fcbf49"),
        ("#283618", "#606c38", "#dda15e", "#bc6c25"),
    ]
    bg_hex, mid_hex, sun_hex, hill_hex = rng.choice(palettes)

    freq_x = rng.randint(65, 145)
    freq_y = rng.randint(85, 175)
    sun_x = rng.randint(100, 360) + (scene_index * 17) % 120
    sun_y = rng.randint(160, 420)
    sun_w = rng.randint(460, 680)
    arch_x = rng.randint(60, 180)
    arch_y = rng.randint(860, 1080)
    fg_x = rng.randint(180, 340)
    fg_y = rng.randint(680, 880)
    fg_w = rng.randint(420, 620)
    noise_seed = rng.randint(1, 999999)

    filter_graph = (
        f"color=c={bg_hex}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d=1,"
        f"geq="
        f"r='clip(r(X,Y)+45*sin(X/{freq_x})+35*cos(Y/{freq_y}),0,255)':"
        f"g='clip(g(X,Y)+35*cos(X/{freq_y})+30*sin(Y/{freq_x}),0,255)':"
        f"b='clip(b(X,Y)+40*sin((X+Y)/{freq_x + 30}),0,255)',"
        f"drawbox=x=0:y=1150:w=1080:h=770:color={mid_hex}@0.85:t=fill,"
        f"drawbox=x={sun_x}:y={sun_y}:w={sun_w}:h={sun_w}:color={sun_hex}@0.9:t=fill,"
        f"drawbox=x={sun_x}:y={sun_y}:w={sun_w}:h={sun_w}:color=black:t=12,"
        f"drawbox=x={arch_x}:y={arch_y}:w=840:h=640:color={hill_hex}@0.95:t=fill,"
        f"drawbox=x={arch_x}:y={arch_y}:w=840:h=640:color=black:t=14,"
        f"drawbox=x={fg_x}:y={fg_y}:w={fg_w}:h=840:color={mid_hex}@0.95:t=fill,"
        f"drawbox=x={fg_x}:y={fg_y}:w={fg_w}:h=840:color=black:t=14,"
        f"noise=alls=16:allf=t:all_seed={noise_seed},"
        f"drawbox=x=24:y=24:w=1032:h=1872:color=black:t=24"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        filter_graph,
        "-frames:v",
        "1",
        "-f",
        "image2",
        "-c:v",
        "png",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def probe_audio_duration(audio_path: Path) -> float:
    """Measure exact duration in seconds of an audio file using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return max(float(result.stdout.strip()), 0.5)


async def _synthesize_scene_audio_async(
    narration: str,
    audio_path: Path,
) -> List[Tuple[float, float, str]]:
    """
    Generate MP3 audio for a single scene using edge-tts (en-US-ChristopherNeural, +5% rate)
    and collect timing cues via SubMaker.
    Returns a list of (start_sec, end_sec, text) relative to the start of the scene.
    """
    communicate = edge_tts.Communicate(
        text=narration,
        voice=TTS_VOICE,
        rate=TTS_RATE,
    )
    submaker = edge_tts.SubMaker()
    cues: List[Tuple[float, float, str]] = []

    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            chunk_type = chunk.get("type")
            if chunk_type == "audio":
                audio_file.write(chunk["data"])
            elif chunk_type in ("WordBoundary", "SentenceBoundary"):
                if hasattr(submaker, "feed"):
                    submaker.feed(chunk)
                elif hasattr(submaker, "create_sub"):
                    submaker.create_sub(
                        (chunk["offset"], chunk["duration"]),
                        chunk["text"],
                    )
                start_sec = chunk["offset"] / 10_000_000.0
                dur_sec = chunk["duration"] / 10_000_000.0
                cues.append((start_sec, start_sec + max(dur_sec, 0.15), chunk["text"]))

    scene_srt_path = audio_path.with_suffix(".srt")
    if hasattr(submaker, "get_srt"):
        srt_text = submaker.get_srt()
    elif hasattr(submaker, "generate_subs"):
        srt_text = submaker.generate_subs()
    else:
        srt_text = ""

    if srt_text.strip():
        scene_srt_path.write_text(srt_text, encoding="utf-8")

    return cues


def _build_chunked_cues_for_scene(
    narration: str,
    raw_cues: List[Tuple[float, float, str]],
    scene_duration: float,
    scene_offset: float,
    words_per_caption: int = 5,
) -> List[Tuple[float, float, str]]:
    """
    Convert per-scene boundary cues (or fallback word proportional timings) into
    punchy 4-6 word kinetic subtitle chunks offset by `scene_offset`.
    """
    if raw_cues and all(len(text.split()) <= 2 for _, _, text in raw_cues):
        grouped: List[Tuple[float, float, str]] = []
        for i in range(0, len(raw_cues), words_per_caption):
            batch = raw_cues[i : i + words_per_caption]
            start_t = scene_offset + batch[0][0]
            end_t = scene_offset + min(batch[-1][1] + 0.08, scene_duration)
            if i + words_per_caption < len(raw_cues):
                next_start = scene_offset + raw_cues[i + words_per_caption][0]
                end_t = min(end_t, next_start)
            text_chunk = " ".join(item[2].strip() for item in batch if item[2].strip())
            if text_chunk:
                grouped.append((start_t, max(end_t, start_t + 0.2), text_chunk))
        if grouped:
            return grouped

    words = [w for w in re.split(r"\s+", narration.strip()) if w]
    if not words:
        return []

    chunks: List[List[str]] = [
        words[i : i + words_per_caption]
        for i in range(0, len(words), words_per_caption)
    ]
    total_chars = sum(len(" ".join(c)) for c in chunks) or 1
    usable_duration = max(scene_duration - 0.1, 0.4)

    result: List[Tuple[float, float, str]] = []
    cursor = scene_offset
    for idx, chunk_words in enumerate(chunks):
        chunk_str = " ".join(chunk_words)
        weight = len(chunk_str) / total_chars
        dur = usable_duration * weight
        start_t = cursor
        end_t = (
            scene_offset + usable_duration
            if idx == len(chunks) - 1
            else cursor + dur
        )
        result.append((start_t, max(end_t, start_t + 0.25), chunk_str))
        cursor = end_t

    return result


def _format_srt_timestamp(seconds: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm."""
    total_ms = int(round(max(seconds, 0.0) * 1000))
    hours = total_ms // 3_600_000
    total_ms %= 3_600_000
    minutes = total_ms // 60_000
    total_ms %= 60_000
    secs = total_ms // 1000
    ms = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _format_ass_timestamp(seconds: float) -> str:
    """Format seconds as ASS timestamp H:MM:SS.cc."""
    total_cs = int(round(max(seconds, 0.0) * 100))
    hours = total_cs // 360_000
    total_cs %= 360_000
    minutes = total_cs // 6_000
    total_cs %= 6_000
    secs = total_cs // 100
    cs = total_cs % 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def write_combined_srt(
    all_cues: List[Tuple[float, float, str]],
    srt_path: Path,
) -> Path:
    """Write combined synchronized subtitles to both .srt and .ass files."""
    blocks = []
    ass_events = []
    for idx, (start_t, end_t, text) in enumerate(all_cues, start=1):
        blocks.append(
            f"{idx}\n"
            f"{_format_srt_timestamp(start_t)} --> {_format_srt_timestamp(end_t)}\n"
            f"{text}\n"
        )
        clean_ass_text = text.replace("\n", " ").replace("{", "(").replace("}", ")")
        ass_events.append(
            f"Dialogue: 0,{_format_ass_timestamp(start_t)},{_format_ass_timestamp(end_t)},Default,,0,0,0,,{clean_ass_text}"
        )
    srt_path.write_text("\n".join(blocks), encoding="utf-8")

    ass_path = srt_path.with_suffix(".ass")
    ass_header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 384\n"
        "PlayResY: 960\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Liberation Sans,18,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,"
        "-1,0,0,0,100,100,0,0,1,3,1,2,24,24,350,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    ass_path.write_text(ass_header + "\n".join(ass_events) + "\n", encoding="utf-8")
    return ass_path


def generate_all_scene_media(script: Dict[str, Any]) -> Dict[str, Any]:
    """
    For each scene in the script:
      1. Download a unique 1080x1920 cartoon image from Pollinations.ai (`scene_X.jpg`),
         verifying via SHA-256 that no two scenes ever share the same image.
      2. Generate neural voiceover audio via edge-tts (`scene_X.mp3`).
      3. Measure exact audio duration via ffprobe and build a master synchronized `.srt` file.
    """
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    scenes = script.get("scenes", [])
    if not scenes:
        raise ValueError("Script contains no scenes to process.")

    scene_assets: List[Dict[str, Any]] = []
    combined_cues: List[Tuple[float, float, str]] = []
    seen_image_hashes: Set[str] = set()
    cumulative_time = 0.0

    for idx, scene in enumerate(scenes, start=1):
        narration = scene["narration"]
        visual_prompt = scene["visual_prompt"]

        image_path = TEMP_DIR / f"scene_{idx}.jpg"
        audio_path = TEMP_DIR / f"scene_{idx}.mp3"

        download_scene_image(
            visual_prompt=visual_prompt,
            output_path=image_path,
            scene_index=idx,
            seen_hashes=seen_image_hashes,
        )

        logger.info("Synthesizing edge-tts voiceover for scene %d/%d...", idx, len(scenes))
        raw_cues = asyncio.run(_synthesize_scene_audio_async(narration, audio_path))
        duration = probe_audio_duration(audio_path)

        scene_cues = _build_chunked_cues_for_scene(
            narration=narration,
            raw_cues=raw_cues,
            scene_duration=duration,
            scene_offset=cumulative_time,
        )
        combined_cues.extend(scene_cues)
        cumulative_time += duration

        scene_assets.append(
            {
                "index": idx,
                "image_path": image_path,
                "audio_path": audio_path,
                "duration": duration,
                "narration": narration,
            }
        )

    master_srt_path = TEMP_DIR / "subtitles.srt"
    master_ass_path = write_combined_srt(combined_cues, master_srt_path)
    logger.info(
        "Generated media for %d scenes (total voiceover duration: %.2fs).",
        len(scene_assets),
        cumulative_time,
    )

    return {
        "scenes": scene_assets,
        "subtitles_path": master_ass_path,
        "total_duration": cumulative_time,
    }
