# Signal Path — the plan behind NetMind AI

NetMind AI is the flagship project inside a broader career-reboot plan called Signal Path, tracked as a living document outside this repo. This file is the markdown summary — read it for context on *why* this project is built the way it is; check the living version for anything that may have moved since this was last synced.

## Background

18+ years in telecom/IT, most recently ~9.5 years as System Architect/Product Owner (Capgemini/Adtran), building NETCONF/RESTCONF/YANG-based NMS cloud plugins at scale in production. Re-entering IT after a career interruption, targeting a role that reflects that seniority — not an entry-tier automation position.

## Positioning

The market rewards automation depth (Python, Terraform, observability tooling) most clearly at the individual-contributor tier — real, but not the lane that uses 18+ years of judgment well, since it means competing against engineers with far more recent, more concentrated coding reps. The better-fit lane is Principal/Staff/Architect-level: evaluated on system-design and security trade-off judgment, not coding velocity.

One honest caveat baked into this plan: senior architecture roles are disproportionately filled internally, so "architecture only, minimal hands-on" is a harder door to break into from outside than it looks. The calibration this project follows: build enough, hands-on, to demonstrate and defend the system under real questioning (AI-assisted implementation is a legitimate, normal way to ship — not a shortcut to hide), and invest the real depth in design and security reasoning — ADRs, a threat model, documented trade-offs. That's the artifact that proves seniority, not line count.

## Why NetMind AI, specifically

NETCONF/RESTCONF/YANG are production-grade skills already, not a learning gap — so the flagship project deliberately isn't a rebuild of past work (NMS plugins). The real gaps closed along the way: gNMI/streaming telemetry, Kubernetes orchestration (theory-only today), public cloud (AWS) networking, and open-source visibility (past work is locked inside proprietary vendor platforms).

Among existing personal projects is LightYear-AI — an already-shipped, production-grade RAG assistant (hybrid retrieval, reranking, citation validation, RAGAS eval, real deployment). A second read-only AI-over-logs assistant on NetMind AI would look less mature sitting next to it. What LightYear-AI structurally can't do is write back to real infrastructure — that's NetMind AI's actual differentiator, and it's exactly the part a NETCONF/RESTCONF production background earns.

## The roadmap, phase by phase

1. **Personal platform live** (weeks 1–3) — a minimal site now, home for every write-up from day one rather than arriving at the end.
2. **Close real gaps only** (weeks 4–7) — Kubernetes from a real cluster up (the genuine gap; past work was plugin-layer, not orchestration), AWS networking on LocalStack's free tier, Docker as a light refresh only.
3. **Big lab + first open-source PR** (weeks 8–11) — Containerlab + srl-telemetry-lab, built/torn down with Terraform/Ansible, first real contribution (docs fix or example) to an existing project in this space.
4. **NetMind AI, part 1 — telemetry & data** (months 3–4) — gNMI/gRPC collection, Prometheus (+ Kafka), Grafana dashboards; actually learning the time-series database (PromQL, retention trade-offs), not just wiring it up.
5. **NetMind AI, part 2 — AI layer + security gate + a real PR** (months 4–6) — retrieval-grounded diagnosis, closed-loop remediation, and the security architecture around the write-back path (least-privilege credential scoping, RBAC, immutable audit log) built together as one core deliverable, not sequentially. Documented as a real ADR with a small threat model, not a "security is good" checkbox. One substantive upstream PR targeted here.
6. **Stretch — extends the same security story** (ongoing from month 6) — Kubernetes/Cilium hardening (secrets management, image scanning, runtime security) applied to the platform NetMind AI actually runs on, continuing the write-back security design rather than introducing a separate one. Optional: an open-source 5G core (Open5GS/free5GC) on the same hardened lab.

## Certifications

Timed deliberately last, after real hands-on confidence, not booked early to "prove" something on paper: CKA (Kubernetes — genuine gap), AWS Advanced Networking, CKS (feeds directly off the security work in phase 5–6). OSCP kept optional; CEH skipped (theory-only, no hands-on exam, doesn't fit this plan's emphasis on demonstrable work).

## Job search, running in parallel

Target titles: Network Automation Engineer, NetDevOps Engineer, Network Reliability Engineer, Infrastructure Automation Engineer, AIOps Engineer — and, per the positioning above, Principal/Staff/Architect-level roles specifically. Still an open decision: apply now (priced as a strong generalist) vs. apply once NetMind AI's closed-loop piece exists (priced as the specialist/architect tier).
