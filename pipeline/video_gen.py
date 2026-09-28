"""
Generates one short video clip per scene.

Real mode: calls Google's Veo model through the Gemini API (REST, long-running
operation) and downloads the resulting mp4.

Demo mode (no GEMINI_API_KEY, or the Veo call fails/quota-limited): renders a
simple animated placeholder clip locally with Pillow + ffmpeg (a colored card
with the character name and a Ken Burns zoom) so the whole pipeline still
produces a playable video end to end.
"""
import functools
import os
import subprocess
import time

import requests
from PIL import Image, ImageDraw, ImageFont

VEO_MODEL = "veo-3.1-generate-preview"
VEO_GENERATE_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{VEO_MODEL}:predictLongRunning"
)
VEO_POLL_URL = "https://generativelanguage.googleapis.com/v1beta/{op_name}"

POLL_INTERVAL_SECONDS = 8
POLL_TIMEOUT_SECONDS = 300

PALETTE = [
    (255, 122, 89), (76, 175, 154), (255, 195, 77),
    (100, 149, 237), (186, 104, 200), (255, 138, 182),
]


def generate_scene_clip(scene: dict, api_key: str | None, out_mp4_path: str,
                         target_seconds: float, log=print) -> str:
    """
    Produces out_mp4_path (roughly target_seconds long, will be trimmed/looped
    later to match the narration exactly). Returns 'veo' or 'demo' to record
    which path was used.
    """
    if api_key:
        try:
            _generate_with_veo(scene["visual_prompt"], api_key, out_mp4_path)
            return "veo"
        except Exception as exc:
            log(f"  [scene {scene['index']}] Veo generation failed ({exc}); using demo placeholder clip.")

    _generate_placeholder(scene, out_mp4_path, target_seconds)
    return "demo"


def _generate_with_veo(prompt: str, api_key: str, out_mp4_path: str):
    resp = requests.post(
        VEO_GENERATE_URL,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "instances": [{"prompt": prompt}],
            "parameters": {"aspectRatio": "16:9", "durationSeconds": "8"},
        },
        timeout=60,
    )
    resp.raise_for_status()
    op_name = resp.json()["name"]

    waited = 0
    while waited < POLL_TIMEOUT_SECONDS:
        time.sleep(POLL_INTERVAL_SECONDS)
        waited += POLL_INTERVAL_SECONDS
        poll = requests.get(
            VEO_POLL_URL.format(op_name=op_name),
            headers={"x-goog-api-key": api_key},
            timeout=30,
        )
        poll.raise_for_status()
        data = poll.json()
        if data.get("done"):
            if "error" in data:
                raise RuntimeError(data["error"])
            samples = data["response"]["generateVideoResponse"]["generatedSamples"]
            video_uri = samples[0]["video"]["uri"]
            video_resp = requests.get(
                video_uri, headers={"x-goog-api-key": api_key}, timeout=120, stream=True
            )
            video_resp.raise_for_status()
            with open(out_mp4_path, "wb") as f:
                for chunk in video_resp.iter_content(chunk_size=1 << 16):
                    f.write(chunk)
            return
    raise TimeoutError("Veo generation did not finish in time")


def _generate_placeholder(scene: dict, out_mp4_path: str, target_seconds: float):
    """Renders a colorful animated 'coming to life' placeholder card as the clip."""
    width, height = 1280, 720
    color = PALETTE[scene["index"] % len(PALETTE)]
    img = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(img)

    label = scene.get("narration_ta") or scene.get("narration_en") or scene.get("visual_prompt", "")
    label = (label[:140] + "...") if len(label) > 140 else label

    is_tamil = any("஀" <= ch <= "௿" for ch in label)
    font = _load_font(40, tamil=is_tamil)
    _draw_wrapped_text(draw, label, font, width, height)

    tmp_dir = os.path.dirname(out_mp4_path)
    still_path = os.path.join(tmp_dir, f"_still_{scene['index']}.png")
    img.save(still_path)

    duration = max(2.0, target_seconds)
    # Ken Burns style slow zoom on the still image
    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", still_path,
            "-t", str(duration),
            "-vf",
            (
                f"scale=1600:900,zoompan=z='min(zoom+0.0008,1.15)':"
                f"d={int(duration * 25)}:s={width}x{height}:fps=25"
            ),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", out_mp4_path,
        ],
        check=True, capture_output=True,
    )
    os.remove(still_path)


@functools.lru_cache(maxsize=8)
def _resolve_font_path(tamil: bool) -> str | None:
    """Ask fontconfig for a font that can render the needed script, falling
    back to a couple of common hardcoded paths if fontconfig isn't around."""
    candidates = []
    if tamil:
        candidates += [
            "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
        ]
    else:
        candidates += ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]

    for path in candidates:
        if os.path.exists(path):
            return path

    # Ask fontconfig for whatever font it would actually use for this script
    # (matches what ffmpeg's libass subtitle burn-in does).
    try:
        query = ":lang=ta:weight=bold" if tamil else ":weight=bold"
        result = subprocess.run(
            ["fc-match", "--format=%{file}", query],
            check=True, capture_output=True, text=True, timeout=5,
        )
        path = result.stdout.strip()
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    return None


def _load_font(size: int, tamil: bool = False):
    path = _resolve_font_path(tamil)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _draw_wrapped_text(draw, text, font, width, height):
    words = text.split()
    lines, current = [], ""
    for w in words:
        trial = f"{current} {w}".strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] > width - 160 and current:
            lines.append(current)
            current = w
        else:
            current = trial
    if current:
        lines.append(current)

    line_height = 56
    total_h = line_height * len(lines)
    y = (height - total_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_height
