# Project Goal for Fablify — "InterviewLens": A Fully-Local Interview-Prep Research App

> **Hand this entire document to Fablify as the build goal.** It is written as an executable
> spec: constraints, architecture, exact models, per-component behavior, the docker-compose
> shape, phased milestones, and acceptance criteria. Do not skip the "Hard Constraints" or
> "Known Gotchas" sections — they encode real hardware limits of the target machine.

---

## 1. One-Sentence Objective

Build a desktop web app that takes **two inputs — a job description (JD) and a resume** — then
**researches the internet for the interview questions most commonly asked at that specific company
for that specific role**, and presents them in a clean UI as categorized question cards, each with a
**best-possible, resume-tailored answer** and source citations. Everything runs **locally** (models
on Ollama), launchable via **`docker compose up`**.

---

## 2. Hard Constraints (non-negotiable)

| Constraint | Detail |
|---|---|
| **Fully local inference** | All LLM/embedding inference runs on **Ollama** on the user's machine. No OpenAI/Anthropic/cloud LLM calls. |
| **Internet allowed only for *search*** | "Local" means models are local. The app still reaches the internet to *research* (via a self-hosted metasearch engine). No third-party paid search APIs (no Tavily/Serper/Exa keys). |
| **Docker-first** | Ship a `docker-compose.yml`. `docker compose up` brings up the whole stack; user opens a browser to a local port. |
| **Target hardware (measured — do NOT exceed)** | GPU: **NVIDIA GTX 1650, 4 GB VRAM** (Turing, compute 7.5, **no tensor cores → int8/q4 only**). Display runs on Intel iGPU, so ~3.9 GB VRAM is free for compute. CPU: **i5-12450H (8C/12T)**. RAM: **16 GB**. Disk: ~150 GB free. OS: **Windows 11**. |
| **No API keys anywhere** | The app must work with zero user-supplied secrets. |
| **Graceful degradation** | If a company has no public interview data, fall back to role- + skill-based generic questions and clearly label them as such. Never fabricate a source. |

---

## 3. Recommended Tech Stack (use unless you have a strong reason not to)

| Layer | Choice | Why |
|---|---|---|
| **LLM runtime** | **Ollama**, running **natively on the Windows host** (not inside Docker) | Docker GPU passthrough on Windows/WSL2 is fragile on a GTX 1650. Native Ollama uses the GPU directly with zero container-runtime friction; Dockerized backend reaches it via `host.docker.internal:11434`. Measured perf is within ~5% of any Dockerized GPU path. |
| **Extraction / routing model** | `qwen2.5:3b-instruct-q4_K_M` (~2.2 GB) | Strong structured-JSON output at 3B; fits 100% on the 4 GB GPU with `num_ctx: 4096`. Used for entity extraction and question extraction. |
| **Answer-generation model** | `qwen2.5:7b-instruct-q4_K_M` (~4.7 GB) **on CPU/partial-offload**, OR `qwen2.5:3b` for speed | Answers are quality-critical but not latency-critical. 7B gives noticeably better answers; it will partially spill to CPU on 4 GB VRAM — acceptable. Expose a **Fast (3B) / Quality (7B)** toggle. |
| **Embeddings** | `nomic-embed-text` (~275 MB) | For deduping/clustering near-identical questions across sources. |
| **Web search** | **SearXNG** (self-hosted metasearch), Dockerized, JSON API | Aggregates Google/Bing/DuckDuckGo/etc., no API key, returns `{title,url,content}` via `/search?q=...&format=json`. This is the "research the internet" engine. |
| **Page fetch + clean-text extraction** | `httpx` (async) + **`trafilatura`** | Fetch top result URLs and strip to clean article text for the LLM. |
| **Resume parsing** | **PyMuPDF (`fitz`)** for PDF, `python-docx` for DOCX | Robust text extraction. |
| **Backend** | **FastAPI + Uvicorn** (Python 3.12), async | Long-running research jobs; stream progress over **SSE**. |
| **Job state / cache** | **SQLite** | Cache research runs keyed by `(company, role)` so re-runs are instant; store questions/answers/sources. |
| **Frontend** | **React + Vite + TailwindCSS** | Progress view + results view; served by nginx in its own container. |
| **Export** | Client-side PDF (e.g. `react-to-print`) and Markdown download | Let the user save their prep sheet. |

