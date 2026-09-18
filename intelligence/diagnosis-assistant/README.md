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
- **Provider scope: pluggable, as of 2026-09-18 (BACKLOG item 35,
  reopens item 22).** `llm_provider.py` dispatches to Ollama (default,
  unchanged local behavior), Groq, or Gemini based on the `LLM_PROVIDER`
  env var — `assistant.py` and `router.py` only ever import
  `llm_provider`, never a specific backend, so adding a fourth provider
  later means adding one file, not touching either of those.

## Layout

- `promql_templates.py` — the fixed template set, keyed by keyword.
- `router.py` — matches a question to a template, or falls back to
  LLM-generated PromQL (validated before use).
- `prometheus_client.py` — thin Prometheus HTTP client, shared by both
  the template and fallback paths.
- `retrieval_client.py` — thin Chroma client, reusing component #6's
  collection (`netmind-docs`).
- `ollama_client.py` — single-shot, non-streaming `/api/generate` call
  with `keep_alive: 0`. Default backend.
- `groq_client.py` — single-shot chat completion against Groq's
  OpenAI-compatible API (`openai/gpt-oss-20b` by default — matches the
  Groq model already in use in another of my providers).
- `gemini_client.py` — single-shot `generateContent` call against
  Google's Gemini API (`gemini-3.5-flash-lite` by default — same
  reasoning; `gemini-2.5-flash` is the noted fallback).
- `llm_provider.py` — the provider abstraction: dispatches to whichever
  of the three above `LLM_PROVIDER` names. The only module
  `assistant.py`/`router.py` actually import for generation.
- `assistant.py` — ties it together: retrieval + metrics (parallel
  lookups, one failing doesn't block the other) assembled into one
  prompt, answered with citations.
- `benchmark.sh` / `benchmark_prompt.txt` — the 3B-vs-8B benchmark
  tooling from the model-decision phase (kept, not scaffolding).

## Running it

Host-level, inside the `Containerlab` distro, with the lab up and
Ollama installed (`docs/setup/07-diagnosis-assistant.md`). Dependencies
install into the **shared `intelligence/.venv`** (`BACKLOG.md` item 32,
2026-09-17) — this component no longer has its own per-component venv:

```bash
cd ~/netmind-lab/intelligence
python3 -m venv .venv          # first time only, if no other component
                                #   has already created it
source .venv/bin/activate
pip install -r requirements.txt
cd diagnosis-assistant
python assistant.py "ethernet-1/1 just flagged an anomaly on carrier transitions, what's going on?"
```

Every subsequent run just needs `source ../.venv/bin/activate` from
inside `diagnosis-assistant/` (or `source .venv/bin/activate` from
`intelligence/` directly), then `deactivate` when done. `.venv/`
persists on native fs across `sync-to-lab.sh` runs (it's explicitly
excluded from the sync, see `scripts/sync-to-lab.sh`), so it doesn't
need recreating each session.

**Switching providers:** copy `.env.example` to `.env` in this
directory (`.env` is gitignored — never commit real keys) and fill in
the key for whichever provider you're using:

```bash
cd ~/netmind-lab/intelligence/diagnosis-assistant
cp .env.example .env
# edit .env: set LLM_PROVIDER=groq (or gemini) and the matching *_API_KEY
python assistant.py "..."
```

Free keys: Groq at `https://console.groq.com/keys`, Gemini at
`https://aistudio.google.com/apikey`. Keys load from `.env` via
python-dotenv (`llm_provider.py`) rather than the command line, so they
never land in shell history or a `ps`/process-list dump. An explicitly
`export`ed env var still overrides `.env` if you'd rather set one that
way for a single run.

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
