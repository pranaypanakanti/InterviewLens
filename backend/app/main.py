"""InterviewLens backend — FastAPI app with SSE progress streaming."""
import asyncio
import json
import logging

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import db
from .jobs import jobs
from .pipeline import run_pipeline
from .services import searxng
from .services.ollama import ollama

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("interviewlens")

app = FastAPI(title="InterviewLens", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def preflight():
    db.init_db()
    health = await ollama.health()
    if not health["reachable"]:
        log.warning("=" * 70)
        log.warning("Ollama is NOT reachable at %s", ollama.base_url)
        log.warning("Install Ollama natively on the host (https://ollama.com) and start it.")
        log.warning("=" * 70)
    else:
        missing = [m["name"] for m in health["models"].values() if not m["present"]]
        if missing:
            log.warning("Ollama is up but models are missing. Run:")
            for m in missing:
                log.warning("  ollama pull %s", m)
        else:
            log.info("Ollama OK — all required models present.")
    sx = await searxng.health()
    if not sx.get("json_api"):
        log.warning("SearXNG problem: %s", sx.get("error", "unreachable"))
    else:
        log.info("SearXNG OK — JSON API enabled.")


@app.get("/api/health")
async def health():
    return {
        "ollama": await ollama.health(),
        "searxng": await searxng.health(),
    }


@app.post("/api/analyze")
async def analyze(
    jd_text: str = Form(...),
    resume_file: UploadFile = None,
    mode: str = Form("quality"),
    force: bool = Form(False),
):
    if not jd_text or len(jd_text.strip()) < 40:
        raise HTTPException(422, "Job description is too short — paste the full JD.")
    if resume_file is None:
        raise HTTPException(422, "A resume file (.pdf/.docx/.txt) is required.")
    if mode not in ("fast", "quality"):
        raise HTTPException(422, "mode must be 'fast' or 'quality'")
    resume_bytes = await resume_file.read()
    if len(resume_bytes) > 10 * 1024 * 1024:
        raise HTTPException(422, "Resume file is too large (max 10 MB).")

    job = jobs.create()
    asyncio.create_task(
        run_pipeline(job, jd_text, resume_file.filename or "", resume_bytes, mode, force)
    )
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job id")

    async def stream():
        queue = job.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield f"data: {json.dumps(event)}\n\n"
                if event["stage"] in ("done", "error"):
                    break
        finally:
            job.unsubscribe(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/jobs/{job_id}/result")
async def job_result(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job id")
    if job.status == "running":
        return {"status": "running"}
    if job.status == "error":
        last = job.events[-1] if job.events else {}
        return {"status": "error", "message": last.get("message", "Unknown error")}
    return {"status": "done", "result": job.result}
