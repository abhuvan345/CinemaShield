// ═══════════════════════════════════════════
// CinemaShield — Producer Page Logic
// ═══════════════════════════════════════════

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const fileInfo = document.getElementById("file-info");
const fileName = document.getElementById("file-name");
const fileSize = document.getElementById("file-size");
const clearBtn = document.getElementById("clear-file");
const uploadBtn = document.getElementById("upload-btn");

const pipelineSec = document.getElementById("pipeline-section");
const progressBar = document.getElementById("progress-bar");
const statusText = document.getElementById("pipeline-status");

const keySec = document.getElementById("key-section");
const keyDisplay = document.getElementById("key-display");
const copyBtn = document.getElementById("copy-key");
const copyToast = document.getElementById("copy-toast");
const shardCount = document.getElementById("shard-count");
const playbackWin = document.getElementById("playback-window");

const uploadProgress = document.getElementById("upload-progress");
const uploadBar = document.getElementById("upload-bar");
const uploadPercent = document.getElementById("upload-percent");
const theatreIdInput = document.getElementById("theatre-id");

let selectedFile = null;

// ── File Selection ──────────────────────

dropzone.addEventListener("click", () => fileInput.click());

dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("drag-over");
});
dropzone.addEventListener("dragleave", () =>
  dropzone.classList.remove("drag-over"),
);
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("drag-over");
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) setFile(fileInput.files[0]);
});

clearBtn.addEventListener("click", clearFile);

function setFile(file) {
  const ext = file.name.split(".").pop().toLowerCase();
  if (!["mp4", "mkv", "avi", "mov"].includes(ext)) {
    alert("Invalid format. Use MP4, MKV, AVI, or MOV.");
    return;
  }
  selectedFile = file;
  fileName.textContent = file.name;
  fileSize.textContent = formatSize(file.size);
  fileInfo.classList.remove("hidden");
  uploadBtn.classList.remove("hidden");
}

function clearFile() {
  selectedFile = null;
  fileInput.value = "";
  fileInfo.classList.add("hidden");
  uploadBtn.classList.add("hidden");
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

// ── Upload with Progress ────────────────

uploadBtn.addEventListener("click", () => {
  if (!selectedFile) return;

  uploadBtn.disabled = true;
  uploadBtn.textContent = "Uploading…";
  uploadProgress.classList.remove("hidden");

  const form = new FormData();
  form.append("file", selectedFile);
  form.append("theatre_id", theatreIdInput.value.trim() || "THEATRE_001");

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload");

  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      uploadBar.style.width = pct + "%";
      uploadPercent.textContent = `Uploading ${pct}%`;
    }
  };

  xhr.onload = () => {
    const data = JSON.parse(xhr.responseText);
    if (xhr.status !== 200) {
      alert(data.error || "Upload failed");
      uploadBtn.disabled = false;
      uploadBtn.textContent = "Upload & Process";
      uploadProgress.classList.add("hidden");
      return;
    }
    uploadPercent.textContent = "Upload complete!";
    document.getElementById("upload-section").classList.add("hidden");
    pipelineSec.classList.remove("hidden");
    runPipeline(data.movie_id);
  };

  xhr.onerror = () => {
    alert("Upload error. Check your connection.");
    uploadBtn.disabled = false;
    uploadBtn.textContent = "Upload & Process";
    uploadProgress.classList.add("hidden");
  };

  xhr.send(form);
});

// ── Pipeline with Animated Stepper ──────

function runPipeline(movieId) {
  const steps = document.querySelectorAll(".stepper .step");
  const source = new EventSource(`/api/process/${movieId}`);

  source.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    progressBar.style.width = msg.progress + "%";
    statusText.textContent = msg.message;

    const stepMap = {
      cleanup: 0,
      sharding: 1,
      sharding_done: 1,
      encrypting: 2,
      encrypting_done: 2,
      manifest: 3,
      manifest_done: 3,
      done: 4,
    };

    const idx = stepMap[msg.step];
    if (idx !== undefined) {
      steps.forEach((s, i) => {
        s.classList.remove("active");
        if (i < idx) s.classList.add("done");
      });
      steps[idx].classList.add("active");
    }

    if (msg.step === "done") {
      source.close();
      steps.forEach((s) => {
        s.classList.remove("active");
        s.classList.add("done");
      });
      showKey(msg.key, msg.shards);
      loadHistory();
      loadAuditLog();
    }

    if (msg.step === "error") {
      source.close();
      statusText.textContent = "❌ " + msg.message;
      statusText.style.color = "#ff4e6a";
    }
  };

  source.onerror = () => {
    source.close();
    statusText.textContent = "❌ Connection lost";
    statusText.style.color = "#ff4e6a";
  };
}

