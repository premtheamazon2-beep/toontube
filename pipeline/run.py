import os
import traceback

from . import scenes as scenes_mod
from . import tts as tts_mod
from . import video_gen as video_gen_mod
from . import subtitles as subtitles_mod
from . import assemble as assemble_mod

JOBS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jobs")


def run_job(job_id: str, params: dict, jobs: dict, jobs_lock):
    """
    params: {
      content, character_name, character_desc,
      languages: ["ta", "en"], api_key (optional)
    }
    Updates jobs[job_id] in place as progress is made.
    """
    def update(**kwargs):
        with jobs_lock:
            jobs[job_id].update(kwargs)

    def log(msg):
        with jobs_lock:
            jobs[job_id]["log"].append(msg)

    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    try:
        api_key = (params.get("api_key") or os.environ.get("GEMINI_API_KEY") or "").strip() or None
        hf_token = (params.get("hf_token") or os.environ.get("HF_TOKEN") or "").strip() or None
        languages = params["languages"]
        content = params["content"]
        character_name = params.get("character_name") or "Chinna Veeran"
        character_desc = params.get("character_desc") or (
            "a brave, cheerful little superhero kid with a red cape"
        )

        update(stage="Planning scenes", percent=5)
        log("Splitting the story into scenes...")
        scene_list = scenes_mod.plan_scenes(content, character_name, character_desc, api_key)
        used_llm = bool(api_key)
        log(f"Created {len(scene_list)} scenes.")

        # if translation is needed but we only have naive-split text, mirror
        # whichever language we do have so downstream steps have *something*
        for s in scene_list:
            if not s["narration_ta"] and not s["narration_en"]:
                s["narration_ta"] = s["narration_en"] = ""
            elif not s["narration_ta"]:
                s["narration_ta"] = s["narration_en"]
            elif not s["narration_en"]:
                s["narration_en"] = s["narration_ta"]

        total_scenes = len(scene_list)
        update(percent=10, stage="Generating video clips")

        # Step 1: one video clip per scene (shared across languages)
        clip_paths = []
        video_source = "demo"
        for s in scene_list:
            clip_path = os.path.join(job_dir, f"clip_{s['index']}.mp4")
            approx_seconds = max(3.0, len(s["narration_en"]) * 0.09)
            src = video_gen_mod.generate_scene_clip(
                s, api_key, clip_path, approx_seconds, log=log, hf_token=hf_token
            )
            video_source = src
            clip_paths.append(clip_path)
            pct = 10 + int(40 * (s["index"] + 1) / total_scenes)
            update(percent=pct)
            log(f"  scene {s['index'] + 1}/{total_scenes} video ready ({src} mode)")

        update(video_mode=video_source)

        # Step 2: per requested language -> audio + subtitles + final assembly
        outputs = {}
        lang_count = len(languages)
        for li, lang in enumerate(languages):
            lang_label = "Tamil" if lang == "ta" else "English"
            update(stage=f"Recording {lang_label} narration", percent=55 + li * 5)
            log(f"Generating {lang_label} narration audio...")

            audio_paths, durations = [], []
            for s in scene_list:
                text = s["narration_ta"] if lang == "ta" else s["narration_en"]
                audio_path = os.path.join(job_dir, f"audio_{lang}_{s['index']}.mp3")
                dur = tts_mod.synthesize(text, lang, audio_path)
                audio_paths.append(audio_path)
                durations.append(dur)

            srt_path = os.path.join(job_dir, f"subs_{lang}.srt")
            entries, t = [], 0.0
            for s, dur in zip(scene_list, durations):
                text = s["narration_ta"] if lang == "ta" else s["narration_en"]
                entries.append((text, t, t + dur))
                t += dur
            subtitles_mod.write_srt(entries, srt_path)

            update(stage=f"Assembling {lang_label} video", percent=70 + li * 10)
            log(f"Assembling final {lang_label} video...")

            pairs = list(zip(clip_paths, audio_paths, durations))
            final_path = os.path.join(job_dir, f"final_{lang}.mp4")
            assemble_mod.assemble_final(pairs, srt_path, job_dir, final_path, log=log)

            outputs[lang] = f"final_{lang}.mp4"
            log(f"{lang_label} video ready!")

        update(
            stage="Done",
            percent=100,
            done=True,
            outputs=outputs,
            used_llm_scenes=used_llm,
        )

    except Exception:
        err = traceback.format_exc()
        update(stage="Failed", error=err, done=True)
