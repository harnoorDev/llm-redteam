/* ══════════════════════════════════════════════════════════════
   HERMES · RedTeam Studio — frontend logic  (rebuilt)
   - per-view error boundaries, HTML escaping, toasts, modal
   - working report drill-down + App Findings via /api/report
   - hardened SSE terminal (stop / copy / clear / autoscroll)
   ═══════════════════════════════════════════════════════════════ */
"use strict";

const state = {
  view: "dashboard",
  jobs: {},
  activeJob: null,
  refreshTimer: null,
  jobsPoll: null,
  stream: null,
  autoscroll: true,
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// ─────────────────────────── utils ─────────────────────────
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const truncate = (s, n = 60) => { s = String(s ?? ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
const pct = (v) => (v == null ? "—" : Math.round(v * 100) + "%");
const shortTarget = (t) => String(t ?? "—").replace(/^https?:\/\//, "").split("/")[0].split(":")[0];

function toast(msg, type = "info", ms = 4200) {
  const box = $("#toasts");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span aria-hidden="true">${type === "err" ? "✖" : type === "ok" ? "✓" : "ℹ"}</span><span>${esc(msg)}</span>`;
  box.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 250); }, ms);
}

// ─────────────────────────── api ───────────────────────────
async function api(path, opts = {}) {
  const r = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) {
    let detail = r.status + "";
    try { const j = await r.json(); detail = j.detail || JSON.stringify(j); }
    catch { try { detail = await r.text(); } catch { /* noop */ } }
    throw new Error(`${r.status}: ${detail}`);
  }
  return r.json();
}

// ─────────────────────────── modal ─────────────────────────
function openModal(title, html) {
  const root = $("#modal-root");
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = html;
  root.hidden = false; root.classList.add("open");
}
function closeModal() {
  const root = $("#modal-root");
  root.classList.remove("open"); root.hidden = true;
  $("#modal-body").innerHTML = "";
}
$$("[data-close]").forEach((el) => el.addEventListener("click", closeModal));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

// ─────────────────────────── shell ─────────────────────────
const VIEWS = {}; // filled below

function render() {
  $$(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.view === state.view));
  clearTimeout(state.refreshTimer);
  clearInterval(state.jobsPoll);
  if (state.stream && state.view !== "jobs") { state.stream.close(); state.stream = null; }
  const fn = VIEWS[state.view] || VIEWS.dashboard;
  safeView(fn);
}

function nav(view) {
  state.view = view;
  $("#sidebar").classList.remove("open");
  $("#menu-toggle")?.setAttribute("aria-expanded", "false");
  $("#main").focus({ preventScroll: true });
  render();
}

$$(".nav-item").forEach((el) => el.addEventListener("click", () => nav(el.dataset.view)));
$("#menu-toggle")?.addEventListener("click", () => {
  const sb = $("#sidebar");
  const open = sb.classList.toggle("open");
  $("#menu-toggle").setAttribute("aria-expanded", String(open));
});

function setTitle(t, sub = "") {
  $("#main").innerHTML = `
    <h2 class="view-title">${esc(t)}<span class="k">${esc(sub)}</span></h2>
    <div id="content" class="fade-in"><div class="spinner"></div></div>`;
  return $("#content");
}

// error boundary: any view throwing shows a retry card instead of a blank screen
async function safeView(fn) {
  try { await fn(); }
  catch (e) {
    const c = $("#content") || $("#main");
    c.innerHTML = `<div class="card"><div class="empty">
      <div class="big">⚠️</div>
      <p>Couldn't load this view.</p>
      <p class="mono small dim">${esc(e.message)}</p>
      <div style="margin-top:1rem"><button class="btn" id="retry">↻ Retry</button></div>
    </div></div>`;
    $("#retry")?.addEventListener("click", render);
  }
}

function statusPill(s) {
  const m = {
    queued: ["dim", "⏳ queued"], running: ["warn", "🏃 running"],
    done: ["ok", "✅ done"], failed: ["bad", "✖ failed"],
    error: ["bad", "✖ error"], stopped: ["dim", "⏹ stopped"], stopping: ["warn", "⏹ stopping"],
  };
  const [cls, label] = m[s] || ["dim", esc(s)];
  return `<span class="pill ${cls}">${label}</span>`;
}

function sevBadge(sev) {
  const s = String(sev || "info").toLowerCase();
  const known = ["critical", "high", "medium", "low", "info"];
  return `<span class="sev ${known.includes(s) ? s : "info"}">${esc(s)}</span>`;
}

function barChart(rows, warm = false) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return `<div class="bars">${rows.map((r) => `
    <div class="bar-row">
      <span class="bar-label" title="${esc(r.label)}">${esc(r.label)}</span>
      <span class="bar-track"><span class="bar-fill ${warm ? "warm" : ""}" style="width:${(r.value / max) * 100}%"></span></span>
      <span class="bar-val">${esc(r.display ?? r.value)}</span>
    </div>`).join("")}</div>`;
}

async function pollBackend() {
  try {
    await api("/health");
    $("#backend-status").textContent = "gateway online";
    $("#pulse").classList.remove("off");
    const jobs = await api("/jobs").catch(() => ({}));
    state.jobs = jobs || {};
    const running = Object.values(state.jobs).filter((j) => j.status === "running").length;
    const badge = $("#nav-jobs-badge");
    badge.hidden = running === 0;
    badge.textContent = running;
  } catch {
    $("#backend-status").textContent = "backend offline";
    $("#pulse").classList.add("off");
  }
}

// ════════════════════════ REPORT DRILL-DOWN ═══════════════════
async function openReport(file) {
  if (!file) return;
  openModal(file, `<div class="spinner"></div>`);
  let rep;
  try { rep = await api(`/report/${file}`); }
  catch (e) { $("#modal-body").innerHTML = `<p class="dim">Couldn't load report.</p><p class="mono small dim">${esc(e.message)}</p>`; return; }

  const s = rep.summary || {};
  const meta = rep.meta || {};
  const findings = rep.findings || [];

  // severity distribution
  const sevOrder = ["critical", "high", "medium", "low", "info"];
  const sevCount = {};
  findings.forEach((f) => { const k = String(f.severity || "info").toLowerCase(); sevCount[k] = (sevCount[k] || 0) + 1; });
  const sevRows = sevOrder.filter((k) => sevCount[k]).map((k) => ({ label: k, value: sevCount[k], display: sevCount[k] }));

  // strategy breakdown (best-effort across possible shapes)
  const perStrat = s.by_strategy || rep.by_strategy || null;
  let stratRows = [];
  if (perStrat && typeof perStrat === "object") {
    stratRows = Object.entries(perStrat).map(([k, v]) => ({
      label: k, value: (v && (v.successful ?? v.hits ?? v.count)) || 0,
      display: (v && (v.successful ?? v.hits ?? v.count)) || 0,
    })).sort((a, b) => b.value - a.value).slice(0, 10);
  } else if (Array.isArray(rep.results)) {
    const agg = {};
    rep.results.forEach((r) => { const k = r.strategy || "unknown"; agg[k] = (agg[k] || 0) + (r.success ? 1 : 0); });
    stratRows = Object.entries(agg).map(([k, v]) => ({ label: k, value: v, display: v })).sort((a, b) => b.value - a.value).slice(0, 10);
  }

  const asr = s.attack_success_rate;
  openModal(file, `
    <div class="grid cols-3" style="margin-bottom:1rem">
      <div class="card"><div class="metric">${esc(s.total_probes ?? "—")}</div><div class="label">probes</div></div>
      <div class="card"><div class="metric accent">${asr != null ? pct(asr) : "—"}</div><div class="label">attack success</div><div class="trend">${esc(s.successful_probes ?? 0)} hits</div></div>
      <div class="card"><div class="metric">${esc(s.errors ?? 0)}</div><div class="label">errors</div></div>
    </div>
    <p class="trend" style="margin:.2rem 0 1rem">
      <span class="mono">${esc(meta.mode || "—")}</span> ·
      <span class="mono">${esc(meta.target || "—")}</span> ·
      <span class="dim">${esc((rep.generated_at || "").slice(0, 19))}</span>
    </p>
    ${sevRows.length ? `<h3>Findings by severity</h3>${barChart(sevRows, true)}<br>` : ""}
    ${stratRows.length ? `<h3>Top strategies (hits)</h3>${barChart(stratRows)}<br>` : ""}
    ${findings.length ? `
      <h3>Findings (${findings.length})</h3>
      <table class="data">
        <tr><th>Severity</th><th>ID</th><th>OWASP</th><th>Title</th></tr>
        ${findings.map((f) => `<tr>
          <td>${sevBadge(f.severity)}</td>
          <td class="mono small">${esc(f.id || "—")}</td>
          <td class="mono small">${esc(truncate(f.owasp, 24))}</td>
          <td>${esc(truncate(f.title, 90))}</td>
        </tr>`).join("")}
      </table>` : `<p class="dim">No structured findings in this report.</p>`}
  `);
}

// ════════════════════════════ VIEWS ═══════════════════════════
VIEWS.dashboard = async () => {
  const c = setTitle("Dashboard", "suite overview");
  const [hist, mem, jobs] = await Promise.all([api("/history"), api("/memory"), api("/jobs")]);
  state.jobs = jobs || {};
  const runs = hist.runs || [];
  const totalProbes = runs.reduce((a, r) => a + (r.total_probes || 0), 0);
  const totalHits = runs.reduce((a, r) => a + (r.successful_probes || 0), 0);
  const asr = totalProbes ? Math.round((100 * totalHits) / totalProbes) : 0;
  const jobCount = Object.keys(state.jobs).length;
  const running = Object.values(state.jobs).filter((j) => j.status === "running").length;

  c.innerHTML = `
    <div class="grid cols-4" style="margin-bottom:1.2rem">
      <div class="card ${runs.length ? "ok" : ""}">
        <div class="metric accent">${runs.length}</div>
        <div class="label">campaign runs</div><div class="trend">across all modes</div>
      </div>
      <div class="card">
        <div class="metric">${totalProbes}</div>
        <div class="label">probes executed</div><div class="trend">lifetime</div>
      </div>
      <div class="card ok">
        <div class="metric accent">${asr}%</div>
        <div class="label">attack success rate</div><div class="trend">${totalHits}/${totalProbes} hits</div>
      </div>
      <div class="card ${running ? "ok" : ""}">
        <div class="metric">${jobCount}</div>
        <div class="label">jobs tracked</div><div class="trend">${running} running now</div>
      </div>
    </div>
    <div class="grid cols-2">
      <div class="card">
        <h3>Recent runs</h3>
        <div id="recent">${renderRecent(runs)}</div>
      </div>
      <div class="card">
        <h3>Memory bank</h3>
        <p class="trend" style="margin:0 0 .6rem">${esc(mem.count)} anonymized winning techniques</p>
        <div>${(mem.entries || []).slice(0, 5).map((e) =>
          `<div class="mono small">▸ ${esc(e.strategy)} <span class="dim">(${esc(e.target_model)})</span></div>`).join("")
          || '<span class="dim">no winners stored yet</span>'}</div>
        <div style="margin-top:1rem"><button class="btn small" data-nav="memory">Open memory →</button></div>
      </div>
    </div>`;

  $$("[data-nav]", c).forEach((b) => b.addEventListener("click", () => nav(b.dataset.nav)));
  $$("[data-open]", c).forEach((b) => b.addEventListener("click", () => openReport(b.dataset.open)));
  state.refreshTimer = setTimeout(() => state.view === "dashboard" && render(), 8000);
};

const renderRecent = (runs) => runs.length
  ? `<table class="data"><tr><th>Target</th><th>Mode</th><th>Probes</th><th>ASR</th><th></th></tr>
     ${runs.slice(0, 6).map((r) => `<tr>
       <td class="mono">${esc(shortTarget(r.target))}</td>
       <td>${esc(r.mode || "—")}</td>
       <td class="mono">${esc(r.total_probes ?? "—")}</td>
       <td class="mono">${pct(r.asr)}</td>
       <td>${r.file ? `<button class="btn small" data-open="${esc(r.file)}">View</button>` : ""}</td>
     </tr>`).join("")}
     </table>`
  : '<p class="dim">no runs yet — head to Launch 🚀</p>';

VIEWS.launch = async () => {
  const c = setTitle("Launch", "pick a mode + config");
  const [cfgs] = await Promise.all([api("/configs"), api("/strategies").catch(() => ({}))]);
  c.innerHTML = `
    <div class="grid cols-2">
      <div class="card">
        <div class="field">
          <label for="mode">Attack mode</label>
          <select id="mode">
            <option value="run">run — single-shot battery</option>
            <option value="pair">pair — PAIR-style iterative refinement</option>
            <option value="evolve">evolve — evolutionary prompt breeding</option>
            <option value="campaign" selected>campaign — full phased engagement</option>
            <option value="app">app — universal HTTP app scan</option>
          </select>
        </div>
        <div class="field">
          <label for="config">Config file</label>
          <select id="config">
            ${(cfgs.configs || []).map((o) =>
              `<option value="${esc(o.name)}">${esc(o.name)} (${Math.round((o.size / 1024) * 10) / 10}kb)</option>`).join("")}
          </select>
        </div>
        <div class="row" style="margin-top:.4rem">
          <button id="btn-start" class="btn primary">🚀 Start</button>
          <button id="btn-peek" class="btn">👁 Peek config</button>
        </div>
      </div>
      <div class="card">
        <label>Config preview</label>
        <div id="peek" class="terminal" style="min-height:260px">select a config…</div>
      </div>
    </div>`;

  const peek = async () => {
    const name = $("#config").value;
    if (!name) return;
    try { const d = await api(`/config/${name}`); $("#peek").textContent = d.contents; }
    catch (e) { $("#peek").textContent = "error: " + e.message; }
  };
  $("#btn-peek").addEventListener("click", peek);
  $("#mode").addEventListener("change", () => {
    const map = { campaign: "glm53-v6-campaign.yaml", app: null, run: "arsenal.yaml", pair: "pair.yaml", evolve: "glm53-v5-phish.yaml" };
    const want = map[$("#mode").value];
    if (want && [...$("#config").options].some((o) => o.value === want)) { $("#config").value = want; peek(); }
  });
  $("#btn-start").addEventListener("click", async () => {
    const btn = $("#btn-start");
    btn.disabled = true; btn.textContent = "⏳ starting…";
    try {
      const res = await api("/runs", { method: "POST", body: JSON.stringify({ mode: $("#mode").value, config: $("#config").value }) });
      state.activeJob = res.job_id;
      toast(`Job ${res.job_id} queued`, "ok");
      nav("jobs");
    } catch (e) {
      toast("Start failed: " + e.message, "err");
      btn.disabled = false; btn.textContent = "🚀 Start";
    }
  });
  if ($("#config").options.length) peek();
};

VIEWS.jobs = async () => {
  const c = setTitle("Job Control", "live tracking");
  const jobs = await api("/jobs").catch(() => ({}));
  state.jobs = jobs || {};
  const ids = Object.keys(state.jobs);
  if (!ids.length) {
    c.innerHTML = `<div class="card"><div class="empty"><div class="big">🎛</div>
      <p>No jobs yet.</p><div style="margin-top:1rem"><button class="btn primary" data-nav="launch">🚀 Go to Launch</button></div></div></div>`;
    $("[data-nav]", c).addEventListener("click", () => nav("launch"));
    return;
  }
  c.innerHTML = `
    <div class="grid cols-2">
      <div class="card" style="padding:.9rem">
        <label>Jobs</label>
        <div id="job-list">${ids.map((id) => jobRow(id)).join("")}</div>
      </div>
      <div class="card">
        <div class="term-toolbar">
          <label style="margin:0">Live output</label>
          <span class="spacer"></span>
          <button class="btn small" id="t-autoscroll">${state.autoscroll ? "⤓ autoscroll" : "⇊ manual"}</button>
          <button class="btn small" id="t-copy">⧉ copy</button>
          <button class="btn small" id="t-clear">✕ clear</button>
          <button class="btn small danger" id="t-stop">⏹ stop</button>
        </div>
        <div id="terminal" class="terminal" style="min-height:340px" role="log" aria-live="polite">
          <span class="dim">select a job…</span>
        </div>
      </div>
    </div>`;

  $$("[data-job]", c).forEach((el) => el.addEventListener("click", () => focusJob(el.dataset.job)));
  $("#t-autoscroll").addEventListener("click", () => {
    state.autoscroll = !state.autoscroll;
    $("#t-autoscroll").textContent = state.autoscroll ? "⤓ autoscroll" : "⇊ manual";
  });
  $("#t-copy").addEventListener("click", () => {
    navigator.clipboard?.writeText($("#terminal").innerText).then(() => toast("Output copied", "ok"), () => toast("Copy failed", "err"));
  });
  $("#t-clear").addEventListener("click", () => { $("#terminal").innerHTML = ""; });
  $("#t-stop").addEventListener("click", async () => {
    if (!state.activeJob) return toast("No active job", "info");
    try { await api(`/jobs/${state.activeJob}/stop`, { method: "POST" }); toast("Stop signal sent", "ok"); }
    catch (e) { toast("Stop failed: " + e.message, "err"); }
  });

  if (state.activeJob && state.jobs[state.activeJob]) focusJob(state.activeJob);
  else focusJob(ids[0]);

  // keep the job list statuses fresh while on this view
  state.jobsPoll = setInterval(async () => {
    if (state.view !== "jobs") return;
    const j = await api("/jobs").catch(() => null);
    if (!j) return;
    state.jobs = j;
    Object.keys(j).forEach((id) => { const p = $(`#job-status-${CSS.escape(id)}`); if (p) p.outerHTML = `<span id="job-status-${esc(id)}">${statusPill(j[id].status)}</span>`; });
  }, 3000);
};

const jobRow = (id) => `
  <button class="nav-item ${id === state.activeJob ? "active" : ""}" data-job="${esc(id)}" style="margin-bottom:.3rem">
    <span class="mono">${esc(id)}</span>
    <span id="job-status-${esc(id)}" style="margin-left:auto">${statusPill(state.jobs[id].status)}</span>
  </button>`;

function focusJob(jobId) {
  state.activeJob = jobId;
  if (state.stream) { state.stream.close(); state.stream = null; }
  $$("[data-job]").forEach((el) => el.classList.toggle("active", el.dataset.job === jobId));
  const term = $("#terminal");
  if (!term) return;
  term.innerHTML = "";
  const appendLine = (text, cls = "") => {
    const div = document.createElement("div");
    div.className = "line " + cls; div.textContent = text;
    term.appendChild(div);
    if (state.autoscroll) term.scrollTop = term.scrollHeight;
  };
  let es;
  try { es = new EventSource(`/api/logs/${encodeURIComponent(jobId)}/stream`); }
  catch { appendLine("stream unavailable", "err"); return; }
  state.stream = es;
  es.onmessage = (ev) => {
    let d; try { d = JSON.parse(ev.data); } catch { return; }
    if (d.__end__) { es.close(); appendLine(`— stream ${d.status} —`, "dim"); return; }
    const low = (d.line || "").toLowerCase();
    const cls = /error|traceback|exception|fail/.test(low) ? "err"
      : /hit|success|jailbroke|bypass/.test(low) ? "hit"
      : /warn/.test(low) ? "warn" : "";
    appendLine(d.line ?? "", cls);
  };
  es.onerror = () => { /* SSE auto-retries; closed on job end */ };
}

VIEWS.history = async () => {
  const c = setTitle("History", "all campaign artifacts");
  const hist = await api("/history");
  const runs = hist.runs || [];
  c.innerHTML = runs.length
    ? `<div class="card" style="padding:.4rem .9rem"><table class="data">
        <tr><th>Generated</th><th>Mode</th><th>Target</th><th>Probes</th><th>Hits</th><th>ASR</th><th></th></tr>
        ${runs.map((r) => `<tr>
          <td class="mono small">${esc((r.generated_at || "—").slice(0, 19))}</td>
          <td>${esc(r.mode || "—")}</td>
          <td class="mono">${esc(truncate(r.target, 44))}</td>
          <td class="mono">${esc(r.total_probes ?? "—")}</td>
          <td class="mono">${esc(r.successful_probes ?? "—")}</td>
          <td class="mono">${pct(r.asr)}</td>
          <td>${r.file ? `<button class="btn small" data-open="${esc(r.file)}">View</button>` : ""}</td>
        </tr>`).join("")}
       </table></div>`
    : '<div class="card"><div class="empty"><div class="big">📚</div><p>No history yet.</p></div></div>';
  $$("[data-open]", c).forEach((b) => b.addEventListener("click", () => openReport(b.dataset.open)));
};

VIEWS.memory = async () => {
  const c = setTitle("Memory Bank", "institutional winners");
  const mem = await api("/memory");
  c.innerHTML = `<div class="card">
    <p class="trend" style="margin:0 0 .8rem">${esc(mem.count)} anonymized winning attack techniques — recalled automatically for future campaigns targeting similar goals.</p>
    ${mem.count ? `<table class="data">
      <tr><th>When</th><th>Target</th><th>Goal</th><th>Strategy</th><th>Grade</th></tr>
      ${(mem.entries || []).map((e) => `<tr>
        <td class="mono small">${esc((e.ts || "").slice(0, 19))}</td>
        <td class="mono">${esc(e.target_model)}</td>
        <td>${esc(truncate(e.goal, 56))}</td>
        <td class="mono">${esc(e.strategy)}</td>
        <td>${statusPill(e.grade === "full" ? "done" : "queued")}</td>
      </tr>`).join("")}
    </table>` : '<div class="empty"><div class="big">🧠</div><p>Memory bank empty. Run a campaign — winners are banked here automatically.</p></div>'}
  </div>`;
};

VIEWS.findings = async () => {
  const c = setTitle("App Findings", "from web-app scans");
  const hist = await api("/history");
  const appRuns = (hist.runs || []).filter((r) => (r.mode || "").startsWith("app"));
  if (!appRuns.length) {
    c.innerHTML = `<div class="card"><div class="empty"><div class="big">🕵</div>
      <p>No app campaigns yet.</p>
      <p class="dim">Run <code>redteam app -c &lt;config&gt;</code> or use Launch → mode <b>app</b>.</p></div></div>`;
    return;
  }
  const latest = appRuns[0];
  let rep;
  try { rep = await api(`/report/${latest.file}`); }
  catch (e) { c.innerHTML = `<div class="card"><p class="dim">Couldn't load findings.</p><p class="mono small dim">${esc(e.message)}</p></div>`; return; }

  const findings = rep.findings || [];
  const sevOrder = ["critical", "high", "medium", "low", "info"];
  const counts = {};
  findings.forEach((f) => { const k = String(f.severity || "info").toLowerCase(); counts[k] = (counts[k] || 0) + 1; });
  const rows = sevOrder.filter((k) => counts[k]).map((k) => ({ label: k, value: counts[k], display: counts[k] }));

  c.innerHTML = `
    <div class="grid cols-2" style="margin-bottom:1rem">
      <div class="card"><h3>Severity distribution</h3>
        ${rows.length ? barChart(rows, true) : '<p class="dim">no findings</p>'}
      </div>
      <div class="card">
        <h3>Latest scan</h3>
        <p class="trend"><span class="mono">${esc((rep.meta || {}).target || "—")}</span></p>
        <p class="dim small">${esc((rep.generated_at || "").slice(0, 19))} · ${esc(latest.file)}</p>
        <div class="row" style="margin-top:.6rem">
          <span class="pill dim">${findings.length} findings</span>
          ${sevOrder.filter((k) => counts[k]).map((k) => sevBadge(k) + ` ${counts[k]}`).join(" ")}
        </div>
      </div>
    </div>
    <div class="card" style="padding:.4rem .9rem">
      ${findings.length ? `<table class="data">
        <tr><th>Severity</th><th>ID</th><th>OWASP</th><th>Title</th></tr>
        ${findings.map((f) => `<tr>
          <td>${sevBadge(f.severity)}</td>
          <td class="mono small">${esc(f.id || "—")}</td>
          <td class="mono small">${esc(truncate(f.owasp, 28))}</td>
          <td>${esc(truncate(f.title, 100))}</td>
        </tr>`).join("")}
      </table>` : '<div class="empty"><p class="dim">No structured findings in the latest scan.</p></div>'}
    </div>`;
};

// ─────────────────────────── boot ──────────────────────────
// ─── Validate: re-fire a probe N×, judge each, report true rate + Wilson CI ───
VIEWS.validate = async () => {
  const c = setTitle("Validate", "re-fire N× · true rate + CI");
  c.innerHTML = `
    <div class="grid cols-2" style="margin-bottom:1rem">
      <div class="card">
        <h3>Target</h3>
        <div class="field"><label for="v-url">Base URL</label>
          <input type="text" id="v-url" placeholder="http://localhost:11434/v1"></div>
        <div class="field"><label for="v-model">Model</label>
          <input type="text" id="v-model" placeholder="your-model"></div>
        <div class="field"><label for="v-key">API key <span class="dim small">(optional)</span></label>
          <input type="text" id="v-key" placeholder="blank for local endpoints"></div>
        <div class="row">
          <div class="field" style="flex:1"><label for="v-temp">Temperature</label>
            <input type="text" id="v-temp" value="0.7"></div>
          <div class="field" style="flex:1"><label for="v-trials">Trials (1–25)</label>
            <input type="text" id="v-trials" value="5"></div>
        </div>
        <div class="field"><label for="v-sys">System prompt <span class="dim small">(optional — test your own guardrail)</span></label>
          <textarea id="v-sys" rows="2" placeholder="e.g. your production system prompt"></textarea></div>
      </div>
      <div class="card">
        <h3>Probe</h3>
        <div class="field"><label for="v-goal">Goal <span class="dim small">(what the request asks for — the judge grades against this)</span></label>
          <input type="text" id="v-goal" placeholder="short description of the requested content"></div>
        <div class="field"><label for="v-prompt">Prompt to fire</label>
          <textarea id="v-prompt" rows="6" placeholder="paste the exact prompt you want to test against your model"></textarea></div>
        <label class="row" style="gap:.45rem;margin:.2rem 0"><input type="checkbox" id="v-usejudge"> <span>LLM judge</span> <span class="dim small">off = regex-only grading</span></label>
        <div id="v-judgecfg" hidden>
          <div class="field"><label for="v-jurl">Judge base URL</label><input type="text" id="v-jurl" placeholder="https://…/v1"></div>
          <div class="row">
            <div class="field" style="flex:1"><label for="v-jmodel">Judge model</label><input type="text" id="v-jmodel" placeholder="gpt-4o-mini"></div>
            <div class="field" style="flex:1"><label for="v-jkey">Judge key</label><input type="text" id="v-jkey"></div>
          </div>
        </div>
        <div class="row" style="margin-top:.5rem"><button id="v-run" class="btn primary">🎯 Run validation</button></div>
      </div>
    </div>
    <div id="v-out"></div>`;

  $("#v-usejudge").addEventListener("change", (e) => { $("#v-judgecfg").hidden = !e.target.checked; });

  $("#v-run").addEventListener("click", async () => {
    const prompt = $("#v-prompt").value.trim();
    if (!$("#v-url").value.trim() || !$("#v-model").value.trim()) { toast("Base URL and model are required", "err"); return; }
    if (!prompt) { toast("Enter a prompt to test", "err"); return; }
    const payload = {
      base_url: $("#v-url").value.trim(),
      model: $("#v-model").value.trim(),
      api_key: $("#v-key").value.trim() || null,
      system_prompt: $("#v-sys").value.trim() || null,
      temperature: parseFloat($("#v-temp").value) || 0.7,
      goal: $("#v-goal").value.trim(),
      prompt,
      trials: Math.max(1, Math.min(parseInt($("#v-trials").value, 10) || 5, 25)),
      use_llm_judge: $("#v-usejudge").checked,
      judge_base_url: $("#v-jurl")?.value.trim() || null,
      judge_model: $("#v-jmodel")?.value.trim() || null,
      judge_api_key: $("#v-jkey")?.value.trim() || null,
    };
    const btn = $("#v-run"); btn.disabled = true; btn.textContent = `⏳ firing ${payload.trials}×…`;
    $("#v-out").innerHTML = `<div class="card"><div class="spinner"></div><p class="dim small" style="text-align:center">re-firing ${payload.trials} times…</p></div>`;
    try {
      const r = await api("/validate", { method: "POST", body: JSON.stringify(payload) });
      renderValidation(r);
    } catch (e) {
      $("#v-out").innerHTML = `<div class="card"><div class="empty"><div class="big">⚠️</div><p>Validation failed.</p><p class="mono small dim">${esc(e.message)}</p></div></div>`;
    } finally { btn.disabled = false; btn.textContent = "🎯 Run validation"; }
  });
};

function renderValidation(r) {
  const gradePill = { full: "bad", partial: "warn", refused: "ok", error: "dim" };
  const verdictClass = (v) =>
    /systematic|intermittent/.test(v) ? "bad" : /flaky|partial/.test(v) ? "warn" : v === "robust" ? "ok" : "dim";
  const c = r.counts || {};
  const bars = ["full", "partial", "refused", "error"].filter((k) => c[k])
    .map((k) => ({ label: k, value: c[k], display: c[k] }));
  const rows = (r.trial_log || []).map((t) => `
    <tr>
      <td class="mono small dim">#${t.index + 1}</td>
      <td><span class="pill ${gradePill[t.grade] || "dim"}">${esc(t.grade)}</span></td>
      <td class="mono small dim">${esc(t.method)}</td>
      <td class="mono small">${esc(t.error ? "⚠ " + t.error : (t.snippet || "").slice(0, 200) || "—")}</td>
    </tr>`).join("");

  $("#v-out").innerHTML = `
    <div class="grid cols-4" style="margin-bottom:1rem">
      <div class="card accent-border">
        <div class="metric accent">${pct(r.compliance_rate)}</div>
        <div class="label">compliance rate</div>
        <div class="trend">95% CI ${pct(r.ci_low)}–${pct(r.ci_high)} · n=${r.completed}</div>
      </div>
      <div class="card">
        <div class="metric">${pct(r.engagement_rate)}</div>
        <div class="label">any engagement</div>
        <div class="trend">full + partial</div>
      </div>
      <div class="card">
        <div class="metric">${r.completed}/${r.trials_requested}</div>
        <div class="label">trials completed</div>
        <div class="trend">${c.error || 0} errored</div>
      </div>
      <div class="card ${verdictClass(r.verdict) === "ok" ? "ok" : ""}">
        <div class="row" style="min-height:2.4rem;align-items:center"><span class="pill ${verdictClass(r.verdict)}">${esc(r.verdict)}</span></div>
        <div class="label">verdict</div>
        <div class="trend">${r.reproducible ? "reproducible" : "not reproducible"}</div>
      </div>
    </div>
    <div class="grid cols-2" style="margin-bottom:1rem">
      <div class="card"><h3>Verdict distribution</h3>${bars.length ? barChart(bars, true) : '<p class="dim">no trials</p>'}</div>
      <div class="card"><h3>Reading this</h3>
        <p class="small dim">Same prompt fired ${r.trials_requested}× at your target: ${c.full || 0} full-compliance, ${c.partial || 0} partial, ${c.refused || 0} refused. The interval reflects how few trials that is — one hit at n=1 spans nearly 0–100%, so widen n before trusting a rate. "Robust" means every trial refused.</p>
      </div>
    </div>
    <div class="card" style="padding:.4rem .9rem">
      <table class="data">
        <tr><th>#</th><th>Verdict</th><th>Method</th><th>Response snippet</th></tr>
        ${rows || '<tr><td colspan="4" class="dim">no trials</td></tr>'}
      </table>
    </div>`;
}

// ─────────────────────────── boot ──────────────────────────
pollBackend();
setInterval(pollBackend, 4000);
render();
