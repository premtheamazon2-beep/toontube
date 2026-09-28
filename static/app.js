const form = document.getElementById("genForm");
const genBtn = document.getElementById("genBtn");
const progressBox = document.getElementById("progressBox");
const resultBox = document.getElementById("resultBox");
const errorBox = document.getElementById("errorBox");
const stageLabel = document.getElementById("stageLabel");
const barFill = document.getElementById("barFill");
const logBox = document.getElementById("logBox");
const downloads = document.getElementById("downloads");
const modeNote = document.getElementById("modeNote");
const errorText = document.getElementById("errorText");

let pollTimer = null;

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const languages = Array.from(document.querySelectorAll(".langs input[type=checkbox]:checked"))
    .map(cb => cb.value);

  const payload = {
    content: document.getElementById("content").value,
    character_name: document.getElementById("character_name").value,
    character_desc: document.getElementById("character_desc").value,
    languages,
    api_key: document.getElementById("api_key").value,
  };

  if (!payload.content.trim()) {
    alert("Please paste your story content first.");
    return;
  }

  genBtn.disabled = true;
  genBtn.textContent = "Generating...";
  progressBox.classList.remove("hidden");
  resultBox.classList.add("hidden");
  errorBox.classList.add("hidden");
  logBox.textContent = "";
  barFill.style.width = "0%";

  const resp = await fetch("/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await resp.json();

  if (!resp.ok) {
    showError(data.error || "Could not start the job.");
    return;
  }

  poll(data.job_id);
});

function poll(jobId) {
  pollTimer = setInterval(async () => {
    const resp = await fetch(`/status/${jobId}`);
    const job = await resp.json();

    stageLabel.textContent = job.stage || "Working...";
    barFill.style.width = `${job.percent || 0}%`;
    logBox.textContent = (job.log || []).join("\n");
    logBox.scrollTop = logBox.scrollHeight;

    if (job.error) {
      clearInterval(pollTimer);
      showError(job.error);
      return;
    }

    if (job.done) {
      clearInterval(pollTimer);
      showResult(jobId, job);
    }
  }, 1500);
}

function showResult(jobId, job) {
  genBtn.disabled = false;
  genBtn.textContent = "Generate video";
  resultBox.classList.remove("hidden");
  downloads.innerHTML = "";

  const labels = { ta: "Download Tamil video", en: "Download English video" };
  Object.keys(job.outputs || {}).forEach(lang => {
    const a = document.createElement("a");
    a.href = `/download/${jobId}/${lang}`;
    a.textContent = labels[lang] || `Download (${lang})`;
    downloads.appendChild(a);
  });

  modeNote.textContent = job.video_mode === "veo"
    ? "Video clips were generated with Veo AI."
    : "Demo Mode: animated placeholder clips were used (no/failed Gemini API key). Add a Gemini API key to generate real AI video clips.";
}

function showError(msg) {
  genBtn.disabled = false;
  genBtn.textContent = "Generate video";
  errorBox.classList.remove("hidden");
  errorText.textContent = msg;
}
