/* ══════════════════════════════════════════════════════════════
   HERMES · RedTeam Studio — frontend logic
   ═══════════════════════════════════════════════════════════════ */
const state = {
  view: "dashboard",
  jobs: {},
  activeJob: null,
  config: null,
  refreshTimer: null,
};

const $ = document.querySelector.bind(document);
const main = $("#main");

// ─────────────────────────── api ───────────────────────────
async function api(path, opts = {}) {
  const r = await fetch(`/api${path}`, {
    headers: {"Content-Type": "application/json"},
    ...opts,
  });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

// ─────────────────────────── shell ─────────────────────────
function render() {
  document.querySelectorAll(".nav-item").forEach(el =>
    el.classList.toggle("active", el.dataset.view === state.view));
  clearTimeout(state.refreshTimer);
  ({dashboard, launch, jobs, history, memory, findings})[state.view]();
}

function nav(view) {
  state.view = view;
  render();
}

document.querySelectorAll(".nav-item").forEach(el => {
  el.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    el.classList.add("active");
    nav(el.dataset.view);
  });
});

function setTitle(t, sub = "") {
  $("#main").innerHTML = `
    <h2 class="view-title">${t}<span class="k">${sub}</span></h2>
    <div id="content" class="fade-in"></div>`;
  return $("#content");
}

function statusPill(s) {
  const m = {queued: ["dim", "⏳ queued"], running: ["warn", "🏃 running"],
             done: ["ok", "✅ done"], failed: ["bad", "✖ failed"],
             error: ["bad", "✖ error"], stopped: ["dim", "⏹ stopped"]};
  const [cls, label] = m[s] || ["dim", s];
  return `<span class="pill ${cls}">${label}</span>`;
}

async function pollBackendStatus() {
  try {
    await api("/health");
    $("#backend-status").textContent = "gateway online";
    $(".pulse-dot").classList.remove("off");
  } catch (e) {
    $("#backend-status").textContent = "backend offline";
    $(".pulse-dot").classList.add("off");
  }
}

// ─────────────────────────── views ─────────────────────────
const dashboard = async () => {
  const c = setTitle("Dashboard", "suite overview");
  const [hist, mem, jobs] = await Promise.all([
    api("/history"), api("/memory"), api("/jobs"),
  ]);
  const runs = hist.runs || [];
  const totalProbes = runs.reduce((s, r) => s + (r.total_probes || 0), 0);
  const totalHits = runs.reduce((s, r) => s + (r.successful_probes || 0), 0);
  const asr = totalProbes ? Math.round(100 * totalHits / totalProbes) : 0;
  const activeCount = Object.values(jobs).filter(j => j.status === "running").length;

  c.innerHTML = `
    <div class="grid cols-4" style="margin-bottom: 1.2rem;">
      <div class="card ${totalHits ? "ok" : ""}">
        <div class="metric accent">${runs.length}</div>
        <div class="label">campaign runs</div>
        <div class="trend">across all modes</div>
      </div>
      <div class="card ${totalProbes ? "ok" : ""}">
        <div class="metric">${totalProbes}</div>
        <div class="label">probes executed</div>
        <div class="trend">lifetime</div>
      </div>
      <div class="card ok">
        <div class="metric" style="color: var(--accent)">${asr}%</div>
        <div class="label">attack success rate</div>
        <div class="trend">${totalHits}/${totalProbes} hits</div>
      </div>
      <div class="card ${activeCount() ? "ok" : ""}">
        <div class="metric">${Object.keys(jobs).length}</div>
        <div class="label">jobs tracked</div>
        <div class="trend">${activeCount()} running now</div>
      </div>
    </div>
    <div class="grid cols-2">
      <div class="card">
        <h3 style="margin:0 0 .7rem; font-size:0.95rem">Recent runs</h3>
        <div id="recent-runs">${renderRecent(runs)}</div>
      </div>
      <div class="card">
        <h3 style="margin:0 0 .7rem; font-size:0.95rem">Memory bank</h3>
        <p class="trend" style="margin:0 0 .6rem;">${mem.count} anonymized winning techniques</p>
        <div id="mem-top">${(mem.entries || []).slice(0, 5).map(e =>
          `<div class="mono small">▸ ${e.strategy} <span class="dim">(${e.target_model})</span></div>`).join("")
          || '<span class="dim">no winners stored yet</span>'}</div>
        <div style="margin-top:1rem;"><button class="btn small" data-nav="memory">Open memory →</button></div>
      </div>
    </div>`;

  c.querySelectorAll("[data-nav]").forEach(b =>
    b.addEventListener("click", () => nav(b.dataset.nav)));
  state.refreshTimer = setTimeout(() => state.view === "dashboard" && render(), 5000);
};

function activeCount() {
  return Object.values(state.jobs).filter(j => j.status === "running").length;
}

