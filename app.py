import os
import threading
import uuid

from flask import Flask, render_template, request, jsonify, send_from_directory, abort

from pipeline.run import run_job, JOBS_DIR

app = Flask(__name__)
os.makedirs(JOBS_DIR, exist_ok=True)

jobs = {}
jobs_lock = threading.Lock()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(force=True)
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Please paste your story content first."}), 400

    languages = data.get("languages") or ["ta"]
    languages = [l for l in languages if l in ("ta", "en")] or ["ta"]

    job_id = uuid.uuid4().hex[:12]
    with jobs_lock:
        jobs[job_id] = {
            "stage": "Queued",
            "percent": 0,
            "done": False,
            "error": None,
            "outputs": {},
            "log": [],
        }

    params = {
        "content": content,
        "character_name": (data.get("character_name") or "").strip(),
        "character_desc": (data.get("character_desc") or "").strip(),
        "languages": languages,
        "api_key": (data.get("api_key") or "").strip(),
        "hf_token": (data.get("hf_token") or "").strip(),
    }

    t = threading.Thread(target=run_job, args=(job_id, params, jobs, jobs_lock), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "unknown job"}), 404
        # return a shallow copy so we don't hold the lock during json encoding
        return jsonify(dict(job))


@app.route("/download/<job_id>/<lang>")
def download(job_id, lang):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or lang not in job.get("outputs", {}):
        abort(404)
    filename = job["outputs"][lang]
    job_dir = os.path.join(JOBS_DIR, job_id)
    return send_from_directory(job_dir, filename, as_attachment=True,
                                download_name=f"toontube_{lang}.mp4")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
