"""ffmpeg-based assembly: fit each scene's clip to its narration length, mux
audio, concatenate all scenes, and burn in subtitles."""
import os
import shutil
import subprocess

W, H = 1280, 720

# Common install locations for a Tamil-capable font, checked in order.
TAMIL_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansTamil-Regular.ttf",
    "/Library/Fonts/NotoSansTamil-Regular.ttf",
    "C:/Windows/Fonts/NotoSansTamil-Regular.ttf",
    "C:/Windows/Fonts/latha.ttf",
]


def _run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def fit_clip_to_audio(clip_path: str, audio_path: str, audio_duration: float,
                       out_path: str):
    """Scale clip to 1280x720, loop/trim so its video length matches
    audio_duration, and mux the narration audio onto it."""
    _run([
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", clip_path,
        "-i", audio_path,
        "-t", str(audio_duration),
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps=25",
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        out_path,
    ])


def concat_clips(clip_paths: list[str], list_file_path: str, out_path: str):
    with open(list_file_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file_path,
        "-c", "copy", out_path,
    ])


def burn_subtitles(video_path: str, srt_path: str, out_path: str):
    font_dir = None
    for candidate in TAMIL_FONT_CANDIDATES:
        if os.path.exists(candidate):
            font_dir = os.path.dirname(candidate)
            break

    style = "FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=1,MarginV=30"
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    vf = f"subtitles='{srt_escaped}':force_style='{style}'"
    if font_dir:
        vf += f":fontsdir='{font_dir}'"

    _run([
        "ffmpeg", "-y", "-i", video_path,
        "-vf", vf,
        "-c:a", "copy",
        out_path,
    ])


def assemble_final(scene_clip_audio_pairs: list[tuple[str, str, float]],
                    srt_path: str, work_dir: str, out_path: str, log=print):
    """
    scene_clip_audio_pairs: list of (video_clip_path, audio_path, audio_duration)
    Produces out_path (final mp4 with burned-in subtitles).
    """
    fitted_paths = []
    for i, (clip, audio, dur) in enumerate(scene_clip_audio_pairs):
        fitted = os.path.join(work_dir, f"_fitted_{i}.mp4")
        fit_clip_to_audio(clip, audio, dur, fitted)
        fitted_paths.append(fitted)
        log(f"  fitted scene {i + 1}/{len(scene_clip_audio_pairs)}")

    concat_list = os.path.join(work_dir, "_concat_list.txt")
    concatenated = os.path.join(work_dir, "_concatenated.mp4")
    concat_clips(fitted_paths, concat_list, concatenated)
    log("  concatenated all scenes")

    if srt_path and os.path.exists(srt_path):
        burn_subtitles(concatenated, srt_path, out_path)
        log("  burned in subtitles")
    else:
        shutil.copy(concatenated, out_path)

    return out_path