const renderRecent = (runs) => runs.length
  ? `<table class="data"><tr><th>Target</th><th>Mode</th><th>Probes</th><th>ASR</th><th></th></tr>
     ${runs.slice(0, 6).map(r => `
       <tr>
         <td class="mono">${(r.target || "—").replace("http://", "").split(":")[0]}</td>
         <td>${r.mode || "—"}</td>
         <td class="mono">${r.total_probes ?? "—"}</td>
         <td class="mono">${(r.asr != null ? (r.asr * 100).toFixed(0) + "%" : "—")}</td>
         <td><button class="btn small" data-open="${r.file}">View</button></td>
       </tr>`).join("")}
     </table>`
  : '<p class="dim">no runs yet — head to Launch 🚀</p>';

// ─────────────────────── launch view ───────────────────────
const launch = async () => {
  const c = setTitle("Launch", "pick a mode + config");
  const [cfgs, strs] = await Promise.all([api("/configs"), api("/strategies")]);
  c.innerHTML = `
    <div class="grid cols-2">
      <div class="card">
        <label>Attack mode</label>
        <select id="mode">
          <option value="run">run — single-shot battery</option>
          <option value="pair">pair — PAIR-style iterative refinement</option>
          <option value="evolve">evolve — evolutionary prompt breeding</option>
          <option value="campaign" selected>campaign — full phased engagement</option>
          <option value="app">app — universal HTTP app scan</option>
        </select>
        <div style="margin-top:.9rem">
          <label>Config file</label>
          <select id="config">
            ${(cfgs.configs || []).map(o =>
              `<option value="${o.name}">${o.name} (${Math.round(o.size / 1024 * 10) / 10}kb)</option>`).join("")}
          </select>
        </div>
        <div style="margin-top:1.2rem; display:flex; gap:.6rem;">
          <button id="btn-start" class="btn primary">🚀 Start</button>
          <button id="btn-validate" class="btn">👁 Peek config</button>
        </div>
      </div>
      <div class="card">
        <label>Config preview</label>
        <div id="config-peek" class="terminal" style="min-height:240px; font-size: 0.72rem;">select a config…</div>
      </div>
    </div>`;

  const peek = async () => {
    const name = $("#mode").value;
    const cfgName = $("#config").value;
    const d = await api(`/config/${cfgName}`);
    $("#config-peek").textContent = d.contents;
  };
  $("#btn-validate").addEventListener("click", peek);
  $("#mode").addEventListener("change", () => {
    const m = $("#mode").value;
    // auto-select config by mode
    const map = {campaign: "glm53-v6-campaign.yaml", app: null,
                 run: "arsenal.yaml", pair: "pair.yaml", evolve: "glm53-v5-phish.yaml"};
    if (map[m] && [...$("#config").options].some(o => o.value === map[m])) {
      $("#config").value = map[m];
    }
  });
  $("#btn-start").addEventListener("click", async () => {
    const btn = $("#btn-start");
    btn.disabled = true;
    try {
      const res = await api("/runs", {
        method: "POST",
        body: JSON.stringify({
          mode: $("#mode").value, config: $("#config").value,
        }),
      });
      state.activeJob = res.job_id;
      nav("jobs");
      setTimeout(() => focusJob(res.job_id), 300);
    } catch (e) {
      alert("start failed: " + e.message);
      btn.disabled = false;
    }
  });
  if ($("#config").options.length) peek();
};

// ─────────────────────── jobs view ─────────────────────────
const jobs = async () => {
  const c = setTitle("Job Control", "live tracking");
  if (!Object.keys(state.jobs).length) {
    try {
      const j = await api("/jobs");
      state.jobs = j || {};
    } catch (e) { state.jobs = {}; }
  }
  const ids = Object.keys(state.jobs);
  if (!ids.length) {
    c.innerHTML = `<div class="card"><p class="dim">No jobs yet.</p>
      <button class="btn primary" data-nav="launch">🚀 Go to Launch</button></div>`;
    c.querySelector("[data-nav]").addEventListener("click", () => nav("launch"));
    return;
  }
  c.innerHTML = `
    <div class="grid cols-2">
      <div class="card" style="padding: .8rem;">
        <label>Job list</label>
        <div id="job-list">${ids.map(id => `
          <div class="nav-item ${id === state.activeJob ? "active" : ""}"
               data-job="${id}" style="margin-bottom:.3rem; display:flex; gap:.6rem;">
            <span class="mono">${id}</span>
            <span id="job-status-${id}">${statusPill(state.jobs[id].status)}</span>
          </div>`).join("")}</div>
      </div>
      <div class="card">
        <label>Live output</label>
        <div id="job-terminal" class="terminal" style="min-height:320px;">
          <span class="dim">select a job…</span>
        </div>
      </div>
    </div>`;
  ids.forEach(id => {
    const el = c.querySelector(`[data-job="${id}"]`);
    el.addEventListener("click", () => focusJob(id));
  });
  if (state.activeJob) focusJob(state.activeJob);
};

