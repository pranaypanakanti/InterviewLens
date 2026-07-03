# InterviewLens — Setup

## Prerequisites

1. **Docker Desktop** for Windows (WSL2 backend) — https://docker.com
2. **Ollama** installed **natively on Windows** (NOT in Docker) — https://ollama.com

## Step 1 — Install Ollama and pull the models

Download and run the Ollama Windows installer, then in a terminal:

```bash
ollama pull qwen2.5:3b-instruct-q4_K_M   # ~2.0 GB — entity + question extraction
ollama pull qwen2.5:7b-instruct-q4_K_M   # ~4.7 GB — Quality-mode answers
ollama pull nomic-embed-text             # ~0.3 GB — question dedupe/clustering
```

Verify Ollama is serving:

```bash
curl http://localhost:11434/api/tags
```

> **Why native, not Docker?** On this hardware (GTX 1650, Windows 11), GPU passthrough into
> Docker/WSL2 is fragile. Native Ollama uses the GPU directly; the Dockerized backend reaches it
> at `http://host.docker.internal:11434`.

## Step 2 — Start the stack

From the project root:

```bash
docker compose up --build
```

First build takes a few minutes (npm + pip installs). Then open **http://localhost:3000**.

## Step 3 — Verify

- The header badge should read **"all systems ready"**.
- Or check `http://localhost:8000/api/health` — it reports:
  - `ollama.reachable` and which of the three models are present,
  - `searxng.json_api` (must be `true`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Badge says "Ollama not running" | Start Ollama (it runs as a tray app / `ollama serve`). |
| Badge says "models missing" | Run the three `ollama pull` commands above. |
| `searxng.json_api: false` / 403s | `searxng/settings.yml` must include `json` under `search.formats` (already committed — don't remove it). |
| Research finds few sources | Glassdoor/LinkedIn block scraping — expected. Snippets still count. Community sources (AmbitionBox, Reddit, GeeksforGeeks) carry most weight. |
| Answers are slow in Quality mode | Expected: the 7B model partially runs on CPU with 4 GB VRAM. Use **Fast** mode for iteration. |
| Out-of-memory / GPU spill | Keep `NUM_CTX=4096` (or lower to 2048) in `docker-compose.yml`. |

## Notes on privacy & keys

- No API keys anywhere; nothing to configure.
- The only outbound traffic is web search/fetch (SearXNG + page fetches). All LLM calls stay on
  `localhost:11434`.