---

## 4. Architecture

```
                    ┌──────────────────────────────────────────────┐
   Browser ───────► │  frontend (nginx + React build)  :3000       │
   localhost:3000   └───────────────┬──────────────────────────────┘
                                    │ REST + SSE
                    ┌───────────────▼──────────────────────────────┐
                    │  backend (FastAPI/uvicorn)       :8000        │
                    │  pipeline: parse → extract → search →         │
                    │  fetch → question-extract → cluster →         │
                    │  answer-generate → store                      │
                    └───┬───────────────┬───────────────┬──────────┘
                        │               │               │
              (host.docker.internal)    │ HTTP          │ SQLite file (volume)
                        │               │               │
        ┌───────────────▼──┐   ┌────────▼─────────┐   ┌─▼──────────┐
        │ Ollama (NATIVE   │   │ searxng  :8080   │   │  ./data/   │
        │ on Windows host) │   │ (Docker)         │   │  app.db    │
        │ :11434           │   │ + redis (cache)  │   └────────────┘
        └──────────────────┘   └──────────────────┘
```

**Containers in docker-compose:** `frontend`, `backend`, `searxng`, `redis` (SearXNG's cache).
**On the host (not in compose):** Ollama, installed via the native Windows installer.

> Provide a `README` + a `preflight` check in the backend that pings `host.docker.internal:11434`
> on startup and prints a clear message if Ollama isn't running / models aren't pulled.

---

## 5. The Pipeline (build this as discrete, testable steps)

**Input:** JD text (pasted or `.txt`) + resume file (`.pdf`/`.docx`).

1. **Parse inputs.** Extract resume text (PyMuPDF/python-docx). Keep JD text as-is.
2. **Extract entities (LLM, 3B, JSON mode).** From the JD, extract: `company`, `job_title`, `seniority`,
   `key_skills[]`, `location`, `domain`. From the resume, extract: `candidate_skills[]`,
   `years_experience`, `notable_projects[]`. Return strict JSON.
3. **Generate search queries.** Build a targeted set, e.g.:
   - `"{company}" "{job_title}" interview questions`
   - `{company} {job_title} interview experience` (let SearXNG surface Blind/Reddit/AmbitionBox/GfG)
   - `{company} interview questions site:teamblind.com`
   - `{company} {job_title} interview site:reddit.com`
   - `{company} interview questions site:ambitionbox.com`  ← strong for India-based roles
   - `{company} interview questions site:glassdoor.com`  ← often blocked; keep, but expect to skip
   - Skill fallbacks: `{skill} interview questions {seniority} {job_title}` for each top skill
4. **Search via SearXNG.** Call `/search?q=...&format=json&categories=general` per query.
   Collect top ~8 results each; dedupe URLs; keep `title`, `url`, `content` (snippet).
5. **Fetch + extract.** Async-fetch each unique URL with a realistic User-Agent + timeout + concurrency
   limit; run `trafilatura` to get clean text. **On block/403/timeout → skip that source silently**
   (this WILL happen for Glassdoor/LinkedIn; the snippet still counts as weak evidence).
6. **Extract questions (LLM, 3B, JSON).** Per document, prompt the model to pull out *actual interview
   questions* with: `question`, `category` ∈ {technical, coding, system-design, behavioral,
   role-specific, domain-knowledge}, `source_url`, `confidence`. Ignore marketing fluff.
7. **Dedupe + rank (embeddings).** Embed questions with `nomic-embed-text`; cluster near-duplicates
   (cosine ≥ ~0.85); each cluster's `frequency` = number of distinct source domains mentioning it.
   Rank by frequency, then confidence. Keep the top ~25–40.
8. **Generate answers (LLM, 7B Quality / 3B Fast).** For each ranked question, generate a
   **best-possible answer tailored to the resume**:
   - Behavioral → **STAR-structured**, drawing on the candidate's real projects from the resume.
   - Technical/coding/system-design → correct, concise model answer + "how to approach it out loud."
   - Include `why_asked` (1 line) and `tips` (1–2 lines).
   - Attach the source URLs from the cluster.
9. **Store + return.** Persist the whole run in SQLite keyed by `(company, job_title)`; stream
   progress to the UI throughout (see SSE below).

---

## 6. Backend API (FastAPI)

- `POST /api/analyze` — multipart: `jd_text`, `resume_file`. Returns a `job_id`. Kicks off the async pipeline.
- `GET  /api/jobs/{job_id}/events` — **SSE stream** of progress events:
  `{stage, message, pct, partial_counts}` (e.g. "Searching Blind… 3/12 queries", "Extracting questions… 41 found").
- `GET  /api/jobs/{job_id}/result` — final structured result (categorized questions + answers + sources).
- `GET  /api/health` — reports Ollama reachability, which models are present, SearXNG reachability.

Research is slow (tens of seconds to a few minutes). **The UI must show live progress**, not a spinner.

---

## 7. Frontend (React + Vite + Tailwind)

- **Landing:** two-panel input — JD textarea + resume drag-and-drop; a **Fast/Quality** toggle; "Research" button.
- **Progress view:** a live checklist driven by the SSE stream (Parsing → Extracting company/role →
  Searching the web → Reading sources → Finding common questions → Writing answers), with running counts.
- **Results view:**
  - Header: detected **company + role**, number of questions, number of sources read.
  - **Category tabs** (Technical / Coding / System Design / Behavioral / Role-Specific / Domain).
  - **Question cards:** question text, a **frequency badge** ("seen in 4 sources"), expandable to reveal
    the tailored answer, `why_asked`, `tips`, and clickable **source links**.
  - **Export** buttons: download as PDF and as Markdown.
  - A clear banner when data is thin: *"Limited public data for this company — showing role- and
    skill-based questions."*
- Clean, calm, single-accent design. Mobile-responsive is a plus, not required.

---

## 8. docker-compose shape (target)

```yaml
services:
  frontend:
    build: ./frontend
    ports: ["3000:80"]
    depends_on: [backend]

  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
      - SEARXNG_URL=http://searxng:8080
      - EXTRACT_MODEL=qwen2.5:3b-instruct-q4_K_M
      - ANSWER_MODEL=qwen2.5:7b-instruct-q4_K_M
      - EMBED_MODEL=nomic-embed-text
      - NUM_CTX=4096
    volumes: ["./data:/app/data"]
    extra_hosts: ["host.docker.internal:host-gateway"]   # so Linux container reaches host Ollama
    depends_on: [searxng]

  searxng:
    image: searxng/searxng:latest
    volumes: ["./searxng:/etc/searxng"]
    environment:
      - SEARXNG_BASE_URL=http://localhost:8080/
    depends_on: [redis]

  redis:
    image: redis:alpine
```

> **SearXNG config note:** in `./searxng/settings.yml`, the JSON API is **disabled by default** —
> you MUST add `json` to `search.formats` and set a `server.secret_key`. Also relax the rate limiter
> for localhost. Bake a working `settings.yml` into the repo.

---

## 9. Phased Milestones (build + verify in this order)

- **P0 — Scaffold & connectivity.** Repo layout, docker-compose, SearXNG up with JSON enabled,
  backend `/api/health` confirms Ollama + models + SearXNG all reachable. Ship a `setup.md` telling
  the user to install native Ollama and run `ollama pull` for the three models.
- **P1 — Input parsing.** Upload resume + JD → return extracted plain text. Verify on a real PDF.
- **P2 — Entity extraction.** JD/resume → structured JSON (company, role, skills). Verify JSON is strict.
- **P3 — Search + fetch + extract.** Query generation → SearXNG → fetch → trafilatura clean text.
  Verify it survives blocked sources (Glassdoor) without crashing.
- **P4 — Question extraction + clustering.** Docs → deduped, frequency-ranked question list.
- **P5 — Answer generation.** Ranked questions → resume-tailored answers with sources. Fast/Quality toggle.
- **P6 — UI.** Full flow in the browser with live SSE progress and the results view.
- **P7 — Cache, export, polish.** SQLite caching by (company, role), PDF/Markdown export, empty-data banner,
  error states, README with a one-command run.

Each phase must be independently runnable and verified against a **real JD + real resume** before moving on.

---

## 10. Acceptance Criteria (definition of done)

1. `docker compose up` + native Ollama running → app reachable at `http://localhost:3000`.
2. Given a real JD (name a well-known company) + a real resume, the app returns **≥ 20 categorized
   questions**, each with a tailored answer and **at least one real source URL**.
3. Live progress is visible throughout; no blind spinner.
4. **Zero** cloud LLM calls and **zero** API keys required (verifiable from code + network).
5. Blocked/unreachable sources degrade gracefully; a low-data company yields labeled fallback questions.
6. Re-running the same (company, role) returns from cache in < 2 seconds.
7. Runs within the 4 GB VRAM budget (no OOM) using the specified models/quantization.
8. User can export the prep sheet to PDF and Markdown.

---

## 11. Known Gotchas (pre-solved — honor these)

1. **Ollama on GPU inside Docker on Windows is unreliable.** Run Ollama **natively on the host**; the
   backend connects via `http://host.docker.internal:11434` with `extra_hosts: host-gateway`. Do not
   try to put Ollama in the compose file with `--gpus all` on this machine.
2. **4 GB VRAM budget.** Only int8/q4 quantized models. Keep `num_ctx` at 2048–4096 (default 8k will
   spill to CPU). Don't assume the 7B answer model fits fully on GPU — expect partial CPU offload and
   size timeouts accordingly. Don't hold 7B + embeddings on GPU simultaneously.
3. **SearXNG JSON is off by default.** Enable `formats: [html, json]` and set a `secret_key`, or every
   API call returns 403.
4. **Glassdoor / LinkedIn will block scraping** (Cloudflare, login walls). Rely on SearXNG *snippets*
   plus scrapeable community sources (**Blind, Reddit, AmbitionBox, GeeksforGeeks, InterviewBit**).
   Respect robots.txt, set a real User-Agent, rate-limit, and skip-on-block. Never fabricate a source URL.
5. **Research is slow.** Parallelize fetches (bounded concurrency ~5), stream progress over SSE, and
   cache aggressively in SQLite.
6. **Cold-start latency.** Set Ollama `keep_alive` (e.g. `"30m"`) on requests so the model isn't
   reloaded between pipeline stages.
7. **Structured output.** Use Ollama's `format: json` / JSON-schema-constrained output for the
   extraction stages so parsing never breaks.
8. **AmbitionBox is the strongest source for India-based companies/roles** — weight it in query generation.

---

## 12. First Command the User Runs (put in README)

```bash
# 1. Install Ollama natively on Windows (https://ollama.com), then:
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull nomic-embed-text

# 2. From the project root:
docker compose up --build

# 3. Open http://localhost:3000
```

---

### Deliverables Fablify must produce
A single git repo containing: `frontend/`, `backend/`, `searxng/settings.yml`, `docker-compose.yml`,
a working `README.md` (with the commands above and the native-Ollama note), and a `setup.md`.
The app must satisfy every item in **Section 10**.
