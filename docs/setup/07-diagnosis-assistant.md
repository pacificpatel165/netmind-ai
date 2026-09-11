# Component #7 setup: diagnosis assistant (in progress)

Step-by-step record of environment install work for component #7,
kept separate from `docs/setup/01-network-lab-environment.md` per this
folder's numbering convention — component-specific setup gets its own
file rather than piling into the shared one. **Design decisions (which
model, local-only vs. also Groq/Gemini, fixed-template vs.
LLM-generated PromQL) are not finalized yet** — see the design
discussion in `PROGRESS_LOG.md` and `docs/roadmap/BACKLOG.md` item 21.
This file only captures what's actually been installed and verified so
far, ahead of that decision landing.

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

## Not yet done

- **Benchmark 3B vs. an 8B-class model** (e.g. `ollama pull
  llama3.1:8b`) for latency and memory headroom on this machine, with
  the other seven lab containers running at the same time — that
  result is what actually decides which model component #7 uses,
  rather than picking one by default. See `docs/roadmap/BACKLOG.md`
  item 21.
- **Placement decision:** Ollama is currently host-installed directly
  inside the `Containerlab` distro, not added to the topology as its
  own container the way every other component here has been. Whether
  it moves into `lab/topologies/netmind-2node.clab.yml` (consistent
  with the rest of the stack, survives `clab destroy` cycles the same
  way) or stays host-level (simpler if a GPU gets passed through to
  WSL2 later) is still open.
- **Multi-provider design:** whether to also wire in Groq and/or
  Gemini behind a shared provider interface (so the model can be
  swapped by config rather than hardcoded) is a real design decision
  under discussion, not yet built. Online providers would also be the
  first time this project needs to handle an API key/secret, which is
  its own small decision once it's actually built.
- **Structured Prometheus query design:** fixed PromQL templates vs.
  LLM-generated PromQL vs. a hybrid — still being discussed, not yet
  decided or built.
