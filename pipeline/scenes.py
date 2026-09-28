"""
Turns raw story content into a list of short "scenes" for the video.

If a Gemini API key is supplied, an LLM breaks the story into clean scenes
and writes an English visual-description prompt for each one (used to drive
the Veo video generator). Without a key, a simple rule-based splitter is
used instead so the app still works end-to-end in "Demo Mode".
"""
import json
import re
import requests

GEMINI_TEXT_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_TEXT_MODEL}:generateContent"
)

# Tamil + Latin sentence terminators
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।॥])\s+|\n+")

TAMIL_RE = re.compile(r"[஀-௿]")


def detect_script(text: str) -> str:
    """Returns 'ta' if the text looks like Tamil script, else 'en'."""
    return "ta" if TAMIL_RE.search(text or "") else "en"


def _naive_split(content: str, max_scenes: int) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(content) if p.strip()]
    if not parts:
        return [content.strip()] if content.strip() else []

    # group sentences into ~max_scenes chunks
    if len(parts) <= max_scenes:
        return parts

    chunk_size = -(-len(parts) // max_scenes)  # ceil division
    chunks = []
    for i in range(0, len(parts), chunk_size):
        chunks.append(" ".join(parts[i:i + chunk_size]))
    return chunks[:max_scenes]


def plan_scenes(content: str, character_name: str, character_desc: str,
                 api_key: str | None, max_scenes: int = 6) -> list[dict]:
    """
    Returns a list of scene dicts:
      {"index": int, "narration_ta": str, "narration_en": str, "visual_prompt": str}
    narration_ta / narration_en are filled in as available; empty string if unknown yet.
    """
    src_lang = detect_script(content)

    if api_key:
        try:
            return _plan_scenes_llm(content, character_name, character_desc,
                                     api_key, max_scenes, src_lang)
        except Exception:
            pass  # fall through to naive split on any API problem

    chunks = _naive_split(content, max_scenes)
    style = f"{character_name}: {character_desc}. Children's cartoon animation style, colorful, safe for kids."
    scenes = []
    for i, chunk in enumerate(chunks):
        scenes.append({
            "index": i,
            "narration_ta": chunk if src_lang == "ta" else "",
            "narration_en": chunk if src_lang == "en" else "",
            "visual_prompt": f"{style} Scene: {chunk}",
        })
    return scenes


def _plan_scenes_llm(content, character_name, character_desc, api_key,
                      max_scenes, src_lang) -> list[dict]:
    instructions = f"""You are a children's animation script editor.
Break the following story into {max_scenes} or fewer short scenes for a kids' cartoon video.

The main character is: {character_name} — {character_desc}

For EACH scene return:
- "narration_ta": the scene's narration in Tamil (translate to Tamil if the source is not Tamil)
- "narration_en": the same narration in English (translate to English if the source is not English)
- "visual_prompt": a vivid ENGLISH visual description for an AI video generator, describing the setting
  and action of this scene featuring {character_name} ({character_desc}). Always mention
  "children's cartoon animation style, colorful, 3D animated, no on-screen text" in the prompt.
  Never reference any existing copyrighted character, show, or brand.

Respond ONLY with valid minified JSON: a list of objects with keys
narration_ta, narration_en, visual_prompt. No markdown, no commentary.

STORY:
{content}
"""
    resp = requests.post(
        GEMINI_URL,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": instructions}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    raw_scenes = json.loads(text)

    scenes = []
    for i, s in enumerate(raw_scenes[:max_scenes]):
        scenes.append({
            "index": i,
            "narration_ta": s.get("narration_ta", "").strip(),
            "narration_en": s.get("narration_en", "").strip(),
            "visual_prompt": s.get("visual_prompt", "").strip(),
        })
    if not scenes:
        raise ValueError("LLM returned no scenes")
    return scenes
