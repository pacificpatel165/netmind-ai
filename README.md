# NetMind AI

> **AI-augmented network observability, automation & security-by-design platform.**

| Item | Value |
|------|-------|
| **Status** | ✅ Components #1–#10 built and live-verified — the full detect→diagnose→propose→approve→execute pipeline runs end to end against a real network lab, proven twice (once per write-back protocol). Component #11 (IaC/environment provisioning) and a set of platform-quality improvements (see `docs/roadmap/BACKLOG.md`) are what's left. |
| **Author** | Prashant Patel |
| **Positioning** | Architecture & security-design judgment, not a coding-depth showcase — see "How this is positioned" below |
| **License** | MIT (code) · CC-BY 4.0 (write-ups, under `docs/`) |

---

## 📖 Vision

NetMind AI streams live network telemetry, understands it, and — with a human in the loop — acts on it. It's built on top of a Containerlab network lab (Nokia SR Linux): **gNMI** streaming telemetry out, **NETCONF/JSON-RPC** configuration push back in, landed in **Prometheus**, visualized in **Grafana**, with an AI layer on top that diagnoses issues and proposes a fix — gated by a security architecture before anything is allowed to touch the real network.

The project exists to prove one specific thing: the difference between a system that can *answer questions about* a network and one that can *act on* it safely. A retrieval-augmented assistant that only reads telemetry and logs is a well-understood pattern at this point — the interesting, harder, and more valuable half is closing the loop back to real configuration state, with a human approving every write and a security design that makes an untrustworthy AI proposal harmless by construction. That full loop is now built and live-verified — see `docs/journal/` for the ADR-style write-ups of how, and `PROGRESS_LOG.md` for the complete session-by-session record.

## 🎯 What makes this different from "another RAG chatbot"

Most AI-on-infrastructure demos stop at Q&A: ask a question, get an answer grounded in retrieved logs/metrics. NetMind AI treats that as step one, not the destination. The core loop, built and proven live:

**detect** (anomaly on the telemetry stream) → **diagnose** (retrieval-grounded explanation over historical metrics/logs/config) → **propose a remediation** (a concrete NETCONF/JSON-RPC config change) → **security gate: human approves** → **execute and verify against real device state** → **append-only audit log**.

That write-back step — and the security architecture around it — is the part that requires actually understanding network configuration protocols and system-design trade-offs, not just prompting an LLM over a vector store. It's also why this project exists alongside LightYear-AI, an already-shipped, production-grade RAG assistant of mine: LightYear-AI proves the read-only retrieval pattern end to end. NetMind AI's job is the harder half LightYear-AI structurally can't do — writing back to real infrastructure, safely — and that loop has now closed for real, twice, once per write-back protocol.

A live finding worth calling out here rather than glossing over: the credential-scoping piece of the security design was investigated directly against the real device, not assumed from documentation, and the honest result was that this platform's local AAA system doesn't support the per-leaf scoping general docs implied — so the actual, load-bearing security boundary is the human-approval gate and audit log, not credential scoping. See `docs/journal/2026-09-phase2-ai-layer-security-gate.md` for the full investigation and reasoning.

## 🔐 How this is positioned

This project is built to demonstrate senior-level system-design and security judgment, not to compete on coding velocity. The calibration: enough working code to build and defend the system under real questioning — AI-assisted implementation included, which is a legitimate and normal way to ship, not a shortcut to hide — with the real depth invested in architecture decision records (ADRs), a threat model for the write-back path, and documented trade-offs. See `docs/architecture/OVERVIEW.md` for the design invariant this project is actually built around, `docs/roadmap/SIGNAL_PATH.md` for the full plan and reasoning behind it, and `docs/journal/` for the phase-by-phase ADRs.

## 🏗 Technology Stack

| Category | Technology | Status |
|----------|------------|--------|
| Lab environment | Containerlab, Nokia SR Linux (2-node) | Built, live |
| Telemetry collection | gNMI / gRPC (`gnmic`) | Built, live |
| Configuration push | NETCONF, JSON-RPC | Built, live — both protocols proven |
| Metrics store | Prometheus | Built, live |
| Dashboards | Grafana | Built, live |
| Anomaly detection | Rolling z-score baseline | Built, live |
| Retrieval | Chroma (vector store) | Built, live |
| AI / diagnosis | Local LLM via Ollama (Llama 3.1 8B), hybrid PromQL templates + validated fallback | Built, live |
| Security gate | Human approval (default-deny), append-only audit log | Built, live |
| Config-push executor | Applies approved changes, verifies against real device state | Built, live |
| Kubernetes, AWS networking | Not yet built — see `docs/roadmap/BACKLOG.md` | Planned |
| IaC (Terraform/Ansible) | Not yet built — component #11 | Planned |
| Kafka buffer | Deliberately deferred, no second consumer yet | Deferred |

---

## 🚧 Roadmap

This repo's phases mirror the living project plan in `docs/roadmap/SIGNAL_PATH.md`:

1. **Telemetry & data** (components #1–#4) — ✅ done, live-verified. Write-up: `docs/journal/2026-09-phase1-telemetry-data.md`.
2. **AI layer + closed loop + security gate** (components #5–#10) — ✅ done, live-verified, both write-back protocols proven. Write-up: `docs/journal/2026-09-phase2-ai-layer-security-gate.md`.
3. **Platform-quality pass** — closing real gaps surfaced by building phases 1–2: automated per-component test scripts, Kubernetes and AWS networking (named in the original plan, not yet started), a real environment-provisioning story (component #11), and reducing operational friction (dependency/venv sprawl, the Windows-mount-plus-sync workflow). Tracked in `docs/roadmap/BACKLOG.md`.
4. **Upstream contribution** — at least one substantive PR to an existing project in this space (e.g. `gnxi`, `srl-telemetry-lab`, `gtexporter`).
5. **Security hardening (extends the core)** — Kubernetes/Cilium zero-trust policies, secrets management, image scanning, and runtime security applied to this project itself, continuing the same security story rather than introducing a new one.

Each phase gets its own ADR-style write-up under `docs/journal/` once real work lands — not before, so nothing here is aspirational marketing.

---

## 🛠 Getting Started

The full pipeline is built and live-verified, but first-time setup docs currently only cover the network lab (`docs/setup/01-network-lab-environment.md`) and the diagnosis assistant (`docs/setup/07-diagnosis-assistant.md`) in step-by-step form — the rest of the components' setup is covered inside their own `README.md` under `intelligence/`, `telemetry/`, `metrics/`, and `grafana/`, plus consolidated testing steps in `docs/testing/TESTING.md`. Filling in the remaining per-component setup docs is a tracked, in-progress gap — see `docs/roadmap/BACKLOG.md`.

## 📄 License

- Code: [MIT](LICENSE)
- Write-ups and documentation under `docs/`: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
