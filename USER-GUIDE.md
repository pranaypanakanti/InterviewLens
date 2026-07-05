# InterviewLens — User Guide

InterviewLens takes a **job description + your resume**, researches the web for the interview
questions actually asked at that company for that role, and gives you a prep sheet of
categorized question cards — each with an answer tailored to *your* resume and the names of
the sites that reported the question.

Everything runs on your machine. No API keys, no cloud LLMs, no accounts.

---

## Part 1 — One-time setup

### What you need

| Requirement | Notes |
|---|---|
| Windows 10/11 with Docker Desktop | WSL2 backend (the default). https://docker.com |
| Ollama installed **natively on Windows** | https://ollama.com — do NOT run it in Docker |
| ~8 GB free disk for models | 3B + 7B + embedding model |
| A GPU is optional but helps | Tuned for 4 GB VRAM (GTX 1650 class); CPU-only also works, just slower |

### Step 1 — Install Ollama and pull the models

Install Ollama from https://ollama.com (it runs as a tray app), then in any terminal:

```bash
ollama pull qwen2.5:3b-instruct-q4_K_M   # ~2.0 GB — extraction model
ollama pull qwen2.5:7b-instruct-q4_K_M   # ~4.7 GB — Quality-mode answers
ollama pull nomic-embed-text             # ~0.3 GB — question deduplication
```

Verify it's serving:

```bash
curl http://localhost:11434/api/tags
```

### Step 2 — Start the app

From the project root (this folder):

```bash
docker compose up --build -d
```

The first build takes a few minutes. Subsequent starts are just `docker compose up -d`.

### Step 3 — Open it

Go to **http://localhost:3000**. The badge in the top-right corner should say
**"all systems ready"**. If it doesn't, see Troubleshooting below.

To stop the app: `docker compose down` (your cached research runs survive in `./data/`).

---

## Part 2 — Using the app

### Running a research

1. **Type the job role** you're applying for (e.g. "Software Development Engineer II").
   This targets the web research and is used to filter out questions that aren't
   relevant to the role.
2. **Paste the job description** into the left panel. Include the company name —
   that's what drives the company-specific research.
3. **Drop your resume** (`.pdf`, `.docx`, or `.txt`) into the right panel.
4. **Pick a mode:**
   - **Fast (3B)** — results in ~5 minutes. Good for a first pass.
   - **Quality (7B)** — noticeably better, more nuanced answers; slower
     (the 7B model partially runs on CPU with 4 GB VRAM). Use it for the final prep.
5. Click **Research →** and watch the live checklist: parsing → extracting company/role →
   searching the web → reading sources → finding common questions → writing answers.
   A full run takes roughly 5–10 minutes depending on mode.

### Reading the results

- **Header** shows the detected company + role, question count, and sources read.
- **Category tabs** filter by Technical / Coding / System Design / Behavioral /
  Role-Specific / Domain.
- Each **question card** shows its category badge; click the card to expand the
  **tailored answer** (behavioral answers are STAR-structured around your actual
  projects), **why they ask this**, **tips**, and the names of the **sites that
  reported the question** (AmbitionBox, Reddit, GeeksforGeeks, …).
- **Amber banner?** It means there's little public interview data for that company.
  The questions are still real and relevant, but they're role/skill-based rather
  than company-reported.

### Exporting your prep sheet

- **⬇ Markdown** — downloads a `.md` file of the full sheet.
- **⬇ PDF** — opens the print dialog with a clean, fully-expanded sheet;
  choose "Save as PDF".

### Caching & re-runs

Runs are cached by (company, role, mode). Re-submitting the same inputs returns
instantly ("FROM CACHE" appears in the header). To force fresh research for a role you
already ran, the cache lives in `./data/app.db` — delete that file to clear everything,
or re-run after the posting changes (a different JD text re-triggers extraction).

### Good to know

- **Fast mode can occasionally misattribute a resume detail** in an answer (small-model
  trade-off). Skim answers before an interview; Quality mode is more reliable.
- The web search uses your own self-hosted SearXNG. If you fire many runs back-to-back,
  upstream engines may briefly rate-limit; wait a few minutes and re-run
  (`docker compose restart searxng` resets it immediately).

### Troubleshooting

| Symptom | Fix |
|---|---|
| Badge: "Ollama not running" | Start Ollama (tray app or `ollama serve`) |
| Badge: "models missing" | Run the three `ollama pull` commands from Step 1 |
| Badge: "search engine not ready" | `docker compose restart searxng`; check `docker compose logs searxng` |
| Few sources read | Glassdoor/LinkedIn block scraping — expected; community sources carry the weight |
| Quality mode very slow | Expected on 4 GB VRAM; use Fast for iteration |
| Everything else | `http://localhost:8000/api/health` shows exactly what's wrong; see also `setup.md` |

---

## Part 3 — Deploying it beyond your machine

The realistic paths, from cheapest up:

- **$0 — keep it on your PC, reach it from anywhere:** install Tailscale on your PC and
  your other devices, then open `http://<pc-tailscale-ip>:3000` from any network. No exposed
  ports, no server rental. (Cloudflare Tunnel + Access is the alternative if you want a real
  `https://` URL.) The recommended first step.
- **$0–9/mo — one small CPU VPS as an always-on service:** move the whole stack to a Linux
  VM (Oracle Cloud's free A1 tier or a Hetzner ARM box). On Linux, Ollama runs fine in
  Docker — add it as a compose service and point `OLLAMA_BASE_URL` at it. Put Caddy in
  front for HTTPS + basic-auth (the app has no login of its own), set
  `restart: unless-stopped` on all containers, and back up `./data/app.db` nightly.
- **Usage-based GPU:** if Quality mode is too slow on CPU, rent a GPU by the hour
  (RunPod/Vast.ai, ~$0.10–0.25/hr) only while you're actively prepping. Avoid a 24/7 GPU
  VM — worst value for a background-research workload like this one.

The cost-efficient strategy in one line: start with Tailscale (free, ten minutes), move to
a cheap ARM VPS only when "my PC must stay on" becomes annoying, and never pay for idle GPU.

### What never changes

Whatever the deployment, the app needs exactly three things reachable from the backend
container: **Ollama** (`OLLAMA_BASE_URL`), **SearXNG** (`SEARXNG_URL`, ships in the
compose file), and a writable **`./data`** volume. No keys, no external services.
