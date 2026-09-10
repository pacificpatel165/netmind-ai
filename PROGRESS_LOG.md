# NetMind AI — Progress Log

Running log of design sessions and implementation work, one entry per session. Newest entry on top. This is the working record; `docs/roadmap/SIGNAL_PATH.md` is the stable plan, `docs/architecture/OVERVIEW.md` is the stable design — this file is where decisions get made before they're stable enough to land there.

---

## Component map

NetMind AI breaks into 11 top-level components, grouped by role, in the order data flows through the system:

**Substrate**
1. **Network lab** — Containerlab + Kubernetes/Cilium cluster simulating the devices NetMind observes and configures. Nothing else works without this existing first.

**Telemetry & storage (phase 4 territory)**
2. **Telemetry collector** — gNMI/gRPC streaming off the lab, normalized for ingestion. The one genuinely new protocol in the project.
3. **Metrics store** — Prometheus (+ Kafka buffer). Learn PromQL and retention/downsampling trade-offs, don't just wire it up.
4. **Dashboards** — Grafana on top of Prometheus. Low design complexity; makes the pipeline visibly real.

**Intelligence layer (phase 5 territory)**
5. **Anomaly detection** — scheduled job, rolling baseline first, a real model (isolation forest or similar) only once the baseline's limits are understood. No LLM involved.
6. **Retrieval index** — runbooks/past incidents chunked, embedded, stored in a vector DB (Chroma or pgvector). Runs continuously in the background.
7. **Diagnosis assistant** — retrieval-grounded LLM: parallel vector search + structured Prometheus/log query, assembled into a prompt, sent to a local model (Ollama), answered with citations.
8. **Remediation proposal** — the diagnosis assistant's output extended one step further into a concrete NETCONF/RESTCONF config change.

**Security & control plane (the differentiator)**
9. **Security gate** — every proposal from #8 passes through here: least-privilege credential scoping, explicit human approval (no default-approve), immutable audit log. The component that makes this an architecture story, not an AI-integration demo.
10. **Config-push executor** — the NETCONF/RESTCONF client that applies an *approved* change, using the scoped credential from #9. Directly reuses production background — the one component that isn't new learning.

**Cross-cutting**
11. **IaC / environment provisioning** — Terraform/Ansible to stand up and tear down #1, #3, #4. Runs alongside the others rather than sitting in the data flow.

Build order follows the numbering: 1→4 is phase 4 (telemetry), 5→10 is phase 5 (AI layer + security gate), 11 runs alongside 1 and 3 throughout.

---

## Session log

### 2026-09-10 — Component breakdown & planning
**Focus:** Decompose NetMind into top-level components before starting design/implementation session by session.
**Decided:** The 11-component map above, plus the build order. Sessions from here go component by component rather than jumping around.
**Next:** Pick a starting component — candidates discussed: #1 (network lab, first in build order) or #9 (security gate, the differentiator with the most open design decisions, doesn't strictly require #1–#8 built first to design on paper).
**Open questions:** none yet — this session was planning-only, no design decisions made on any individual component.
