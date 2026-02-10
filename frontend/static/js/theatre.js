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

    document.getElementById("info-shards").textContent = data.movie_info.shards;
    document.getElementById("info-theatre").textContent =
      data.movie_info.theatre_id;
    document.getElementById("info-time").textContent =
      data.movie_info.time_remaining;

    videoPlayer.src = `/api/stream/${data.token}`;
    videoPlayer.load();
    videoPlayer.play().catch(() => {});
  } catch (err) {
    authError.textContent = "Connection error: " + err.message;
    authError.classList.remove("hidden");
    authLoading.classList.add("hidden");
    authBtn.disabled = false;
  }
});
