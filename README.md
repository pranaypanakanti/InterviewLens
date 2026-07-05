# InterviewLens

An interview-prep research app. Give it a **job description + your resume**; it researches the
web for the interview questions most commonly reported for that company and role, and builds a
prep sheet of categorized question cards — each with an answer tailored to *your* resume.

- **LLM inference runs on your own machine** via [Ollama](https://ollama.com) — no cloud LLM APIs, no API keys, no accounts.
- The internet is used **only for web search**, through a self-hosted [SearXNG](https://github.com/searxng/searxng) metasearch instance.
- One command to run: `docker compose up`.

📖 **Docs:** [User Guide](USER-GUIDE.md) (setup & usage) · [setup.md](setup.md) (install troubleshooting)

## Features

- **Company-specific research** — searches community sources (AmbitionBox, GeeksforGeeks, Reddit, Blind, InterviewBit, …) for questions actually reported for the target company and role.
- **Resume-tailored answers** — every question comes with a draft answer built around your projects and experience; behavioral answers are STAR-structured.
- **Categorized prep sheet** — Technical / Coding / System Design / Behavioral / Role-Specific / Domain tabs.
- **Two quality modes** — Fast (3B model) for iteration, Quality (7B model) for the final prep.
- **Live progress** — the research pipeline streams its progress over SSE (parsing → searching → reading → clustering → answering); no blind spinner.
- **Honest degradation** — blocked sites are skipped; if a company has little public interview data, the app tops up with role/skill-based questions and says so with a banner. It never fabricates sources.
- **Caching** — runs are cached in SQLite by (company, role, mode); repeating a search returns in under 2 seconds.
- **Export** — download the sheet as Markdown, or as PDF via a print-optimized layout.

## Architecture

```
                       ┌────────────────────────── Docker ──────────────────────────┐
  Browser ──────────►  │  frontend (nginx + React)  :3000                           │
                       │        │  /api (proxy, SSE-safe)                           │
                       │        ▼                                                   │
                       │  backend (FastAPI)  :8000 ──────► searxng ◄──── redis      │
                       │        │                     (metasearch JSON API)         │
                       └────────┼───────────────────────────────────────────────────┘
                                ▼
                       Ollama (native on host)  :11434
                       qwen2.5 3B / 7B + nomic-embed-text
```

### The research pipeline

```
JD + resume ──► parse (PyMuPDF / python-docx)
            ──► extract entities — company, role, skills (3B LLM, JSON-schema-constrained)
            ──► generate search queries (company-specific + skill fallbacks)
            ──► SearXNG metasearch (self-hosted, JSON API)
            ──► fetch pages (httpx + trafilatura; robots.txt-aware, skip-on-block)
            ──► extract interview questions per source (3B LLM, JSON)
            ──► dedupe/cluster via embeddings (nomic-embed-text, cosine similarity)
            ──► rank by cross-source frequency; top up with labeled generic questions if thin
            ──► write resume-tailored answers (7B Quality / 3B Fast)
            ──► store in SQLite, stream progress via SSE throughout
```

Design decisions worth knowing:

- **JSON-schema-constrained generation.** Every LLM call passes a JSON schema through Ollama's
  `format` parameter, so small models return parseable, well-typed output.
- **Company-mention verification.** A source only counts as *company-reported* evidence if its
  text actually names the company — search engines return fuzzy matches, so query origin alone
  is not trusted. Fewer than 8 company-reported questions triggers the "limited data" banner.
- **Snippet fallback.** Sites that block scraping (Glassdoor, LinkedIn) still contribute their
  search-result snippets as weak evidence instead of being lost entirely.
- **Two-tier cache.** Entity extraction is cached by a hash of the inputs; full results are
  cached by (company, role, mode). Both live in one SQLite file under `./data/`.

## Tech stack

| Layer | Technology | Why |
|---|---|---|
| LLM inference | Ollama (native host) · qwen2.5 3B & 7B q4, nomic-embed-text | Local, free, fits a 4 GB GPU |
| Backend | Python 3.12 · FastAPI · httpx · trafilatura · PyMuPDF | Async pipeline + SSE streaming |
| Search | SearXNG (self-hosted) + Valkey/Redis cache | Metasearch across engines, no API keys |
| Storage | SQLite (single file volume) | Zero-ops caching |
| Frontend | React 18 · Vite · Tailwind CSS, served by nginx | Single-page state machine: input → progress → results |
| Orchestration | Docker Compose (4 services) | One-command startup |

## Project structure

```
backend/app/
  main.py            # FastAPI routes: /api/analyze, /api/jobs/{id}/events (SSE), /api/health
  pipeline.py        # The end-to-end research pipeline
  jobs.py            # In-memory job manager + SSE event history
  db.py              # SQLite cache (entities + results)
  services/
    ollama.py        # Ollama client: schema-constrained chat, embeddings, health
    searxng.py       # SearXNG JSON API client
    fetcher.py       # Concurrent page fetching, robots.txt, clean-text extraction
    extraction.py    # LLM prompts + JSON schemas (entities, questions, generics)
    clustering.py    # Embedding-based dedupe + frequency ranking
    answers.py       # Tailored answer generation
    parsing.py       # Resume parsing (PDF / DOCX / TXT)
frontend/src/        # React app (App, InputPanel, ProgressView, ResultsView, QuestionCard)
searxng/settings.yml # SearXNG config (JSON API enabled, engine resilience tuning)
docker-compose.yml   # frontend + backend + searxng + redis
```

## Quick start

```bash
# 1. Install Ollama (https://ollama.com), then pull the models:
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull nomic-embed-text

# 2. From the project root:
docker compose up --build

# 3. Open http://localhost:3000  — the header badge should say "all systems ready"
```

> **On Windows, Ollama must run natively on the host, not in Docker** — GPU passthrough for
> consumer GPUs under WSL2 is unreliable. The backend container reaches host Ollama via
> `host.docker.internal:11434`. On Linux servers, Ollama in Docker is fine —
> point `OLLAMA_BASE_URL` at the container instead.

## Configuration

All configuration is environment variables on the `backend` service in `docker-compose.yml`:

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Where Ollama listens |
| `SEARXNG_URL` | `http://searxng:8080` | Self-hosted search endpoint |
| `EXTRACT_MODEL` | `qwen2.5:3b-instruct-q4_K_M` | Entity/question extraction |
| `ANSWER_MODEL` | `qwen2.5:7b-instruct-q4_K_M` | Quality-mode answers |
| `EMBED_MODEL` | `nomic-embed-text` | Question clustering |
| `NUM_CTX` | `4096` | Context window (tuned for 4 GB VRAM) |

`GET /api/health` reports Ollama reachability, pulled models, and SearXNG status — the UI shows
the same as a header badge.

## License

[MIT](LICENSE)
