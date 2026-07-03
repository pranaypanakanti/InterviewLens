# InterviewLens

A **fully-local** interview-prep research app. Give it a job description and your resume; it
researches the web for the interview questions most commonly asked at that company for that role,
and presents categorized question cards — each with a resume-tailored answer and real source links.

- **All LLM inference is local** (Ollama on your machine). Zero cloud LLM calls, zero API keys.
- Internet is used **only for search**, via a self-hosted [SearXNG](https://github.com/searxng/searxng) metasearch engine.
- One command to run: `docker compose up`.

## Quick start

```bash
# 1. Install Ollama natively on Windows (https://ollama.com), then pull the models:
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull nomic-embed-text

# 2. From the project root:
docker compose up --build

# 3. Open http://localhost:3000
```

> **Ollama must run natively on the host, not in Docker.** GPU passthrough for a GTX 1650 on
> Windows/WSL2 is unreliable; the backend container reaches host Ollama via
> `host.docker.internal:11434`. See [setup.md](setup.md) for details and troubleshooting.

## How it works

```
JD + resume ──► parse ──► extract entities (3B LLM, JSON)
            ──► generate search queries ──► SearXNG (self-hosted metasearch)
            ──► fetch pages (httpx + trafilatura, skip-on-block)
            ──► extract interview questions per source (3B LLM, JSON)
            ──► dedupe/cluster via embeddings (nomic-embed-text), rank by source frequency
            ──► write resume-tailored answers (7B Quality / 3B Fast)
            ──► cache in SQLite, stream progress over SSE
```

- **Fast (3B) / Quality (7B)** toggle: answers are quality-critical but not latency-critical.
  The 7B model partially offloads to CPU on a 4 GB GPU — slower, noticeably better.
- **Graceful degradation:** blocked sources (Glassdoor, LinkedIn) are skipped silently; their
  search snippets still count as weak evidence. If a company has little public interview data,
  the app tops up with role/skill-based questions clearly labeled *generic* — it never fabricates
  a source.
- **Caching:** runs are cached in SQLite by (company, role, mode); re-running the same inputs
  returns in under 2 seconds.
- **Export:** download your prep sheet as Markdown or PDF (print dialog).

## Services

| Service    | Where           | Port | Purpose                                |
|------------|-----------------|------|----------------------------------------|
| frontend   | Docker (nginx)  | 3000 | React UI, proxies `/api` to backend     |
| backend    | Docker          | 8000 | FastAPI pipeline + SSE progress         |
| searxng    | Docker          | —    | Self-hosted metasearch (JSON API)       |
| redis      | Docker          | —    | SearXNG cache                           |
| **Ollama** | **Native host** | 11434| Local LLM + embedding inference         |

## Health check

`http://localhost:8000/api/health` reports Ollama reachability, which models are pulled, and
SearXNG JSON-API status. The UI shows the same as a badge in the header.

## Hardware target

Tuned for: NVIDIA GTX 1650 (4 GB VRAM), i5-12450H, 16 GB RAM, Windows 11.
Only q4-quantized models; `num_ctx=4096`; the 3B extract model fits fully on GPU, the 7B answer
model partially offloads to CPU (expected and fine).