let currentStream = null;
function focusJob(jobId) {
  state.activeJob = jobId;
  if (currentStream) currentStream.close();
  if (!state.jobs[jobId]) state.jobs[jobId] = {status: "running", mode: "", config: ""};
  document.querySelectorAll("[data-job]").forEach(el =>
    el.classList.toggle("active", el.dataset.job === jobId));
  const term = $("#job-terminal");
  if (!term) return;
  term.innerHTML = "";
  const es = new EventSource(`/api/logs/${jobId}/stream`);
  currentStream = es;
  es.onmessage = (ev) => {
    const d = JSON.parse(ev.data);
    if (d.__end__) {
      es.close();
      const line = document.createElement("div");
      line.className = "line dim";
      line.textContent = `— stream ${d.status} —`;
      term.appendChild(line);
      return;
    }
    const div = document.createElement("div");
    const lower = (d.line || "").toLowerCase();
    div.className = "line " + (lower.includes("error") || lower.includes("traceback")
                       ? "err" : lower.includes("hit")
                       ? "hit" : "");
    div.textContent = d.line;
    term.appendChild(div);
    term.scrollTop = term.scrollHeight;
  };
}

// ─────────────────────── history / memory / findings ───────
const history = async () => {
  const c = setTitle("History", "all campaign artifacts");
  const hist = await api("/history");
  const runs = hist.runs || [];
  c.innerHTML = runs.length
    ? `<table class="data">
        <tr><th>Generated</th><th>Mode</th><th>Target</th><th>Probes</th>
        <th>Hits</th><th>ASR</th><th>File</th></tr>
        ${runs.map(r => `
          <tr>
            <td class="mono small">${(r.generated_at || "—").slice(0, 19)}</td>
            <td>${r.mode || "—"}</td>
            <td class="mono">${(r.target || "—").slice(0, 50)}</td>
            <td class="mono">${r.total_probes ?? "—"}</td>
            <td class="mono">${r.successful_probes ?? "—"}</td>
            <td class="mono small">${r.file}</td>
          </tr>`).join("")}
       </table>`
    : '<div class="card"><p class="dim">No history yet.</p></div>';
};

const memory = async () => {
  const c = setTitle("Memory Bank", "institutional winners");
  const mem = await api("/memory");
  c.innerHTML = `
    <div class="card">
      <p class="trend" style="margin:0 0 .8rem;">
        ${mem.count} anonymized winning attack techniques — recalled automatically
        for future campaigns targeting similar goals.
      </p>
      ${mem.count ? `
      <table class="data">
        <tr><th>When</th><th>Target</th><th>Goal</th><th>Strategy</th><th>Grade</th></tr>
        ${mem.entries.map(e => `
          <tr>
            <td class="mono">${(e.ts || "").slice(0, 19)}</td>
            <td class="mono">${e.target_model}</td>
            <td>${_short(e.goal, 60)}</td>
            <td class="mono">${e.strategy}</td>
            <td>${statusPill(e.grade === "full" ? "done" : "queued")}</td>
          </tr>`).join("")}
      </table>` : '<p class="dim">Memory bank empty. Run a campaign — winners are automatically banked here.</p>'}
    </div>`;
};

const findings = async () => {
  const c = setTitle("App Findings", "from scans");
  const hist = await api("/history");
  const appRuns = (hist.runs || []).filter(r => r.mode === "app-campaign");
  if (!appRuns.length) {
    c.innerHTML = `<div class="card"><p class="dim">No app campaigns yet. Use
      <code>uv run redteam app -c ...</code> or Launch → mode "app".</p></div>`;
    return;
  }
  // pick most recent, load full report
  const latest = appRuns[0];
  const cfg = await fetch(`/api/config/${latest.file.replace(".json", "")}`)
    .then(r => r.json()).catch(() => null);
  // simpler: try loading the JSON directly (path may differ)
  try {
    const rep = await (await fetch(`/api/config/${latest.file.replace(".json", "")}.yaml`)).json();
    renderFindings(rep);
  } catch (e) {
    c.innerHTML += '<p class="dim">no stored findings</p>';
  }
};

function _short(s, n) { return (s || "").slice(0, 60); }
function renderFindings(rep) {
  const c = $("#content");
  const findings = rep.findings || [];
  c.innerHTML = findings.length
    ? `<table class="data">
       <tr><th>Severity</th><th>ID</th><th>OWASP</th><th>Title</th></tr>
       ${findings.map(f => `
         <tr>
           <td class="sev-${f.severity}">${f.severity}</td>
           <td class="mono">${f.id}</td>
           <td class="mono">${_short(f.owasp, 40)}</td>
           <td>${_short(f.title, 80)}</td>
         </tr>`).join("")}
       </table>`
    : '<p class="dim">no findings yet</p>';
}

// boot
pollBackendStatus();
setInterval(pollBackendStatus, 4000);
render();