# Component #7 setup: diagnosis assistant (in progress)

Step-by-step record of environment install work for component #7,
kept separate from `docs/setup/01-network-lab-environment.md` per this
folder's numbering convention — component-specific setup gets its own
file rather than piling into the shared one.

**Decided:**
- Model: **Llama 3.1 8B**, run via Ollama with `keep_alive: 0` on
  every API request (see §5 below) — not `llama3.2:3b`.
- Placement: **host-installed, not containerized** (2026-09-13,
  PROGRESS_LOG entry 23). Keeping it out of the topology means the
  ~4.9GB model file (native to `~/.ollama`) survives every `clab
  destroy`/`clab deploy` cycle for free, and avoids adding Docker
  overhead on top of an already memory-tight WSL2 VM (§5). Revisit
  only if a concrete reason shows up (e.g. GPU passthrough into WSL2
  making a container-level integration worthwhile).
- Provider scope: **local-only, no Groq/Gemini for now** (2026-09-13,
  same entry). 8B already proved correct with proper citations — there
  is no concrete gap yet that a second provider would close. Building
  a provider abstraction speculatively would break this project's
  established pattern of proving something's needed before building
  it (same reasoning as the Kafka, retention, and re-ingestion
  deferrals in `docs/roadmap/BACKLOG.md`). Revisit if a real question
  later exposes a correctness or capability gap 8B can't cover.
- Structured Prometheus query strategy: **hybrid** — fixed PromQL
  templates first, LLM-generated PromQL fallback, validated before
  ever running (`PROGRESS_LOG.md` entry 21). Not yet built — this is
  the next real build step for the component.

---

## 1. Install zstd (Ollama install-script dependency)

Not present in the base `wsl-containerlab` image; Ollama's install
script needs it for extraction:

```bash
sudo apt update
sudo apt install -y zstd
```

## 2. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

The install script starts its own background `ollama serve`
automatically, bound to `127.0.0.1:11434`. **Don't also run `ollama
serve` manually** — it will fail with "address already in use" against
the service already running; that error is expected and not a real
problem, the already-running service is what actually serves requests.

## 3. Pull and verify a model

```bash
ollama pull llama3.2:3b
ollama run llama3.2:3b "test prompt"
```

Confirmed working 2026-09-11: `llama3.2:3b` (2.0GB) downloaded and
returned a coherent response.

## 4. Benchmark 3B vs. 8B

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/intelligence/diagnosis-assistant/benchmark.sh
```

Run with the lab already up (`lab-up.sh`) so the timing reflects real
contention against the other seven containers, not an idle machine.
Pulls `llama3.1:8b` if not already present, then runs the same
representative prompt (`benchmark_prompt.txt` — a retrieved doc chunk
+ a metrics summary + a question, the actual shape component #7 will
send) against both `llama3.2:3b` and `llama3.1:8b`, printing wall time
and peak RSS for each. Run 2026-09-11 — see §5 below for the result
and the model decision it produced.

## 5. Model decision and memory finding (2026-09-11)

Both correctness and a real memory constraint were involved:

- **8B is meaningfully more correct.** 3B misstated the actual Kafka
  decision (said it was "added" when it was deliberately skipped) and
  cited sources vaguely. 8B got the fact right and cited the specific
  source inline, on two separate runs. For a tool whose whole value is
  grounded, cited answers, that outweighs 8B's ~2.3x slower response
  (67s vs. 29s for this prompt).
- **Real memory constraint found and resolved.** This machine has
  24GB physical RAM, but Windows itself runs tight (confirmed via
  Task Manager: `vmmemWSL` alone used ~7.8GB while the lab + a loaded
  8B model were active — by far the largest process on the machine).
  While the model is actively loaded, `free -h` inside the WSL2 VM
  showed available memory drop to ~1.5GB (used 9.6-9.7GB of 11GiB) —
  tight enough to be a real risk if left resident.
- **`OLLAMA_KEEP_ALIVE=0` set on the `ollama run` CLI did NOT work** —
  memory stayed pinned at ~9.6GB across multiple checks over 20+
  seconds. Root cause: `ollama serve` was already running as a
  background daemon (auto-started by the install script) before that
  variable was ever set; a client-side env var doesn't retroactively
  change an already-running server's behavior.
- **`ollama stop llama3.1:8b` reliably works** — confirmed: memory
  returned to the exact baseline (4.5GB used / 6.7GB available,
  matching the pre-load reading) immediately after, and held there.
- **The correct production fix is `"keep_alive": 0` in the API request
  body**, not a CLI env var or a manual `ollama stop` call after every
  use. Ollama's `/api/generate` endpoint accepts `keep_alive`
  per-request and the server honors it natively — component #7's real
  code should set this on every call it makes, so the model unloads
  automatically after each response without a separate step.

**Decision: Llama 3.1 8B**, called with `keep_alive: 0` on every request.

## Not yet done

All design decisions for component #7 are now made (model, placement,
provider scope, PromQL strategy). What's left is the actual build:
the fixed PromQL template set, the router that picks a template or
falls back to LLM-generated PromQL, the generate-and-validate fallback
path itself, and the prompt assembly that combines retrieval (Chroma)
+ structured metrics (Prometheus) + the question into what gets sent
to Ollama.
