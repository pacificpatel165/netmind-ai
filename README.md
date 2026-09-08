# NetMind AI

> **AI-augmented network observability, automation & security-by-design platform.**

| Item | Value |
|------|-------|
| **Status** | 🚧 Early development — telemetry layer not yet built |
| **Author** | Prashant Patel |
| **Positioning** | Architecture & security-design judgment, not a coding-depth showcase — see "How this is positioned" below |
| **License** | MIT (code) · CC-BY 4.0 (write-ups, under `docs/`) |

---

## 📖 Vision

NetMind AI streams live network telemetry, understands it, and — with a human in the loop — acts on it. It's built on top of a Containerlab + Kubernetes network lab: **gNMI** streaming telemetry out, **NETCONF/RESTCONF** configuration push back in, landed in **Prometheus** (optionally buffered through **Kafka**), visualized in **Grafana**, with an AI layer on top that diagnoses issues and proposes a fix — gated by a security architecture before anything is allowed to touch the real network.

The project exists to prove one specific thing: the difference between a system that can *answer questions about* a network and one that can *act on* it safely. A retrieval-augmented assistant that only reads telemetry and logs is a well-understood pattern at this point — the interesting, harder, and more valuable half is closing the loop back to real configuration state, with a human approving every write and a security design that makes an untrustworthy AI proposal harmless by construction.

## 🎯 What makes this different from "another RAG chatbot"

Most AI-on-infrastructure demos stop at Q&A: ask a question, get an answer grounded in retrieved logs/metrics. NetMind AI treats that as step one, not the destination. The core loop is:

**detect** (anomaly on the telemetry stream) → **diagnose** (retrieval-grounded explanation over historical metrics/logs/config) → **propose a remediation** (a concrete NETCONF/RESTCONF config change) → **security gate: human approves, scoped credential** → **execute and verify** → **immutable audit log**.

That write-back step — and the security architecture around it — is the part that requires actually understanding network configuration protocols and system-design trade-offs, not just prompting an LLM over a vector store. It's also why this project exists alongside LightYear-AI, an already-shipped, production-grade RAG assistant of mine: LightYear-AI proves the read-only retrieval pattern end to end. NetMind AI's job is the harder half LightYear-AI structurally can't do — writing back to real infrastructure, safely.

## 🔐 How this is positioned

This project is built to demonstrate senior-level system-design and security judgment, not to compete on coding velocity. The calibration: enough working code to build and defend the system under real questioning — AI-assisted implementation included, which is a legitimate and normal way to ship, not a shortcut to hide — with the real depth invested in architecture decision records (ADRs), a threat model for the write-back path, and documented trade-offs. See `docs/architecture/OVERVIEW.md` for the design invariant this project is actually built around, and `docs/roadmap/SIGNAL_PATH.md` for the full plan and reasoning behind it.

## 🏗 Technology Stack (planned)

| Category | Technology |
|----------|------------|
| Lab environment | Containerlab, Kubernetes (kind/k3d), Cilium |
| Telemetry collection | gNMI / gRPC |
| Configuration push | NETCONF / RESTCONF |
| Metrics store | Prometheus (+ Kafka as a buffer) |
| Dashboards | Grafana |
| AI / retrieval | Local LLM via Ollama, vector store (Chroma or pgvector) |
| Security gate | Least-privilege NETCONF/RESTCONF credential scoping, RBAC on approvals, immutable audit log |
| IaC | Terraform / Ansible |

Stack is not finalized in code yet — this repo starts as a scaffold and fills in phase by phase. See the roadmap below.

---

## 🚧 Roadmap

This repo's phases mirror the living project plan in `docs/roadmap/SIGNAL_PATH.md`:

1. **Telemetry & data** — gNMI/gRPC collection off the lab, landed in Prometheus (+ Kafka), Grafana dashboards.
2. **AI layer + closed loop + security gate** — anomaly detection on the telemetry stream, retrieval-grounded diagnosis, NETCONF/RESTCONF-driven remediation proposals, and the human-approval security architecture around them, built together, not sequentially.
3. **Upstream contribution** — at least one substantive PR to an existing project in this space (e.g. `gnxi`, `srl-telemetry-lab`, `gtexporter`) once confident in the codebase.
4. **Security hardening (extends the core)** — Kubernetes/Cilium zero-trust policies, secrets management, image scanning, and runtime security applied to this project itself, continuing the same security story rather than introducing a new one.

Each phase gets its own ADR-style write-up under `docs/journal/` once real work lands — not before, so nothing here is aspirational marketing.

---

## 🛠 Getting Started

Nothing runnable yet — this is the initial scaffold. `docs/architecture/` carries the design as components land; check back as phase 1 (telemetry) is built out.

---

## 📄 License

- Code: [MIT](LICENSE)
- Write-ups and documentation under `docs/`: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
