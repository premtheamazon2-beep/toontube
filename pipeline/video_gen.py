"""
Generates one short video clip per scene.

Four tiers, tried in order (first one with the right key/availability wins):
1. Veo (needs a paid/billing-enabled GEMINI_API_KEY) — best quality real AI
   video motion.
2. Hugging Face Inference Providers text-to-video (needs a free HF_TOKEN —
   huggingface.co/settings/tokens, no credit card, free-tier credits) — a
   real (if rougher) AI-animated moving clip per scene.
3. Free AI illustration — calls Pollinations.ai's free, keyless text-to-image
   API to get an actual AI-drawn picture of the scene, then animates it with
   a Ken Burns pan/zoom in ffmpeg. No account, no key, no cost, but the
   "motion" is just a pan/zoom on a still picture.
4. Plain placeholder card — solid color + the scene text. Last-resort
   fallback if everything else is unreachable, so the pipeline always
   finishes with a playable video.
"""
import functools
import os
import subprocess
import time
import urllib.parse

import requests
from PIL import Image, ImageDraw, ImageFont

VEO_MODEL = "veo-3.1-generate-preview"
VEO_GENERATE_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{VEO_MODEL}:predictLongRunning"
)
VEO_POLL_URL = "https://generativelanguage.googleapis.com/v1beta/{op_name}"

POLL_INTERVAL_SECONDS = 8
POLL_TIMEOUT_SECONDS = 300

# Small, fast, free-tier-friendly text-to-video model on Hugging Face's
# Inference Providers router. Swap for a bigger model if you have more quota.
HF_T2V_MODEL = "Wan-AI/Wan2.1-T2V-1.3B"
HF_T2V_PROVIDER = "fal-ai"

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"

PALETTE = [
    (255, 122, 89), (76, 175, 154), (255, 195, 77),
    (100, 149, 237), (186, 104, 200), (255, 138, 182),
]


def generate_scene_clip(scene: dict, api_key: str | None, out_mp4_path: str,
                         target_seconds: float, log=print, hf_token: str | None = None) -> str:
    """
    Produces out_mp4_path (roughly target_seconds long, will be trimmed/looped
    later to match the narration exactly). Returns which tier was used:
    'veo', 'huggingface', 'free-ai-image', or 'placeholder'.
    """
    if api_key:
        try:
            _generate_with_veo(scene["visual_prompt"], api_key, out_mp4_path)
            return "veo"
        except Exception as exc:
            log(f"  [scene {scene['index']}] Veo generation failed ({exc}); trying next option.")

    if hf_token:
        try:
            _generate_with_huggingface(scene["visual_prompt"], hf_token, out_mp4_path)
            return "huggingface"
        except Exception as exc:
            log(f"  [scene {scene['index']}] Hugging Face video generation failed ({exc}); trying free AI image instead.")

    try:
        _generate_from_free_image(scene, out_mp4_path, target_seconds)
        return "free-ai-image"
    except Exception as exc:
        log(f"  [scene {scene['index']}] Free AI image generation failed ({exc}); using placeholder card.")

    _generate_placeholder(scene, out_mp4_path, target_seconds)
    return "placeholder"


def _generate_with_huggingface(prompt: str, hf_token: str, out_mp4_path: str):
    """Real (if short/rough) AI video motion using Hugging Face's free-tier
    Inference Providers router — no billing setup needed, just a free token."""
    from huggingface_hub import InferenceClient

    client = InferenceClient(provider=HF_T2V_PROVIDER, api_key=hf_token)
    video_bytes = client.text_to_video(prompt, model=HF_T2V_MODEL)
    with open(out_mp4_path, "wb") as f:
        f.write(video_bytes)


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


CARTOON_STYLE_SUFFIX = (
    "Flat 2D cartoon character design, thick clean black outlines, simple "
    "rounded shapes, bright solid flat colors with minimal shading, "
    "Japanese-anime-inspired children's TV show art style, plain simple "
    "background, single character centered in frame, vector illustration "
    "look, no text, no watermark, no photorealism, no 3D render."
)


def _get_with_retry(url: str, params: dict, timeout: int, max_attempts: int = 4):
    """GET with backoff on 429 (rate limit) and 5xx (transient server errors) —
    Pollinations occasionally hiccups on a single request; retrying almost
    always succeeds."""
    last_exc = None
    for attempt in range(max_attempts):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = requests.HTTPError(f"{resp.status_code} error from image service", response=resp)
                time.sleep(8 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            time.sleep(5 * (attempt + 1))
            continue
        except requests.HTTPError as exc:
            last_exc = exc
            code = exc.response.status_code if exc.response is not None else None
            if code == 429 or (code is not None and code >= 500):
                time.sleep(8 * (attempt + 1))
                continue
            raise
    raise last_exc or RuntimeError("Pollinations request failed after retries")


def _generate_from_free_image(scene: dict, out_mp4_path: str, target_seconds: float):
    """Free, keyless: get an AI-illustrated picture for this scene from
    Pollinations.ai and animate it with a Ken Burns pan/zoom."""
    prompt = scene.get("visual_prompt") or scene.get("narration_en") or scene.get("narration_ta") or "a cheerful cartoon scene"
    # Belt-and-suspenders: force the flat-cartoon look even if the prompt
    # came from an older job / naive split that didn't include it.
    if "flat 2d cartoon" not in prompt.lower():
        prompt = f"{prompt} {CARTOON_STYLE_SUFFIX}"
    encoded = urllib.parse.quote(prompt[:600])
    url = POLLINATIONS_URL.format(prompt=encoded)
    seed = abs(hash(prompt)) % 100000

    resp = _get_with_retry(
        url,
        params={"width": 1280, "height": 720, "nologo": "true", "seed": seed, "quality": "high"},
        timeout=60,
    )
    if not resp.headers.get("content-type", "").startswith("image"):
        raise ValueError("free image service did not return an image")

    tmp_dir = os.path.dirname(out_mp4_path)
    still_path = os.path.join(tmp_dir, f"_ai_still_{scene['index']}.jpg")
    with open(still_path, "wb") as f:
        f.write(resp.content)

    _ken_burns_from_still(still_path, out_mp4_path, target_seconds)
    os.remove(still_path)


def _generate_placeholder(scene: dict, out_mp4_path: str, target_seconds: float):
    """Last-resort fallback: a colorful card with the scene text on it."""
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

    _ken_burns_from_still(still_path, out_mp4_path, target_seconds)
    os.remove(still_path)


def _ken_burns_from_still(still_path: str, out_mp4_path: str, target_seconds: float):
    width, height = 1280, 720
    duration = max(2.0, target_seconds)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", still_path,
            "-t", str(duration),
            "-vf",
            (
                f"scale=1600:900:force_original_aspect_ratio=increase,crop=1600:900,"
                f"zoompan=z='min(zoom+0.0008,1.15)':"
                f"d={int(duration * 25)}:s={width}x{height}:fps=25"
            ),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", out_mp4_path,
        ],
        check=True, capture_output=True,
    )


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
