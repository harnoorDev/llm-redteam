"""Backend (part 1): app + job engine + basic endpoints."""
from __future__ import annotations

import asyncio
import json
import logging
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

from redteam.judge import GRADED_PROMPT, Judge
from redteam.target import OpenAICompatTarget
from redteam.validate import validate_probe

log = logging.getLogger(__name__)

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
        log.exception("job %s crashed", job_id)
        with _LOCK:
            job["status"] = "error"
            job["last_line"] = f"exception: {e}"
            job["finished"] = time.time()


class RunRequest(BaseModel):
    mode: str
    config: str
    validate_reps: int | None = None  # run mode: re-fire each winner N times


@app.get("/api/health")
def health():
    return {"ok": True, "time": time.time()}


@app.get("/api/strategies")
def list_strategies_endpoint():
    from redteam.strategies.base import get_strategy, list_strategies
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


LAUNCH_MODES = ("run", "pair", "evolve", "campaign", "app", "harmbench")


@app.post("/api/runs")
def start_run(req: RunRequest):
    if req.mode not in LAUNCH_MODES:
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
    # reliability pass is a `run`-only flag; clamp to the same bound as /api/validate
    if req.mode == "run" and req.validate_reps:
        cmd += ["--validate", str(max(1, min(int(req.validate_reps), 25)))]
    threading.Thread(target=_runner_thread, args=(job_id, cmd), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/encoders")
def encoders_endpoint():
    """The mutation arsenal, same list the CLI stacks and the MCP server expose."""
    from redteam.encoders import ENCODERS
    return {"count": len(ENCODERS), "encoders": sorted(ENCODERS)}


@app.get("/api/harmbench/categories")
def harmbench_categories_endpoint():
    from redteam.harmbench import HARMBENCH_CATEGORIES
    return {
        "count": len(HARMBENCH_CATEGORIES),
        "categories": [{"name": k, "behaviors": len(v)}
                       for k, v in sorted(HARMBENCH_CATEGORIES.items())],
    }


class RenderRequest(BaseModel):
    goal: str
    strategy: str = "godmode"
    encoder: str | None = None


@app.post("/api/render")
def render_endpoint(req: RenderRequest):
    """Render an attack payload offline (no target contacted).

    Mirrors the MCP `render_attack`/`encode` tools so the Studio can preview
    exactly what a strategy or mutation will put on the wire.
    """
    if not (req.goal or "").strip():
        raise HTTPException(400, "goal is required")
    from redteam.strategies.base import get_strategy, resolve_stack
    try:
        if "+" in req.strategy:
            payload = resolve_stack(req.strategy, req.goal)
            multi = False
        else:
            strat = get_strategy(req.strategy)
            payload = strat.payload(req.goal)
            multi = strat.is_multi_turn
    except KeyError as e:
        raise HTTPException(404, f"unknown strategy {req.strategy!r}") from e
    turns = [payload] if isinstance(payload, str) else list(payload)
    if req.encoder:
        from redteam.encoders import ENCODERS
        if req.encoder not in ENCODERS:
            raise HTTPException(404, f"unknown encoder {req.encoder!r}")
        turns = [str(ENCODERS[req.encoder](t)) for t in turns]
    return {"strategy": req.strategy, "encoder": req.encoder,
            "is_multi_turn": multi, "turns": turns}


class ConvergeRequest(BaseModel):
    runs: list[str]
    top_k: int = 5


@app.post("/api/converge")
def converge_endpoint(req: ConvergeRequest):
    """Mine selected run reports for universal (cross-goal, cross-model) prompts."""
    if not req.runs:
        raise HTTPException(400, "select at least one run report")
    runs_root = RUNS.resolve()
    paths: list[str] = []
    for name in req.runs:
        safe = Path(name).name  # strip directory components
        if not safe.endswith(".json") or safe.startswith(".state-"):
            raise HTTPException(400, f"invalid report name: {name}")
        target = (RUNS / safe).resolve()
        if runs_root not in target.parents or not target.is_file():
            raise HTTPException(404, f"report not found: {name}")
        paths.append(str(target))
    from redteam.converge import discover_universal_prompts
    try:
        return discover_universal_prompts(paths, top_k=max(1, min(req.top_k, 50)))
    except (OSError, json.JSONDecodeError, ValueError) as e:
        raise HTTPException(400, f"converge failed: {e}") from e


class ValidateRequest(BaseModel):
    base_url: str
    model: str
    api_key: str | None = None
    system_prompt: str | None = None
    temperature: float = 0.7
    goal: str = ""
    prompt: str
    trials: int = 5
    use_llm_judge: bool = False
    judge_base_url: str | None = None
    judge_model: str | None = None
    judge_api_key: str | None = None


@app.post("/api/validate")
def run_validation(req: ValidateRequest):
    """Re-fire a caller-supplied probe K times at a caller-supplied target and report a
    true compliance rate with a Wilson confidence interval. Evaluation only: it grades
    responses, it does not generate or mutate attacks."""
    if not req.base_url or not req.model:
        raise HTTPException(400, "base_url and model are required")
    if not (req.prompt or "").strip():
        raise HTTPException(400, "prompt is required")
    n = max(1, min(int(req.trials), 25))
    target = OpenAICompatTarget(
        req.base_url, req.model, req.api_key,
        system_prompt=(req.system_prompt or None),
        temperature=req.temperature,
    )
    judge_target = None
    if req.use_llm_judge and req.judge_base_url and req.judge_model:
        judge_target = OpenAICompatTarget(
            req.judge_base_url, req.judge_model, req.judge_api_key
        )
    judge = Judge(
        judge_target=judge_target,
        judge_prompt=(GRADED_PROMPT if judge_target else None),
    )
    try:
        result = validate_probe(
            target=target, judge=judge,
            goal=req.goal, prompt=req.prompt, trials=n,
        )
    finally:
        target.close()
        if judge_target is not None:
            judge_target.close()
    return result.to_dict()


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
    with _LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "unknown job")
        pid = job.get("pid")
        status = job["status"]
    if pid and status == "running":
        try:
            os_proc = subprocess.run(["ps", "-o", "pid=", "-p", str(pid)],
                                     capture_output=True, text=True, check=False)
            if os_proc.stdout.strip():
                subprocess.run(["kill", str(pid)], capture_output=True, check=False)
                return {"job_id": job_id, "status": "stopping"}
        except (OSError, subprocess.SubprocessError) as e:
            log.warning("could not stop job %s: %s", job_id, e)
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
    return {"name": name, "contents": f.read_text(encoding="utf-8")}


