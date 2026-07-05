# InterviewLens — Cloud Deployment Guide

How to move InterviewLens off your PC and run it as an always-on service, with a focus on
**cost efficiency**. Read the decision guide first — the cheapest correct answer depends on
how you actually use the app.

## What the app needs, wherever it runs

The backend container needs exactly three things reachable:

1. **Ollama** — `OLLAMA_BASE_URL` (the only heavy component; needs RAM/GPU)
2. **SearXNG** — `SEARXNG_URL` (ships in the compose file, negligible resources)
3. **A writable `./data` volume** — the SQLite cache (back this up; it's the only state)

No API keys, no managed databases, no external services. That's what makes cheap deployment
possible: everything fits on **one machine**.

## Decision guide

| Your situation | Best option | Monthly cost |
|---|---|---|
| Personal use, PC is usually on | **Option A: Tailscale to your PC** | **$0** |
| Personal use, want it always-on off your PC | **Option B: free/cheap CPU VPS** | **$0–9** |
| Few users, Quality mode must be fast | Option C: on-demand GPU | ~$5–30 (usage-based) |
| Real multi-user product | Option D: re-architect first | $50+ |

The single most cost-efficient strategy for a personal tool: **Option A now, Option B when
"my PC must be on" becomes annoying.** Skip GPUs until CPU inference speed actually bothers you —
this app is research-style, not chat-style; a 10-minute background run is acceptable.

---

## Option A — $0: keep it on your PC, reach it from anywhere

Your PC already runs the whole stack. Add a private tunnel so your phone/laptop can reach it
from any network. No server, no exposed ports, no code changes.

**With Tailscale (recommended, ~10 minutes):**

1. Install Tailscale on your PC and on the devices you'll use — https://tailscale.com (free for personal use).
2. Sign both into the same tailnet.
3. Open `http://<your-pc-tailscale-ip>:3000` from anywhere. Done.

**With Cloudflare Tunnel** (if you want a real `https://…` URL): run `cloudflared` on your PC
pointing at `localhost:3000`, and put **Cloudflare Access** (free tier) in front for login.

Good practices for this option:

- Set Docker Desktop and Ollama to start on boot; set `restart: unless-stopped` on all
  compose services (see the service section below).
- Don't port-forward 3000 on your router — the tunnel is the whole point. The app has no
  built-in authentication.

**Limits:** your PC must be on. Sleep/hibernate kills it. If that's fine, stop here — this is
unbeatable on cost.

---

## Option B — $0–9/month: one small CPU VPS, running as a real service

Move the whole stack (including Ollama, in Docker — the Windows "native only" rule doesn't
apply on Linux servers) to a single Linux VM.

### B1. Sizing and providers (cost-efficiency is decided here)

CPU-only inference works for this app. Realistic minimums:

- **3B model (Fast mode):** 4 vCPU / 8 GB RAM — perfectly usable
- **7B model (Quality mode):** 8 GB RAM minimum, 16 GB comfortable; slow (~2–5 tok/s) but fine
  for a background research job

| Provider | Machine | Price | Notes |
|---|---|---|---|
| **Oracle Cloud Free Tier** | Ampere A1: 4 ARM cores, 24 GB RAM | **$0 forever** | Best value in existence; qwen2.5 has ARM builds via Ollama. Capacity in popular regions can take a few tries to grab. |
| **Hetzner** | CAX21 (4 ARM cores, 8 GB) / CAX31 (8 cores, 16 GB) | ~€4 / €8 | Cheapest reliable paid option |
| Contabo | 6 vCPU, 12 GB | ~€6 | Cheap, variable performance |
| DigitalOcean/Vultr | 4 vCPU, 8 GB | ~$24+ | Only if you're already there |

**Recommended:** try Oracle's free A1 first; fall back to Hetzner CAX31. Both are ARM —
Ollama and all images used here (nginx, python, searxng, valkey) publish arm64 builds; the
frontend/backend Dockerfiles build natively on ARM.

### B2. Step-by-step

```bash
# 1. Provision Ubuntu 24.04, SSH in. Immediately:
sudo apt update && sudo apt -y upgrade
sudo ufw allow OpenSSH && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable

# 2. Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # re-login after this

# 3. Get the code
git clone https://github.com/pranaypanakanti/InterviewLens.git
cd InterviewLens
```

**4. Add Ollama as a container.** Create `docker-compose.cloud.yml` next to the main compose file:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama-models:/root/.ollama
    restart: unless-stopped
    # If the VM has an NVIDIA GPU, uncomment:
    # deploy:
    #   resources:
    #     reservations:
    #       devices: [{ driver: nvidia, count: all, capabilities: [gpu] }]

  backend:
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434   # instead of host.docker.internal
    depends_on:
      - ollama

  frontend:
    ports: !override
      - "127.0.0.1:3000:80"   # localhost only — Caddy fronts it (step 6)

volumes:
  ollama-models:
```

```bash
# 5. Start everything and pull the models (one-time, ~7 GB)
docker compose -f docker-compose.yml -f docker-compose.cloud.yml up -d --build
docker compose exec ollama ollama pull qwen2.5:3b-instruct-q4_K_M
docker compose exec ollama ollama pull qwen2.5:7b-instruct-q4_K_M
docker compose exec ollama ollama pull nomic-embed-text
```

**6. Put HTTPS + a login in front.** The app has no auth — never expose port 3000 raw.
Caddy is the least-effort choice (automatic HTTPS certificates):

```bash
sudo apt install -y caddy
caddy hash-password   # enter a password, copy the hash
```

`/etc/caddy/Caddyfile` (point a DNS A-record of your (sub)domain at the VM first):

```
prep.yourdomain.com {
    basic_auth {
        you <paste-the-hash-here>
    }
    reverse_proxy 127.0.0.1:3000 {
        flush_interval -1   # required: keeps SSE progress streaming, unbuffered
    }
}
```

```bash
sudo systemctl reload caddy
```

No domain? Skip Caddy entirely and install **Tailscale on the VM** — private access,
zero attack surface, still $0.

### B3. Running as a service (survives reboots, restarts on crash)

- Every service in both compose files should have `restart: unless-stopped` (the cloud
  override above sets it for ollama; add it to the four services in `docker-compose.yml`).
- Docker's daemon starts on boot by default on Ubuntu — with those restart policies, the
  whole stack self-heals after a reboot or crash. Verify: `sudo reboot`, wait, reload the page.
- **Back up the state**: `./data/app.db` is everything. A nightly cron is plenty:

```bash
crontab -e
# 0 3 * * * cp ~/InterviewLens/data/app.db ~/backups/app-$(date +\%u).db
```

- **Updates**: `git pull && docker compose -f docker-compose.yml -f docker-compose.cloud.yml up -d --build`.
  Don't run auto-updaters (Watchtower) on a stack with pinned model behavior.

---

## Option C — GPU, only when speed actually hurts

CPU Quality-mode runs take tens of minutes. If that becomes a real problem, **don't rent a
24/7 GPU box** (a persistent T4/RTX VM is $150–300/month — wildly inefficient for occasional use).
Cost-efficient GPU patterns, in order:

1. **Marketplace GPU by the hour** — RunPod / Vast.ai, RTX 3060/4000-class at ~$0.10–0.25/hr.
   Run the whole stack there only while you're actively prepping (a few evenings before an
   interview ≈ **$1–3 total**), keep `./data/app.db` synced off-box, destroy the pod after.
2. **Split deployment** — keep Option B's cheap CPU VPS for frontend/backend/searxng, and point
   `OLLAMA_BASE_URL` at a GPU pod's Ollama endpoint only when it's up. Ollama on the pod should
   listen on a private network (Tailscale between VPS and pod) — never a public unauthenticated port.
3. **Serverless GPU (Modal / RunPod Serverless)** — pay per second of inference, scale-to-zero.
   Most cost-efficient at very low usage, but requires replacing the Ollama client with their
   endpoint format — a small code change; only worth it if 1–2 don't fit.

## Option D — if it ever becomes a multi-user product

The current design assumes one trusted user: no auth, a shared cache, in-memory job state, and
one inference queue. Before real users, you'd add: authentication (per-user data), Postgres
instead of SQLite, a proper job queue (one GPU worker pulling jobs), and rate limiting (every
run costs minutes of compute — that's your cost exposure, not bandwidth). Container hosting for
frontend/backend is trivial (Fly.io, Cloud Run); the LLM stays the expensive part — at that
scale, benchmark a hosted open-model API against your own GPU box before committing.

---

## Good practices checklist (any option)

- [ ] **Never expose the app without auth** — Caddy basic-auth minimum, Tailscale/Cloudflare Access better
- [ ] **HTTPS always** if it has a public hostname (Caddy/Cloudflare make this free and automatic)
- [ ] Firewall: only 22/80/443 open; app ports bound to `127.0.0.1` or a private network
- [ ] `restart: unless-stopped` on all containers; verify recovery with a test reboot
- [ ] Nightly backup of `./data/app.db` (the only state)
- [ ] Regenerate `searxng/settings.yml` → `secret_key` for any shared deployment (`openssl rand -hex 32`)
- [ ] Keep SSE working through every proxy layer you add: no response buffering
  (`proxy_buffering off` in nginx, `flush_interval -1` in Caddy)
- [ ] Watch your search etiquette: one instance, modest query rate — SearXNG's engine
  suspensions (already tuned in `settings.yml`) are the app telling you to slow down

## Cost summary

| Path | Setup effort | $/month | What you give up |
|---|---|---|---|
| A: PC + Tailscale | ~10 min | **0** | PC must stay on |
| B: Oracle free A1 | ~1 evening | **0** | Region capacity hunt; ARM |
| B: Hetzner CAX31 | ~1 evening | ~€8 | Nothing, really |
| C: hourly GPU when needed | per-use | ~$1–3/prep cycle | Manual spin-up |
| 24/7 GPU VM | — | $150+ | ❌ don't — worst value for this workload |
