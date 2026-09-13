# intelligence/diagnosis-assistant/

Component #7 — retrieval-grounded LLM: parallel vector search
(Chroma, component #6) + structured Prometheus query, assembled into
a prompt, sent to a local model (Ollama), answered with citations.

All design decisions are made — see `docs/setup/07-diagnosis-assistant.md`
and `PROGRESS_LOG.md` entries 21-23 for the full reasoning. Summary:

- **Model:** Llama 3.1 8B, via Ollama, `keep_alive: 0` on every
  request so the model unloads immediately after each response rather
  than sitting resident (a real memory constraint on this machine, see
  the setup doc §5).
- **Placement:** this whole component runs **host-level, not
  containerized** — same reasoning as Ollama's own placement (avoids
  re-solving Chroma/Prometheus's persistent-storage problem for a
  third thing, avoids Docker overhead on an already memory-tight WSL2
  VM). It reaches Chroma and Prometheus via the ports the topology
  already publishes to the host (`localhost:8000`, `localhost:9090`),
  and Ollama via `localhost:11434` — no container network involved.
- **Structured metrics: hybrid.** `router.py` tries a fixed PromQL
  template first (`promql_templates.py` — error rate, discard rate,
  flap/transition history, anomaly score); only when nothing matches
  does it ask the model to generate PromQL itself, which then gets
  validated by actually running it against Prometheus before its
  result is trusted (an invalid query fails there, not silently).
- **Provider scope: local-only.** No Groq/Gemini — see BACKLOG item 22
  for why that's deferred, not forgotten.

## Layout

- `promql_templates.py` — the fixed template set, keyed by keyword.
- `router.py` — matches a question to a template, or falls back to
  LLM-generated PromQL (validated before use).
- `prometheus_client.py` — thin Prometheus HTTP client, shared by both
  the template and fallback paths.
- `retrieval_client.py` — thin Chroma client, reusing component #6's
  collection (`netmind-docs`).
- `ollama_client.py` — single-shot, non-streaming `/api/generate` call
  with `keep_alive: 0`.
- `assistant.py` — ties it together: retrieval + metrics (parallel
  lookups, one failing doesn't block the other) assembled into one
  prompt, answered with citations.
- `benchmark.sh` / `benchmark_prompt.txt` — the 3B-vs-8B benchmark
  tooling from the model-decision phase (kept, not scaffolding).

## Running it

Host-level, inside the `Containerlab` distro, with the lab up and
Ollama installed (`docs/setup/07-diagnosis-assistant.md`). Dependencies
install into a dedicated virtual environment, not the system Python —
see §6 of that doc for why (Debian's Python refuses a bare `pip
install` on purpose, and `--break-system-packages` is a workaround,
not the fix):

```bash
cd ~/netmind-lab/intelligence/diagnosis-assistant
python3 -m venv .venv          # first time only
source .venv/bin/activate
pip install -r requirements.txt
python assistant.py "ethernet-1/1 just flagged an anomaly on carrier transitions, what's going on?"
```

Every subsequent run just needs `source .venv/bin/activate` again
(then `deactivate` when done) — `.venv/` persists on native fs across
`sync-to-lab.sh` runs (it's explicitly excluded from the sync, see
`scripts/sync-to-lab.sh`), so it doesn't need recreating each session.

## Not yet done / known limits of this first build

- **LLM-generated PromQL validation is syntactic only.** "Validated"
  currently means "Prometheus accepted it and returned something," not
  "it's the semantically right query for the question." Real
  limitation of a stage-1 fallback that hasn't been exercised with a
  real off-template question yet — revisit once it has been.
- **No retry/repair loop on a rejected generated query.** If the
  model's first attempt fails validation, the assistant reports that
  plainly rather than asking the model to try again. Simpler for stage
  1; a repair loop is a natural stage-2 addition once real usage shows
  it's needed.
- **Not yet tested end-to-end against the live lab** — built and
  reviewed, but no confirmed run against the real Ollama/Prometheus/
  Chroma stack yet. That run is the actual exit criterion for this
  build, same pattern as every prior component.
- **Citation quality depends on the model**, same as the benchmark
  found — this is Llama 3.1 8B's job to get right, not something the
  code enforces beyond asking for it in the prompt.