@app.get("/api/history")
def history_endpoint():
    out = []
    if RUNS.exists():
        for f in sorted(RUNS.glob("*.json")):
            # runs/ also holds non-report sidecars: resume state, the strix
            # coverage ledger, and the shared attack-memory bank (a JSON list).
            if f.name.startswith((".state-", "coverage-")) or \
                    f.name == "attack-memory.json":
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    rep = json.load(fh)
                if not isinstance(rep, dict) or not (
                        "summary" in rep or "results" in rep):
                    continue  # not a run report
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
            except (OSError, json.JSONDecodeError, KeyError,
                    AttributeError, TypeError) as e:
                log.debug("skipping unreadable run %s: %s", f, e)
                continue
    out.sort(key=lambda x: x["generated_at"] or "", reverse=True)
    return {"count": len(out), "runs": out}


@app.get("/api/report/{name}")
def report_detail(name: str):
    """Return a full run report JSON by filename (path-traversal safe)."""
    safe = Path(name).name  # strip any directory components
    if not safe.endswith(".json") or safe.startswith(".state-"):
        raise HTTPException(400, "invalid report name")
    target = (RUNS / safe).resolve()
    runs_root = RUNS.resolve()
    # ensure the resolved path stays inside the runs directory
    if runs_root not in target.parents or not target.is_file():
        raise HTTPException(404, "report not found")
    try:
        with open(target) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(500, f"could not read report: {e}") from e


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
async def stream_log(job_id: str):
    """SSE live tail of the given job's output (async: frees the event loop
    between polls instead of pinning a threadpool worker per open stream)."""
    if job_id not in JOBS:
        raise HTTPException(404, "unknown job")

    async def gen():
        idx = 0
        while True:
            with _LOCK:  # held only microseconds to snapshot the buffer
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
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/")
def index():
    return FileResponse(UI_DIR / "index.html")


app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")
