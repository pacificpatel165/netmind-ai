# NetMind AI — Architecture Overview

This document describes the intended architecture. It is written ahead of the code deliberately — the roadmap builds phase by phase (telemetry first, AI layer second), and this file gets corrected against reality as each phase lands. Treat anything below as a design intent, not a claim about what's implemented.

## System shape

```
┌─────────────────  ┐    gNMI/gRPC           ┌─────────────┐
│  Network lab      │  ───────────────────▶ |Telemetry     │
│  (Containerlab +  │                        │  collector  │
│   Kubernetes/     │ ◀───────────────────  │              │
│   Cilium)         │   NETCONF/RESTCONF     └─────┬───────┘
└─────────▲─────────┘   (config push back)         │
          │                                        ▼
          │                                 ┌──────────────┐
          │                                 │  Prometheus  │
          │                                 │  (+ Kafka    │
          │                                 │   buffer)    │
          │                                 └──────┬───────┘
          │                                        │
          │                                        ▼
          │                                 ┌──────────────┐
          │                                 │  Grafana     │
          │                                 │  dashboards  │
          │                                 └──────┬───────┘
          │                                        │
          │                                        ▼
          │                                 ┌──────────────┐
          │                                 │  Anomaly     │
          │                                 │  detection   │
          │                                 └──────┬───────┘
          │                                        │ on anomaly
          │                                        ▼
          │                                 ┌────────────── ┐
          │                                 │  Diagnosis:   │
          │                                 │  retrieval    │
          │                                 │  over metrics/│
          │                                 │  logs/config  │
          │                                 │  history      │
          │                                 └──────┬─────── ┘
          │                                        │ proposed fix
          │                                        ▼
          │                                 ┌──────────────┐
          │                                 │  Human       │
          │                                 │  approval    │
          │                                 └──────┬───────┘
          │                approved                │
          └────────────────────────────────────────┘
                    NETCONF/RESTCONF config push
```

## Why NETCONF/RESTCONF write-back is the core design decision

Every component above the "Grafana dashboards" box is table-stakes for a modern observability stack. What makes this a distinct project rather than a rebuild of an existing pattern is the bottom loop: a proposed remediation only ever reaches the network through the same NETCONF/RESTCONF channel used for legitimate configuration management, gated by an explicit human-approval step. No component in this system is permitted to push configuration without that gate — this is a design invariant, not a phase-2 nice-to-have, and it should hold even in early prototypes where the "human approval" step is a CLI prompt rather than a UI.

## Retrieval scope

The retrieval layer indexes three sources for the diagnosis step: recent Prometheus metric history (windowed, not full-resolution — the point is trend context, not raw dumps), structured event/log data if Kafka/Elasticsearch is in the pipeline, and the network's own configuration history (what changed, when, and what was pushed as a result of a prior remediation). Grounding diagnosis in the network's own configuration history — not just external documentation — is what separates this from a general-purpose RAG assistant pointed at a knowledge base.

## Open questions (to resolve as phase 1/2 land)

- Anomaly detection: statistical baselining first (rolling mean/stddev, seasonal decomposition), escalate to a real model (isolation forest or similar) only once the baseline's limits are understood and articulable.
- Local LLM choice for the diagnosis/remediation-proposal layer: to be decided against actual hardware constraints once this phase starts — no api dependency, self-hosted via Ollama.
- Approval interface: starts as the simplest thing that enforces the gate (CLI y/n), not a build-a-UI detour before the loop itself works end to end.
