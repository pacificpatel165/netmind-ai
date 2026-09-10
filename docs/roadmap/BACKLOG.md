# NetMind AI — backlog: deferred decisions & installation index

Two things live in this file, kept separate on purpose:

1. **Deferred decisions** — every point where we deliberately chose
   "smallest thing that works now" over "the more complete answer,"
   with why, and what "done" looks like when we come back to it. The
   component map and build order in `PROGRESS_LOG.md` tell you *what's
   next*; this file tells you *what we already looked at and set
   aside*, so nothing gets silently forgotten between sessions.
2. **Installation index** — a one-page map of everything installed so
   far and where the actual steps live, so "how do I rebuild this
   environment" never means re-reading every session log.

**How to use this file:** when a design discussion produces a "not now,
but note it" decision, add a row here in the same session, dated, with
a pointer to the `PROGRESS_LOG.md` entry it came from. When an item
gets picked up and resolved, move its row to **Resolved** below rather
than deleting it — the record of "we knew about this and chose when to
fix it" is worth keeping.

---

## Open / deferred

| # | Topic | Component | Why deferred | What "done" looks like | Noted |
|---|---|---|---|---|---|
| 1 | Kafka buffer between gnmic and Prometheus | #3 metrics store | Direct scrape proves the pipeline with one less moving part; Kafka is real architecture but adds a third component before Prometheus itself was even confirmed working | gnmic publishes to a Kafka topic, a consumer/exporter feeds Prometheus from it — worth doing once a *second* consumer of the same telemetry stream exists (e.g. #6 retrieval index also wanting it), not before | 2026-09-10, log (9) |
| 2 | Prometheus retention & downsampling policy | #3 metrics store | Roadmap explicitly names this as a learning goal, not a wiring task — there isn't enough real accumulated data yet to reason about the trade-offs concretely | A deliberate retention policy (short local retention + a downsampling or remote-write strategy) chosen *because* of what real data volume/query patterns turned out to need, not chosen in the abstract | 2026-09-10, log (9) |
| 3 | Prometheus persistent storage | #3 metrics store | A bind-mounted `/prometheus` would hit the same container-user (`nobody`) vs host-dir-owner (`clab`) permission mismatch that broke gnmic's file output initially — not worth solving before Prometheus itself is proven | Data survives `clab destroy`/`clab deploy` cycles; needs either a fixed-ownership bind mount or a named Docker volume instead of a host bind | 2026-09-10, log (9) |
| 4 | Kubernetes (k3s) + Cilium underlay | phase 2 / future component | Deliberately sequenced after the telemetry pipeline (#2–#4) is solid, so K8s learning doesn't compete with getting the pipeline proven | k3s running natively inside the `Containerlab` distro (not Docker Desktop's K8s toggle — same isolation problem as before), Cilium as CNI, attached to the `e1-2` interface already reserved on `srl1`/`srl2` | 2026-09-10, log (4) |
| 5 | Grow the lab past 2 nodes (leaf-spine) | #1 network lab | Smallest topology that proves the pipeline came first; topology complexity deferred until there's a real reason to add it (e.g. testing telemetry at scale, or the K8s-underlay attachment) | A second `.clab.yml` stage (kept alongside `netmind-2node.clab.yml`, not overwriting it) with 2 leaf + 2 spine nodes | 2026-09-10, log (2) |
| 6 | Pin container image tags | #2, #3, #4 | `gnmic`, `prom/prometheus`, and now `grafana/grafana` all currently track `:latest` in the topology file, written without a chance to confirm the resolved version first | All three pinned to the exact tag confirmed working, so an upstream release can't silently change lab behavior between sessions | 2026-09-10, log (6, 9, 12) |
| 12 | Grafana lab-only auth posture | #4 dashboards | Anonymous viewer access + a hardcoded admin password in the topology file are fine for a single-user local lab reachable only on `localhost`, not a pattern to carry forward once anything here is ever exposed beyond that | Revisit if/when Grafana (or anything else in this stack) is ever reachable from outside the local machine — swap to real auth, stop committing the admin password in plain YAML | 2026-09-10, log (12) |
| 7 | Install `rsync` in the `Containerlab` distro | tooling | Not in the base `wsl-containerlab` image; `sync-to-lab.sh` falls back to `cp`, which works but won't prune files deleted from the repo | `sudo apt install rsync` run once inside the distro, script automatically picks it up (already written to prefer rsync when present) | 2026-09-10, log (6) |
| 8 | `systemd` user-session warning on distro boot | tooling | `wsl: Failed to start the systemd user session for 'clab'` appeared on first boot; didn't block anything verified so far, so not investigated | Only worth digging into if something that specifically needs a systemd *user* service (not the root-level services containerlab/Docker CE use) starts misbehaving | 2026-09-10, log (2) |
| 9 | Containerlab distro's baked-in SSH key | tooling / security hygiene | `id_ecdsa` ships identical inside every download of the `wsl-containerlab` image — fine for its original purpose (`ssh clab@localhost`), not something to trust for anything else | A personal `id_ed25519` was already generated and registered on GitHub for git push (see log 5/6) — this row is a standing reminder not to reuse `id_ecdsa` for anything sensitive later, not an open task | 2026-09-10, log (5, 6) — mitigated, not fully "resolved" since the shared key still exists in the distro |
| 11 | Components #5–#11 | anomaly detection, retrieval index, diagnosis assistant, remediation proposal, security gate, config-push executor, IaC/environment provisioning | Not started — next in build order after #4 (dashboards) | Full descriptions live in `PROGRESS_LOG.md`'s Component map; not duplicated here on purpose, so there's one place to check for "what's actually left" | ongoing |

## Resolved

| # | Topic | Component | Resolved | Notes |
|---|---|---|---|---|
| 10 | gnmic → Prometheus metric names unverified | #3 metrics store | 2026-09-10, log (11) | Confirmed working end-to-end against real scrape output — Prometheus Status→Targets shows `netmind-gnmic` `UP` and `netmind_`-prefixed series return for both nodes. Component #3 stage 1 closed out. |

---

## Installation index

What's been installed, where, and which doc has the actual steps —
use this to find the right file fast rather than re-reading every
session log.

| Installed | Where | Steps live in | Notes |
|---|---|---|---|
| WSL2 update (≥ 2.4.4) | Windows host | `docs/setup/01-network-lab-environment.md` §2 | one-time per machine |
| `wsl-containerlab` distro | Windows host (as a WSL2 distro) | `docs/setup/01-network-lab-environment.md` §3 | official `srl-labs/wsl-containerlab` image |
| Docker Desktop WSL integration turned OFF for `Containerlab` | Windows host (Docker Desktop settings) | `docs/setup/01-network-lab-environment.md` §4 | the step that actually prevents the kernel-namespace conflict |
| Docker CE + containerlab | `Containerlab` distro | `docs/setup/01-network-lab-environment.md` §5 | one combined setup script |
| `gnmic` CLI | `Containerlab` distro | `docs/setup/01-network-lab-environment.md` §8 | separate from containerlab itself |
| Personal SSH key for GitHub push | `Containerlab` distro | this file, row 9 above | needed because the distro's baked-in key isn't yours |
| `srl1` / `srl2` (Nokia SR Linux) | Docker containers, inside `Containerlab` distro | `lab/README.md` | stood up via `clab deploy`, no separate host install |
| `gnmic` collector container | same | `telemetry/README.md` | stood up via `clab deploy` |
| Prometheus container | same | `metrics/README.md` | stood up via `clab deploy`; genuinely no host-level install step — it only exists as a container |
