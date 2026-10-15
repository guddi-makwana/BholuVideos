import logging
import math
import secrets
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from src.config import (
    BGM_PATH,
    BGM_VOLUME,
    BHOLU_IMAGE_PATH,
    FINAL_VIDEO_PATH,
    OUTPUT_DIR,
    TEMP_DIR,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)

logger = logging.getLogger(__name__)


def ensure_bgm_exists(bgm_path: Path = BGM_PATH) -> Path:
    """
    Ensure `assets/bgm.mp3` exists. If missing, synthesize a loopable royalty-free
    cinematic ambient background track using FFmpeg lavfi so the repo works out-of-the-box.
    """
    bgm_path.parent.mkdir(parents=True, exist_ok=True)
    if bgm_path.exists() and bgm_path.stat().st_size > 10_000:
        return bgm_path

    logger.info("Generating royalty-free ambient cinematic track at %s...", bgm_path)
    lavfi_expr = (
        "aevalsrc='"
        "0.22*sin(2*PI*110*t)*(0.85+0.15*sin(2*PI*0.18*t))"
        "+0.16*sin(2*PI*164.81*t)*(0.85+0.15*cos(2*PI*0.12*t))"
        "+0.12*sin(2*PI*220*t)*(0.80+0.20*sin(2*PI*0.09*t))"
        "+0.08*sin(2*PI*130.81*t)*(0.85+0.15*sin(2*PI*0.15*t))"
        "+0.04*sin(2*PI*329.63*t)*(0.70+0.30*cos(2*PI*0.07*t))"
        "':s=44100:d=65,"
        "lowpass=f=900,afade=t=in:st=0:d=2,afade=t=out:st=63:d=2"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        lavfi_expr,
        "-c:a",
        "libmp3lame",
        "-b:a",
        "128k",
        str(bgm_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return bgm_path


def _build_zoompan_filter(
    scene_index: int,
    duration: float,
    motion_mode: int | None = None,
) -> str:
    """
    Build a continuous 3-axis (Zoom + Pan-X + Pan-Y) 2.5D Ken Burns filter expression
    with randomized micro-trajectories and living atmospheric lighting so that no two frames
    or seconds in any video ever look static or identical.
    """
    rng = secrets.SystemRandom()
    total_frames = max(int(math.ceil(duration * VIDEO_FPS)), 15)
    denom = max(total_frames - 1, 1)
    mode = motion_mode if motion_mode is not None else (scene_index - 1) % 8

    # Randomized per-scene zoom span (between 0.13 and 0.18) and subtle orbital sway
    z_span = round(rng.uniform(0.13, 0.18), 4)
    z_base = round(rng.uniform(1.01, 1.04), 4)
    z_high = round(z_base + z_span, 4)
    sway_freq = round(rng.uniform(1.2, 2.4), 3)
    sway_amp_x = rng.randint(14, 28)
    sway_amp_y = rng.randint(18, 34)

    prog = f"(on/{denom})"

    if mode == 0:
        # 1. Slow push-in (z_base -> z_high) + diagonal drift top-left to center-right
        z_expr = f"{z_base}+{z_span}*{prog}"
        x_expr = f"(iw-iw/zoom)*(0.20+0.55*{prog})+{sway_amp_x}*sin(2*PI*{prog}*{sway_freq})"
        y_expr = f"(ih-ih/zoom)*(0.25+0.45*{prog})+{sway_amp_y}*cos(2*PI*{prog}*{sway_freq})"
    elif mode == 1:
        # 2. Slow pull-out (z_high -> z_base) + upward reveal pan bottom-right to upper-left
        z_expr = f"{z_high}-{z_span}*{prog}"
        x_expr = f"(iw-iw/zoom)*(0.75-0.50*{prog})+{sway_amp_x}*cos(2*PI*{prog}*{sway_freq})"
        y_expr = f"(ih-ih/zoom)*(0.80-0.55*{prog})+{sway_amp_y}*sin(2*PI*{prog}*{sway_freq})"
    elif mode == 2:
        # 3. Sweeping left-to-right tracking pan + continuous zoom-in
        z_expr = f"1.08+0.10*{prog}"
        x_expr = f"(iw-iw/zoom)*{prog}"
        y_expr = f"(ih-ih/zoom)*(0.35+0.30*sin(PI*{prog}))"
    elif mode == 3:
        # 4. Sweeping bottom-to-top vertical crane rise + gentle zoom-out
        z_expr = f"1.18-0.10*{prog}"
        x_expr = f"(iw-iw/zoom)*(0.50+0.30*cos(PI*{prog}))"
        y_expr = f"(ih-ih/zoom)*(1.0-{prog})"
    elif mode == 4:
        # 5. Dramatic zoom-in toward upper-third character focal point + right-to-left pan
        z_expr = f"{z_base}+{z_span}*{prog}"
        x_expr = f"(iw-iw/zoom)*(0.85-0.65*{prog})"
        y_expr = f"(ih-ih/zoom)*(0.65-0.45*{prog})+{sway_amp_y}*sin(PI*{prog})"
    elif mode == 5:
        # 6. Top-to-bottom dramatic tilt down + pull-back reveal
        z_expr = f"{z_high}-{z_span}*{prog}"
        x_expr = f"(iw-iw/zoom)*(0.25+0.50*{prog})"
        y_expr = f"(ih-ih/zoom)*{prog}"
    elif mode == 6:
        # 7. Diagonal bottom-left to top-right heroic push-in
        z_expr = f"1.03+{z_span}*{prog}"
        x_expr = f"(iw-iw/zoom)*(0.15+0.70*{prog})"
        y_expr = f"(ih-ih/zoom)*(0.85-0.70*{prog})"
    else:
        # 8. Smooth orbital arc + breathing zoom curve
        z_expr = f"1.06+0.12*sin(PI*{prog}/2)"
        x_expr = f"(iw-iw/zoom)*(0.50+0.38*sin(2*PI*{prog}))"
        y_expr = f"(ih-ih/zoom)*(0.50+0.38*cos(2*PI*{prog}))"

    # Subtle per-scene color vibrance & contrast signature + animated frame-by-frame vignette
    sat = round(rng.uniform(1.04, 1.14), 3)
    contrast = round(rng.uniform(1.02, 1.07), 3)
    vig_speed = round(rng.uniform(1.8, 3.2), 2)

    return (
        f"scale=2160:3840:force_original_aspect_ratio=increase,"
        f"crop=2160:3840,"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS},"
        f"eq=saturation={sat}:contrast={contrast},"
        f"vignette=angle='PI/6+0.035*sin(2*PI*t/{vig_speed})':eval=frame,"
        f"fade=t=in:st=0:d=0.18,"
        f"setsar=1,format=yuv420p"
    )


def _escape_ffmpeg_subtitle_path(path: Path) -> str:
    """Escape a filesystem path for FFmpeg's `subtitles=filename` filter on Windows & Linux."""
    posix_str = path.resolve().as_posix()
    escaped = posix_str.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return escaped


def render_scene_clip(scene: Dict[str, Any], motion_mode: int | None = None) -> Path:
    """Render a single scene image + voiceover MP3 into a 2.5D animated segment MP4."""
    idx = scene["index"]
    image_path: Path = scene["image_path"]
    audio_path: Path = scene["audio_path"]
    duration: float = scene["duration"]

    segment_path = TEMP_DIR / f"segment_{idx}.mp4"
    vf_filter = _build_zoompan_filter(
        scene_index=idx,
        duration=duration,
        motion_mode=motion_mode,
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(image_path),
        "-i",
        str(audio_path),
        "-vf",
        vf_filter,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-t",
        f"{duration:.3f}",
        str(segment_path),
    ]
    logger.info(
        "Rendering 2.5D Ken Burns segment %d (%.2fs @ %dfps, motion_mode=%s)...",
        idx,
        duration,
        VIDEO_FPS,
        motion_mode,
    )
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed while rendering segment {idx}:\n{proc.stderr[-1500:]}"
        )
    return segment_path


