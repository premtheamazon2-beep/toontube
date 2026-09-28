# ToonTube Maker

A small web app: paste story content → get a kids-cartoon-style animated
video with Tamil and/or English voiceover and subtitles, ready to upload to
YouTube.

**Important — about "Chotta Bheem":** Chhota Bheem is a copyrighted
character. This app will not draw him (or any existing show's characters) —
uploading that to YouTube would get copyright-struck. Instead, you give it an
**original** character (name + short description) and it builds scenes
around that instead. Change `character_name` / `character_desc` in the form
to whatever original character you like.

## What it does

1. Splits your story into scenes.
2. Generates a short video clip per scene.
3. Generates Tamil and/or English narration audio.
4. Burns in matching subtitles.
5. Stitches everything into one MP4 per language, downloadable from the browser.

## Modes

- **Free mode (default, no API key needed):** each scene gets an actual
  AI-illustrated picture from [Pollinations.ai](https://pollinations.ai)
  (free, keyless) of your character/scene, animated with a Ken Burns
  pan/zoom, with real Tamil/English voiceover (`gTTS`, free) and burned-in
  subtitles. No signup, no billing, no cost. This is what you get by
  default — just leave the API key field empty.
- **Placeholder fallback:** if the free image service is briefly
  unreachable, a scene falls back to a plain colored card with the scene
  text instead of a picture — narration/subtitles are unaffected. Usually
  transient; just try again.
- **Real AI video clips (optional, paid):** add a **Gemini API key** (from
  [Google AI Studio](https://aistudio.google.com/apikey)) in the form to use
  Google's **Veo** model instead, which generates actual moving video per
  scene (not just an animated still) and also lets Gemini write cleaner
  scenes and translate between Tamil/English. Veo requires billing enabled
  on the key — check current pricing in Google AI Studio before generating.

You can also set the key once as an environment variable instead of typing
it every time:
```bash
export GEMINI_API_KEY="your-key-here"
```

## Setup

```bash
cd toontube
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

You also need **ffmpeg** installed and on your PATH:
- Mac: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt install ffmpeg`
- Windows: download from ffmpeg.org and add to PATH

## Run it

```bash
python3 app.py
```

Open **http://localhost:5000** in your browser.

## 📱 Deploy free online so you can open it from your phone

The app is a normal web app — the easiest way to use it on mobile is to
deploy it to a free hosting service and just open the link in your phone's
browser (no app install needed). **Render.com** is a good free choice
because it gives full outbound internet access (needed for the Gemini/Veo
and voice APIs) and this project already includes the `Dockerfile` it needs.

**Steps:**

1. **Put the code on GitHub** (Render deploys from a git repo):
   - Create a free account at [github.com](https://github.com) if you don't have one.
   - Create a new empty repository, e.g. `toontube`.
   - From inside the `toontube` folder on your computer:
     ```bash
     git init
     git add .
     git commit -m "ToonTube Maker"
     git branch -M main
     git remote add origin https://github.com/<your-username>/toontube.git
     git push -u origin main
     ```

2. **Deploy on Render:**
   - Sign up free at [render.com](https://render.com) (you can sign in with GitHub).
   - Click **New +** → **Web Service** → connect your `toontube` repo.
   - Render will detect the `Dockerfile` automatically (or pick "Docker" as
     the environment if asked). Choose the **Free** instance type.
   - Under **Environment Variables**, optionally add `GEMINI_API_KEY` with
     your key, so you don't have to paste it into the form every time.
   - Click **Create Web Service**. First build takes a few minutes.

3. Once it's live, Render gives you a URL like
   `https://toontube-xxxx.onrender.com` — **open that link on your phone's
   browser** and use the app exactly like on a computer.

**Good to know about the free tier:**
- The free service "sleeps" after ~15 minutes of no traffic — the first
  request after that takes 30–60 seconds to wake up, then works normally.
- Its disk is temporary — generated videos live under `jobs/<job_id>/` and
  may be cleared on redeploy/restart, so download the video from the app
  soon after it finishes rather than leaving it for later.
- Video generation with real Veo clips can take a few minutes for a
  multi-scene story — that's normal; the progress bar keeps updating.

## Tamil subtitles look like boxes?

Your system needs a font that supports Tamil script for ffmpeg to burn
subtitles correctly. Install "Noto Sans Tamil" (free, from Google Fonts) and
restart the app — `pipeline/assemble.py` already looks for it in the usual
system font folders.

## Uploading to YouTube

Once a video downloads, just upload the MP4 to YouTube as usual. A few tips:
- Keep your character and story fully original to avoid copyright strikes.
- YouTube Kids / made-for-kids content has extra rules (no external links,
  limited comments) — mark the video as "made for kids" if it targets
  children.
- If you used Demo Mode for testing, regenerate with a real Gemini API key
  before publishing so the video isn't just placeholder cards.

## Notes / things you can tune

- `pipeline/scenes.py` — how the story is split into scenes and how visual
  prompts are written for Veo.
- `pipeline/video_gen.py` — swap in a different video-generation API here if
  you prefer something other than Veo (e.g. Runway, Pika, Kling) — just
  replace `_generate_with_veo`.
- `pipeline/tts.py` — uses free Google Translate TTS (`gTTS`). For nicer
  voices, swap in a paid TTS API here.
- Videos and intermediate files are written under `jobs/<job_id>/` — safe to
  delete old job folders to free disk space.
