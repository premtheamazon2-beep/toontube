"""
Text-to-speech for scene narration.

Uses gTTS (needs internet, free, no API key). If gTTS is unavailable or the
network call fails, falls back to a silent audio clip of a reasonable length
so the pipeline can still complete (subtitles still show the text).
"""
import math
import subprocess

FALLBACK_SECONDS_PER_CHAR = 0.09  # rough speaking-rate estimate for silent fallback


def synthesize(text: str, lang: str, out_mp3_path: str) -> float:
    """
    Writes narration audio to out_mp3_path and returns its duration in seconds.
    lang: 'ta' or 'en'
    """
    text = (text or "").strip()
    if not text:
        text = " "

    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang=lang)
        tts.save(out_mp3_path)
        return _probe_duration(out_mp3_path)
    except Exception:
        return _make_silence(text, out_mp3_path)


def _make_silence(text: str, out_mp3_path: str) -> float:
    duration = max(2.0, math.ceil(len(text) * FALLBACK_SECONDS_PER_CHAR))
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", str(duration), "-q:a", "9", out_mp3_path,
        ],
        check=True, capture_output=True,
    )
    return float(duration)


def _probe_duration(path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())
