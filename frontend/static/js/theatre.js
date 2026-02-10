// ═══════════════════════════════════════════
// CinemaShield — Theatre Page Logic
// ═══════════════════════════════════════════

const statusBanner = document.getElementById("status-banner");
const statusText = document.getElementById("status-text");
const authForm = document.getElementById("auth-form");
const keyInput = document.getElementById("key-input");
const authBtn = document.getElementById("auth-btn");
const authError = document.getElementById("auth-error");
const authLoading = document.getElementById("auth-loading");
const authSection = document.getElementById("auth-section");
const playerSec = document.getElementById("player-section");
const videoPlayer = document.getElementById("video-player");

let currentToken = null;
let expiryTimer = null;
let countdownTimer = null;
let windowEnd = null;

// ── Check System Status ──────────────────

async function checkStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();

    if (!data.ready) {
      statusBanner.classList.remove("hidden");
      statusBanner.className = "banner banner-warn";
      statusText.textContent =
        "⚠ No movie available yet. Ask the producer to upload a movie first.";
      authBtn.disabled = true;
    } else if (!data.playback_active) {
      statusBanner.classList.remove("hidden");
      statusBanner.className = "banner banner-warn";
      statusText.textContent = `⚠ Playback window is not active. Window: ${formatUTC(data.playback_start)} — ${formatUTC(data.playback_end)}`;
      authBtn.disabled = true;
    } else {
      statusBanner.classList.remove("hidden");
      statusBanner.className = "banner banner-info";
      statusText.textContent = `✅ Movie ready — ${data.shards} shards | Theatre: ${data.theatre_id} | Window ends ${formatUTC(data.playback_end)}`;
      authBtn.disabled = false;
    }
  } catch {
    statusBanner.classList.add("hidden");
  }
}

function formatUTC(iso) {
  const d = new Date(iso);
  return (
    d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) +
    " " +
    d.toLocaleDateString([], { month: "short", day: "numeric" })
  );
}

checkStatus();
setInterval(checkStatus, 30000);

// ── Authentication ───────────────────────

authForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const key = keyInput.value.trim();
  if (!key) return;

  authError.classList.add("hidden");
  authLoading.classList.remove("hidden");
  authBtn.disabled = true;

  try {
    const res = await fetch("/api/authenticate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    });

    const data = await res.json();

    if (!res.ok) {
      authError.textContent = data.error || "Authentication failed";
      authError.classList.remove("hidden");
      authLoading.classList.add("hidden");
      authBtn.disabled = false;
      return;
    }

    // Success — show the player
    authLoading.classList.add("hidden");
    authSection.classList.add("hidden");
    statusBanner.classList.add("hidden");
    playerSec.classList.remove("hidden");

    currentToken = data.token;
    windowEnd = new Date(data.movie_info.window_end);

    document.getElementById("info-shards").textContent = data.movie_info.shards;
    document.getElementById("info-theatre").textContent = data.movie_info.theatre_id;
    document.getElementById("info-time").textContent = data.movie_info.time_remaining;

    // Set DRM watermark
    const watermark = document.getElementById("drm-watermark");
    watermark.setAttribute("data-watermark", `${data.movie_info.theatre_id} • PROTECTED`);

    videoPlayer.src = `/api/stream/${data.token}`;
    videoPlayer.load();
    videoPlayer.play().catch(() => {});

    // Enable screen protection
    enableScreenProtection();

    // Start expiry countdown
    startExpiryCountdown();

  } catch (err) {
    authError.textContent = "Connection error: " + err.message;
    authError.classList.remove("hidden");
    authLoading.classList.add("hidden");
    authBtn.disabled = false;
  }
});

// ═══════════════════════════════════════════
// SCREEN CAPTURE PROTECTION
// ═══════════════════════════════════════════