def render_final_video(
    media_bundle: Dict[str, Any],
    output_path: Path = FINAL_VIDEO_PATH,
) -> Path:
    """
    Full FFmpeg video rendering pipeline:
      1. Shuffle 8 distinct 3-axis camera motion modes so no two scenes share the same camera movement.
      2. Render each scene into a 2.5D Ken Burns segment matching its exact audio duration.
      3. Concatenate all scene video/audio segments.
      4. Burn in synchronized kinetic subtitles (MarginV=350, FontSize=18, Alignment=2, bold white + thick black outline)
         and mix `assets/bgm.mp3` (from a randomized start offset) at 12% volume (`volume=0.12`, `amix=inputs=2:duration=first`).
      5. Save final video to `output/final_short.mp4`.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    ensure_bgm_exists(BGM_PATH)

    scenes: List[Dict[str, Any]] = media_bundle["scenes"]
    subtitles_path: Path = media_bundle["subtitles_path"]

    rng = secrets.SystemRandom()
    motion_modes = rng.sample(range(8), k=min(len(scenes), 8))
    while len(motion_modes) < len(scenes):
        motion_modes.append(rng.randrange(8))

    segment_paths: List[Path] = []
    for scene, m_mode in zip(scenes, motion_modes):
        segment_paths.append(render_scene_clip(scene, motion_mode=m_mode))

    concat_list_path = TEMP_DIR / "concat_list.txt"
    concat_lines = [
        f"file '{seg.resolve().as_posix()}'" for seg in segment_paths
    ]
    concat_list_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

    concatenated_path = TEMP_DIR / "concatenated.mp4"
    concat_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c",
        "copy",
        str(concatenated_path),
    ]
    logger.info("Concatenating %d scene segments...", len(segment_paths))
    concat_proc = subprocess.run(
        concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if concat_proc.returncode != 0:
        raise RuntimeError(
            f"FFmpeg concat failed:\n{concat_proc.stderr[-1500:]}"
        )

    escaped_subs = _escape_ffmpeg_subtitle_path(subtitles_path)
    force_style = (
        "FontName=Liberation Sans,"
        "FontSize=18,"
        "Bold=1,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BackColour=&H80000000,"
        "BorderStyle=1,"
        "Outline=3,"
        "Shadow=1,"
        "Alignment=2,"
        "MarginV=350"
    )

    bgm_offset = round(rng.uniform(0.0, 20.0), 2)
    af_mix = (
        f"[0:a]volume=1.0[vo];"
        f"[1:a]volume={BGM_VOLUME}[bgm];"
        f"[vo][bgm]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
    )

    if BHOLU_IMAGE_PATH.exists():
        # Overlay the user-provided BHOLU character image as an animated floating cameo badge in the top-right corner
        bholu_filter = (
            f"[2:v]scale=210:260:force_original_aspect_ratio=increase,"
            f"crop=210:260,"
            f"drawbox=x=0:y=0:w=210:h=260:color=white:t=8,"
            f"drawbox=x=0:y=0:w=210:h=260:color=#ff3366:t=3,"
            f"format=yuv420p[bholu];"
            f"[0:v][bholu]overlay=x='W-w-36+6*cos(2*PI*t/2.8)':y='52+10*sin(2*PI*t/2.1)':shortest=1[v_with_bholu];"
            f"[v_with_bholu]subtitles='{escaped_subs}':force_style='{force_style}',"
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:out_range=tv,format=yuv420p[vout]"
        )
        final_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(concatenated_path),
            "-stream_loop",
            "-1",
            "-ss",
            str(bgm_offset),
            "-i",
            str(BGM_PATH),
            "-loop",
            "1",
            "-i",
            str(BHOLU_IMAGE_PATH),
            "-filter_complex",
            f"{bholu_filter};{af_mix}",
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(VIDEO_FPS),
            "-s",
            f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    else:
        vf_subtitles = (
            f"subtitles='{escaped_subs}':force_style='{force_style}',"
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:out_range=tv,format=yuv420p"
        )
        final_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(concatenated_path),
            "-stream_loop",
            "-1",
            "-ss",
            str(bgm_offset),
            "-i",
            str(BGM_PATH),
            "-filter_complex",
            f"[0:v]{vf_subtitles}[vout];{af_mix}",
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(VIDEO_FPS),
            "-s",
            f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    logger.info("Burning kinetic subtitles and mixing BGM into %s...", output_path)
    final_proc = subprocess.run(
        final_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if final_proc.returncode != 0:
        raise RuntimeError(
            f"FFmpeg final render failed:\n{final_proc.stderr[-1500:]}"
        )

    logger.info("Final short rendered successfully: %s", output_path)
    return output_path
