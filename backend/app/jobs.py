"""In-memory job registry with SSE fan-out (history replay + live events)."""
import asyncio
import time
import uuid


class Job:
    def __init__(self):
        self.id = uuid.uuid4().hex[:12]
        self.status = "running"  # running | done | error
        self.events: list[dict] = []
        self.result: dict | None = None
        self.subscribers: list[asyncio.Queue] = []
        self.created_at = time.time()

    async def publish(self, stage: str, message: str, pct: int, **extra):
        event = {"stage": stage, "message": message, "pct": pct, **extra}
        self.events.append(event)
        for q in list(self.subscribers):
            await q.put(event)

    async def finish(self, result: dict):
        self.status = "done"
        self.result = result
        await self.publish("done", "Research complete", 100)

    async def fail(self, message: str):
        self.status = "error"
        await self.publish("error", message, 100)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        for e in self.events:  # replay history for late joiners
            q.put_nowait(e)
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self.subscribers:
            self.subscribers.remove(q)


class JobManager:
    def __init__(self):
        self.jobs: dict[str, Job] = {}

    def create(self) -> Job:
        job = Job()
        self.jobs[job.id] = job
        self._prune()
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def _prune(self, max_age_s: int = 6 * 3600):
        cutoff = time.time() - max_age_s
        for jid in [j for j, job in self.jobs.items() if job.created_at < cutoff and job.status != "running"]:
            del self.jobs[jid]


jobs = JobManager()