function showKey(key, shards) {
  keySec.classList.remove("hidden");
  keyDisplay.textContent = key;
  shardCount.textContent = shards;
  playbackWin.textContent = "3 hours from now";
}

// ── Upload Another ──────────────────────

document.getElementById("new-upload-btn").addEventListener("click", () => {
  keySec.classList.add("hidden");
  pipelineSec.classList.add("hidden");
  uploadProgress.classList.add("hidden");
  uploadBar.style.width = "0%";
  progressBar.style.width = "0%";
  const uploadSec = document.getElementById("upload-section");
  uploadSec.classList.remove("hidden");
  uploadBtn.disabled = false;
  uploadBtn.textContent = "Upload & Process";
  clearFile();
  document.querySelectorAll(".stepper .step").forEach(s => {
    s.classList.remove("active", "done");
  });
});

// ── Copy Key ────────────────────────────

copyBtn.addEventListener("click", () => {
  navigator.clipboard.writeText(keyDisplay.textContent).then(() => {
    copyToast.classList.remove("hidden");
    setTimeout(() => copyToast.classList.add("hidden"), 2000);
  });
});

// ── Upload History ──────────────────────

async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    const data = await res.json();

    const list = document.getElementById("history-list");
    const empty = document.getElementById("history-empty");

    if (!data.length) {
      list.classList.add("hidden");
      empty.classList.remove("hidden");
      return;
    }

    empty.classList.add("hidden");
    list.classList.remove("hidden");
    list.innerHTML = data.map(h => `
      <div class="history-item">
        <div>
          <span class="h-name">🎬 ${h.name}</span>
          <span class="h-meta"> — ${h.shards} shards — ${h.theatre_id}</span>
        </div>
        <span class="h-key" title="Click to copy key" onclick="navigator.clipboard.writeText('${h.key}')">${h.key}</span>
      </div>
    `).join("");
  } catch {
    // silently ignore
  }
}

// ── Audit Log ───────────────────────────

async function loadAuditLog() {
  try {
    const res = await fetch("/api/audit-log");
    const data = await res.json();

    const list = document.getElementById("audit-list");
    const empty = document.getElementById("audit-empty");

    if (!data.length) {
      list.classList.add("hidden");
      empty.classList.remove("hidden");
      return;
    }

    empty.classList.add("hidden");
    list.classList.remove("hidden");

    list.innerHTML = data.slice(0, 100).map(e => {
      const t = new Date(e.timestamp);
      const time = t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const cls = getAuditClass(e.action);
      const detail = e.details ? Object.entries(e.details).map(([k,v]) => `${k}: ${v}`).join(" | ") : "";
      return `
        <div class="audit-entry">
          <span class="audit-time">${time}</span>
          <span class="audit-action ${cls}">${e.action}</span>
          <span class="audit-detail">${detail}</span>
        </div>
      `;
    }).join("");
  } catch {
    // silently ignore
  }
}

function getAuditClass(action) {
  if (action.includes("UPLOAD")) return "upload";
  if (action.includes("ENCRYPT")) return "encrypt";
  if (action.includes("SHARD")) return "shard";
  if (action.includes("MANIFEST")) return "manifest";
  if (action.includes("PIPELINE")) return "pipeline";
  if (action.includes("PLAYBACK") && !action.includes("FAIL")) return "playback";
  if (action.includes("FAIL") || action.includes("EXPIRED")) return "failed";
  return "";
}

document.getElementById("refresh-audit").addEventListener("click", loadAuditLog);

// ── Init ────────────────────────────────

loadHistory();
loadAuditLog();
