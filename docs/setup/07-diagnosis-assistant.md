# Component #7 setup: diagnosis assistant

Step-by-step record of environment install work for component #7,
kept separate from `docs/setup/01-network-lab-environment.md` per this
folder's numbering convention — component-specific setup gets its own
file rather than piling into the shared one.

**Status (updated 2026-09-17, `BACKLOG.md` item 37):** built and
live-verified — see §7 below. This file previously described the
component as "in progress" and listed the build as not-yet-done; that
went stale once component #7 was actually finished and confirmed
against the live lab (`PROGRESS_LOG.md` entry 29, 2026-09-13). Caught
and fixed while writing the other 8 `docs/setup/` files (entry 50) —
flagged separately rather than silently left inconsistent, same
discipline as the root `README.md` fix in entry 44.

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
  deferrals in `docs/roadmap/BACKLOG.md`). **Update, 2026-09-16:** a
  concrete reason has since been given directly and this is reopened
  as `BACKLOG.md` item 35 — not started yet, but no longer "no reason
  exists."
- Structured Prometheus query strategy: **hybrid** — fixed PromQL
  templates first, LLM-generated PromQL fallback, validated before
  ever running (`PROGRESS_LOG.md` entry 21). Built and exercised for
  real — see §7.

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

## 6. Install python3-venv, and run the assistant in its own virtual environment

`python3-pip` and the venv module aren't in the base `wsl-containerlab`
image either — same class of gap as `rsync`/`zstd`/`time`. Note: the
generic `python3-venv` package name doesn't cover it on this distro —
Debian ties the venv module to the specific interpreter version, so
the real package name is `python3.11-venv` (or whatever `python3
--version` reports on the machine you're setting this up on):

```bash
sudo apt update
sudo apt install -y python3-pip python3.11-venv
```

If `python3 -m venv .venv` still fails with "ensurepip is not
available" after this, the error message itself names the exact
package it wants — install that one rather than guessing.

**Correction (2026-09-13):** the first pass at this doc suggested a
plain `pip install -r requirements.txt` against the system Python.
That's the wrong way to do this — Debian's Python (PEP 668,
"externally-managed-environment") refuses exactly this for good
reason: installing packages into the system interpreter risks
clashing with whatever apt itself depends on, and offers no
isolation between this component's dependencies and anything else
that might run Python in this distro later. `--break-system-packages`
would silence the error but doesn't fix the actual problem — it's a
workaround, not a decision. The correct, standard practice is a
per-project virtual environment:

```bash
cd ~/netmind-lab/intelligence/diagnosis-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Update, 2026-09-17 (`BACKLOG.md` item 32):** since this venv
consolidation, `diagnosis-assistant` shares `intelligence/.venv` with
every other host-level component rather than having its own — if
you've already created that shared venv for another component, use
`source ../.venv/bin/activate` from inside `intelligence/
diagnosis-assistant` instead of creating a new one here. The commands
above still work standalone if you're on the older per-component
layout.

`.venv/` is gitignored (`intelligence/diagnosis-assistant/.gitignore`)
— it's a local, disposable environment, not something to commit.
Every subsequent run needs the venv active:

```bash
cd ~/netmind-lab/intelligence/diagnosis-assistant
source .venv/bin/activate   # or ../.venv/bin/activate — see the note above
python assistant.py "<question>"
```

(`deactivate` leaves the venv when done.) `.venv/` is explicitly
excluded in `scripts/sync-to-lab.sh` (same fix shape as the
containerlab-generated-state exclude from the lab-restart bug) — the
first version of this doc claimed the venv would survive a resync
untouched without checking that, which was wrong: without the
exclude, `sync-to-lab.sh`'s `rsync --delete` would wipe it on every
`lab-up.sh` run, since it only ever exists natively. With the exclude
in place, it correctly survives resyncs and only needs recreating if
you delete it yourself or move to a fresh machine.

## 7. Built and verified against the live lab (2026-09-13, PROGRESS_LOG entries 21–29)

All design decisions above were carried through to a real, working
component, not left as decisions on paper:

- The fixed PromQL template set and the router that picks a template
  or falls back to LLM-generated PromQL (`router.py`,
  `promql_templates.py`).
- The generate-and-validate fallback path — a real off-template
  question ("what's the current traffic rate") made Llama 3.1 8B
  generate syntactically invalid PromQL on the first attempt;
  validation correctly rejected it and reported failure rather than
  presenting bad data (entry 28). Traffic rate was then promoted to
  its own fixed template (`octet_rate`) rather than left on the
  fragile LLM-generated path, since it's too common a question for
  that.
- Prompt assembly combining retrieval (Chroma) + structured metrics
  (Prometheus) + the question, sent to Ollama with citations.

**Exit criterion met (entry 29):**

```bash
cd ~/netmind-lab/intelligence/diagnosis-assistant
source ../.venv/bin/activate   # or ./.venv/bin/activate on the older layout
python assistant.py "what's the current traffic rate on ethernet-1/1, and why don't we use Kafka to buffer this telemetry?"
```

Returned a correctly cited answer combining a real Prometheus number
(via the `octet_rate` template) and a real doc citation (via retrieval
against the re-ingested corpus) — proof this component actually
answers grounded, cited questions against live data, not just that it
runs without erroring.

## 8. Automated tests (optional, no lab or Ollama needed)

`test_router.py` covers `match_template()`/`extract_interface()`'s
deterministic keyword routing, including the exact off-template case
from entry 28 above, with no live Prometheus/Ollama/Chroma required.
Uses the shared `intelligence/.venv` from §6 — see
`docs/testing/TESTING.md`'s "Automated tests" section.
