/* ═══════════════════════════════════════════
   CinemaShield — AI Analytics Dashboard JS
   ═══════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", loadAll);

function loadAll() {
  loadAnalyticsSummary();
}

/* ── Summary + Threats ──────────────────── */
async function loadAnalyticsSummary() {
  try {
    const res = await fetch("/api/ai/analytics-summary");
    const data = await res.json();

    // Overview cards
    setText("total-events", data.total_events);
    setText("recent-events", data.recent_24h);
    setText("unique-ips", data.unique_ip_count);

    // Threat level
    const threats = data.threats || {};
    const riskLevel = threats.risk_level || "low";
    const riskScore = threats.risk_score || 0;
    const levelEl = document.getElementById("risk-level");
    levelEl.textContent = riskLevel.toUpperCase();
    levelEl.className = "ai-card-value risk-" + riskLevel;

    // Threat meter
    const fill = document.getElementById("threat-fill");
    fill.style.width = riskScore + "%";
    fill.className = "threat-fill threat-" + riskLevel;
    setText("threat-score", riskScore + " / 100");

    // Anomalies
    const anomalyList = document.getElementById("anomaly-list");
    const anomalies = threats.anomalies || [];
    if (anomalies.length === 0) {
      anomalyList.innerHTML =
        '<p class="empty-state">✅ No anomalies detected — system secure</p>';
    } else {
      anomalyList.innerHTML = anomalies
        .map(
          (a) => `
        <div class="anomaly-item anomaly-${a.severity}">
          <div class="anomaly-header">
            <span class="anomaly-badge">${a.severity.toUpperCase()}</span>
            <span class="anomaly-type">${a.type.replace(/_/g, " ")}</span>
          </div>
          <p class="anomaly-msg">${a.message}</p>
          <p class="anomaly-rec">💡 ${a.recommendation}</p>
        </div>
      `,
        )
        .join("");
    }

    // Auth stats ring
    const auth = data.auth_stats || {};
    const rate = auth.success_rate || 0;
    setText("auth-success", auth.success || 0);
    setText("auth-failed", auth.failed || 0);
    setText("auth-total", auth.total || 0);
    document
      .getElementById("ring-fill")
      .setAttribute("stroke-dasharray", `${rate}, 100`);
    setText("ring-text", rate + "%");

    // Timeline chart
    buildTimeline(data.hourly_distribution || {});

    // Event breakdown
    buildEventBreakdown(data.action_counts || {});
  } catch (err) {
    console.error("Analytics load error:", err);
  }
}

/* ── Timeline Bar Chart ─────────────────── */
function buildTimeline(hourly) {
  const chart = document.getElementById("timeline-chart");
  const labels = document.getElementById("timeline-labels");
  const values = Object.values(hourly).map(Number);
  const max = Math.max(...values, 1);

  chart.innerHTML = "";
  labels.innerHTML = "";

  for (let h = 0; h < 24; h++) {
    const val = hourly[String(h)] || 0;
    const pct = (val / max) * 100;

    const bar = document.createElement("div");
    bar.className = "tl-bar";
    bar.style.height = Math.max(pct, 2) + "%";
    bar.title = `${h}:00 — ${val} event(s)`;
    if (val > 0) bar.classList.add("tl-bar-active");
    chart.appendChild(bar);

    if (h % 3 === 0) {
      const lbl = document.createElement("span");
      lbl.className = "tl-label";
      lbl.textContent = String(h).padStart(2, "0");
      lbl.style.left = (h / 24) * 100 + "%";
      labels.appendChild(lbl);
    }
  }
}

/* ── Event Breakdown ────────────────────── */
function buildEventBreakdown(counts) {
  const container = document.getElementById("event-breakdown");
  const entries = Object.entries(counts);

  if (entries.length === 0) {
    container.innerHTML = '<p class="empty-state">No events recorded yet</p>';
    return;
  }

  const total = entries.reduce((s, [, v]) => s + v, 0);

  container.innerHTML = entries
    .sort((a, b) => b[1] - a[1])
    .map(([action, count]) => {
      const pct = ((count / total) * 100).toFixed(1);
      const cls = getEventClass(action);
      return `
        <div class="event-row">
          <span class="event-name ${cls}">${action}</span>
          <div class="event-bar-track">
            <div class="event-bar-fill ${cls}" style="width: ${pct}%"></div>
          </div>
          <span class="event-count">${count}</span>
        </div>`;
    })
    .join("");
}

function getEventClass(action) {
  if (action.includes("FAIL") || action.includes("EXPIRED")) return "ev-danger";
  if (action.includes("AUTH") || action.includes("PLAYBACK")) return "ev-warn";
  if (action.includes("AI") || action.includes("FORENSIC")) return "ev-ai";
  return "ev-info";
}

/* ── Forensic Fingerprint ───────────────── */
async function generateFingerprint() {
  const theatre =
    document.getElementById("fp-theatre").value.trim() || "THEATRE_001";
  const token =
    document.getElementById("fp-token").value.trim() || "demo-session";

  try {
    const res = await fetch("/api/ai/fingerprint", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theatre_id: theatre, token: token }),
    });
    const fp = await res.json();

    document.getElementById("fp-hash").textContent = fp.fingerprint;
    document.getElementById("fp-short").textContent = fp.fingerprint_short;
    document.getElementById("fp-trace").textContent = fp.traceable
      ? "✅ Yes"
      : "❌ No";
    document.getElementById("fp-time").textContent = new Date(
      fp.generated_at,
    ).toLocaleString();
    document.getElementById("fingerprint-result").style.display = "block";
  } catch (err) {
    console.error("Fingerprint error:", err);
  }
}

/* ── Helpers ─────────────────────────────── */
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
