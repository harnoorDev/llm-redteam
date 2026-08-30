"""Backend (part 1): app + job engine + basic endpoints."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"
CONFIGS = ROOT / "configs"
UI_DIR = ROOT / "src" / "redteam" / "ui"

app = FastAPI(title="Hermes RedTeam Studio", version="0.1.0")

JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _runner_thread(job_id: str, cmd: list[str]) -> None:
    job = JOBS[job_id]
    buf: list[str] = []
    try:
        with _LOCK:
            job["status"] = "running"
            job["started"] = time.time()
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=str(ROOT))
        with _LOCK:
            job["pid"] = proc.pid
        while True:
            line = proc.stdout.readline()
            if line:
                buf.append(line.rstrip())
                with _LOCK:
                    job["lines"] = buf[-800:]
                    job["last_line"] = line.rstrip()
            elif proc.poll() is not None:
                break
            else:
                time.sleep(0.08)
        rc = proc.returncode
        with _LOCK:
            job["status"] = "done" if rc == 0 else "failed"
            job["returncode"] = rc
            job["finished"] = time.time()
    except Exception as e:
        with _LOCK:
            job["status"] = "error"
            job["last_line"] = f"exception: {e}"
            job["finished"] = time.time()


class RunRequest(BaseModel):
    mode: str
    config: str


@app.get("/api/health")
def health():
    return {"ok": True, "time": time.time()}


@app.get("/api/strategies")
def list_strategies_endpoint():
    from redteam.strategies.base import list_strategies, get_strategy
    out = []
    for name in sorted(list_strategies()):
        s = get_strategy(name)
        out.append({
            "name": name,
            "description": s.description,
            "is_multi_turn": s.is_multi_turn,
        })
    return {"count": len(out), "strategies": out}


class _RunResponse:
    pass


@app.post("/api/runs")
def start_run(req: RunRequest):
    if req.mode not in ("run", "pair", "evolve", "campaign", "app"):
        raise HTTPException(400, f"unknown mode {req.mode}")
    config_path = (CONFIGS / req.config) if not req.config.startswith("/") \
        else Path(req.config)
    if not config_path.exists():
        raise HTTPException(404, f"config not found: {req.config}")

    job_id = uuid.uuid4().hex[:8]
    with _LOCK:
        JOBS[job_id] = {
            "id": job_id, "mode": req.mode, "config": req.config,
            "status": "queued", "lines": [], "last_line": "",
        }
    cmd = [sys.executable, str(ROOT / "src" / "redteam" / "cli.py"),
           req.mode, "-c", str(config_path)]
    threading.Thread(target=_runner_thread, args=(job_id, cmd), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs")
def jobs_endpoint():
    with _LOCK:
        return {jid: {k: v for k, v in j.items() if k != "lines"}
                for jid, j in JOBS.items()}


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str, after: int = 0):
    with _LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "unknown job")
        lines = job["lines"][after:]
        return {
            "id": job_id, "mode": job["mode"], "config": job["config"],
            "status": job["status"], "last_line": job["last_line"],
            "pid": job.get("pid"), "returncode": job.get("returncode"),
            "lines_rolling": len(job["lines"]),
            "started": job.get("started"), "finished": job.get("finished"),
            "new_lines": lines,
        }


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str):
    import signal
    with _LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "unknown job")
        pid = job.get("pid")
        status = job["status"]
    if pid and status == "running":
        try:
            os_proc = subprocess.run(["ps", "-o", "pid=", "-p", str(pid)],
                                     capture_output=True, text=True)
            if os_proc.stdout.strip():
                subprocess.run(["kill", str(pid)], capture_output=True)
                return {"job_id": job_id, "status": "stopping"}
        except Exception as e:
            return {"job_id": job_id, "error": str(e)}
        return {"job_id": job_id, "status": job["status"]}
    return {"job_id": job_id, "status": status}


@app.get("/api/configs")
def configs_endpoint():
    out = []
    for f in sorted(CONFIGS.glob("*.yaml")):
        out.append({"name": f.name, "size": f.stat().st_size})
    return {"count": len(out), "configs": out}


@app.get("/api/config/{name}")
def config_detail(name: str):
    f = CONFIGS / name
    if not f.exists() or not f.name.endswith((".yaml", ".yml")):
        raise HTTPException(404, "not found")
    return {"name": name, "contents": f.read_text()}


@app.get("/api/history")
def history_endpoint():
    out = []
    if RUNS.exists():
        for f in sorted(RUNS.glob("*.json")):
            if f.name.startswith(".state-"):
                continue
            try:
                with open(f) as fh:
                    rep = json.load(fh)
                s = rep.get("summary") or {}
                out.append({
                    "file": f.name,
                    "mode": (rep.get("meta") or {}).get("mode"),
                    "target": (rep.get("meta") or {}).get("target"),
                    "total_probes": s.get("total_probes"),
                    "successful_probes": s.get("successful_probes"),
                    "asr": s.get("attack_success_rate"),
                    "errors": s.get("errors"),
                    "generated_at": rep.get("generated_at"),
                    "size": f.stat().st_size,
                })
            except Exception:
                continue
    out.sort(key=lambda x: x["generated_at"] or "", reverse=True)
    return {"count": len(out), "runs": out}


@app.get("/api/memory")
def memory_endpoint():
    p = RUNS / "attack-memory.json"
    if not p.exists():
        return {"count": 0, "entries": []}
    with open(p) as f:
        entries = json.load(f)
    entries.sort(key=lambda e: e.get("ts") or "", reverse=True)
    return {"count": len(entries), "entries": entries}


@app.get("/api/logs/{job_id}/stream")
def stream_log(job_id: str):
    """SSE live tail of the given job's output."""
    if job_id not in JOBS:
        raise HTTPException(404, "unknown job")

    def gen():
        idx = 0
        while True:
            with _LOCK:
                job = JOBS.get(job_id)
                lines = (job or {}).get("lines") or []
                status = (job or {}).get("status")
                new = lines[idx:]
            if new:
                idx = len(lines)
                for ln in new:
                    yield f"data: {json.dumps({'line': ln})}\n\n"
            if status in ("done", "failed", "error"):
                yield f"data: {json.dumps({'__end__': True, 'status': status})}\n\n"
                return
            time.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/")
def index():
    return FileResponse(UI_DIR / "index.html")


app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")