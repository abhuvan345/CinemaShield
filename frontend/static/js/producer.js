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

// ── Upload & Pipeline ───────────────────

uploadBtn.addEventListener("click", async () => {
  if (!selectedFile) return;

  uploadBtn.disabled = true;
  uploadBtn.textContent = "Uploading…";

  const form = new FormData();
  form.append("file", selectedFile);

  try {
    const res = await fetch("/api/upload", { method: "POST", body: form });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || "Upload failed");
      uploadBtn.disabled = false;
      uploadBtn.textContent = "Upload & Process";
      return;
    }

    // Hide upload section, show pipeline
    document.getElementById("upload-section").classList.add("hidden");
    pipelineSec.classList.remove("hidden");

    runPipeline(data.movie_id);
  } catch (err) {
    alert("Upload error: " + err.message);
    uploadBtn.disabled = false;
    uploadBtn.textContent = "Upload & Process";
  }
});

function runPipeline(movieId) {
  const steps = document.querySelectorAll(".stepper .step");
  const source = new EventSource(`/api/process/${movieId}`);

  source.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    // Update progress bar
    progressBar.style.width = msg.progress + "%";
    statusText.textContent = msg.message;

    // Update stepper dots
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

copyBtn.addEventListener("click", () => {
  navigator.clipboard.writeText(keyDisplay.textContent).then(() => {
    copyToast.classList.remove("hidden");
    setTimeout(() => copyToast.classList.add("hidden"), 2000);
  });
});