function enableScreenProtection() {
  // Disable right-click on video
  videoPlayer.addEventListener("contextmenu", (e) => e.preventDefault());

  // Disable keyboard shortcuts for screenshots
  document.addEventListener("keydown", blockScreenCapture);

  // Detect visibility change (screen recording detection heuristic)
  document.addEventListener("visibilitychange", onVisibilityChange);
}

function blockScreenCapture(e) {
  // Block PrintScreen
  if (e.key === "PrintScreen") {
    e.preventDefault();
    showCaptureWarning();
  }
  // Block Ctrl+Shift+S, Ctrl+Shift+I, Ctrl+S
  if (e.ctrlKey && e.shiftKey && (e.key === "S" || e.key === "I" || e.key === "s" || e.key === "i")) {
    e.preventDefault();
    showCaptureWarning();
  }
  if (e.ctrlKey && (e.key === "s" || e.key === "S") && !e.shiftKey) {
    e.preventDefault();
  }
}

function showCaptureWarning() {
  // briefly flash a warning overlay
  const container = document.getElementById("video-container");
  container.style.filter = "brightness(0)";
  setTimeout(() => { container.style.filter = ""; }, 800);
}

function onVisibilityChange() {
  if (document.hidden && videoPlayer && !videoPlayer.paused) {
    videoPlayer.pause();
  }
}

// ═══════════════════════════════════════════
// SESSION AUTO-EXPIRY
// ═══════════════════════════════════════════

function startExpiryCountdown() {
  const timeBadge = document.getElementById("time-badge");
  const infoTime = document.getElementById("info-time");
  const expiryWarning = document.getElementById("expiry-warning");

  // Check every 10 seconds
  countdownTimer = setInterval(() => {
    if (!windowEnd) return;

    const now = new Date();
    const remaining = Math.max(0, Math.floor((windowEnd - now) / 1000));
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;

    infoTime.textContent = `${mins}m ${secs}s`;

    // <5 min warning
    if (remaining < 300 && remaining > 60) {
      timeBadge.className = "time-badge warning";
      expiryWarning.classList.remove("hidden");
    }
    // <1 min danger
    else if (remaining <= 60 && remaining > 0) {
      timeBadge.className = "time-badge danger";
    }
    // Expired
    else if (remaining <= 0) {
      clearInterval(countdownTimer);
      expireSession();
    }
  }, 10000);

  // Also check with server every 60s
  expiryTimer = setInterval(async () => {
    if (!currentToken) return;
    try {
      const res = await fetch(`/api/check-expiry/${currentToken}`);
      const data = await res.json();
      if (data.expired) {
        clearInterval(expiryTimer);
        clearInterval(countdownTimer);
        expireSession();
      }
    } catch {
      // ignore
    }
  }, 60000);
}

function expireSession() {
  videoPlayer.pause();
  videoPlayer.src = "";
  document.getElementById("expired-overlay").classList.remove("hidden");

  // Exit cinema mode if active
  const container = document.getElementById("video-container");
  container.classList.remove("cinema-mode");
  document.querySelectorAll(".cinema-exit").forEach(b => b.remove());
}

// ═══════════════════════════════════════════
// FULLSCREEN / CINEMA MODE
// ═══════════════════════════════════════════

document.getElementById("fullscreen-btn").addEventListener("click", () => {
  const container = document.getElementById("video-container");
  container.classList.add("cinema-mode");

  // Add exit button
  const exitBtn = document.createElement("button");
  exitBtn.className = "cinema-exit";
  exitBtn.textContent = "✕ Exit Cinema";
  exitBtn.addEventListener("click", () => {
    container.classList.remove("cinema-mode");
    exitBtn.remove();
  });
  document.body.appendChild(exitBtn);

  // ESC to exit
  const escHandler = (e) => {
    if (e.key === "Escape") {
      container.classList.remove("cinema-mode");
      exitBtn.remove();
      document.removeEventListener("keydown", escHandler);
    }
  };
  document.addEventListener("keydown", escHandler);
});
