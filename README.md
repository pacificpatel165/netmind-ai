# NetMind AI

> **AI-augmented network observability & closed-loop automation platform.**

| Item | Value |
|------|-------|
| **Status** | 🚧 Early development — telemetry layer not yet built |
| **Author** | Prashant Patel |
| **License** | MIT (code) · CC-BY 4.0 (write-ups, under `docs/`) |

---

## 📖 Vision

NetMind AI streams live network telemetry, understands it, and — with a human in the loop — acts on it. It's built on top of a Containerlab + Kubernetes network lab: **gNMI** streaming telemetry out, **NETCONF/RESTCONF** configuration push back in, landed in **Prometheus** (optionally buffered through **Kafka**), visualized in **Grafana**, with an AI layer on top that can explain what's happening and propose a fix.

The project exists to prove one specific thing: the difference between a system that can *answer questions about* a network and one that can *act on* it. A retrieval-augmented assistant that only reads telemetry and logs is a well-understood pattern at this point — the interesting, harder, and more valuable half is closing the loop back to real configuration state, safely, with a human approving every write.

## 🎯 What makes this different from "another RAG chatbot"

Most AI-on-infrastructure demos stop at Q&A: ask a question, get an answer grounded in retrieved logs/metrics. NetMind AI treats that as step one, not the destination. The core loop is:

**detect** (anomaly on the telemetry stream) → **diagnose** (retrieval-grounded explanation over historical metrics/logs/config) → **propose a remediation** (a concrete NETCONF/RESTCONF config change) → **human approves** → **execute and verify**.

That write-back step is the part that requires actually understanding network configuration protocols, not just prompting an LLM over a vector store — which is exactly the depth this project is meant to demonstrate.

## 🏗 Technology Stack (planned)

| Category | Technology |
|----------|------------|
| Lab environment | Containerlab, Kubernetes (kind/k3d), Cilium |
| Telemetry collection | gNMI / gRPC |
| Configuration push | NETCONF / RESTCONF |
| Metrics store | Prometheus (+ Kafka as a buffer) |
| Dashboards | Grafana |
| AI / retrieval | Local LLM via Ollama, vector store (Chroma or pgvector) |
| IaC | Terraform / Ansible |

Stack is not finalized in code yet — this repo starts as a scaffold and fills in phase by phase. See the roadmap below.

---

## 🚧 Roadmap

This repo's phases mirror the living project plan (kept up to date outside this repo):

1. **Telemetry & data** — gNMI/gRPC collection off the lab, landed in Prometheus (+ Kafka), Grafana dashboards.
2. **AI layer + closed loop** — anomaly detection on the telemetry stream, retrieval-grounded diagnosis, and NETCONF/RESTCONF-driven remediation proposals with human approval.
3. **Upstream contribution** — at least one substantive PR to an existing project in this space (e.g. `gnxi`, `srl-telemetry-lab`, `gtexporter`) once confident in the codebase.
4. **Security hardening** — Kubernetes/Cilium zero-trust policies, secrets management, image scanning, and runtime security applied to this project itself.

Each phase gets its own write-up under `docs/journal/` once real work lands — not before, so nothing here is aspirational marketing.

---

## 🛠 Getting Started

Nothing runnable yet — this is the initial scaffold. `docs/architecture/` will carry the design as components land; check back as phase 1 (telemetry) is built out.

---

## 📄 License

- Code: [MIT](LICENSE)
- Write-ups and documentation under `docs/`: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
