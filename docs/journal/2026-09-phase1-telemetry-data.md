# ADR-001 — Phase 1: Telemetry & Data Pipeline (components #1–#4)

**Status:** Done, live-verified. **Dates:** 2026-09-10.
**Components:** #1 network lab, #2 telemetry collector, #3 metrics store, #4 dashboards.

## Context

The flagship project's first real question wasn't AI at all — it was whether a
believable, protocol-correct network lab could be stood up, streamed, stored,
and visualized end to end. Everything downstream (anomaly detection,
diagnosis, remediation) depends on this pipeline being real and trustworthy,
not a mock. The goal for this phase was the smallest topology and the
smallest pipeline that could prove the full path — deploy, subscribe, scrape,
render — before adding any complexity on top of it.

## Decisions

**Lab isolation.** Containerlab runs inside its own dedicated WSL2 distro
(`srl-labs/wsl-containerlab`), kept deliberately separate from the Docker
Desktop + Ubuntu setup already used for other projects on this machine.
Containerlab manipulates network namespaces and veth pairs directly; Docker
Desktop's WSL2 integration does the same at a different layer, and the two
collide. Docker Desktop's WSL integration is explicitly switched off for the
`Containerlab` distro to avoid that conflict outright rather than work around
symptoms of it.

**Topology size and shape.** Two SR Linux nodes, one link — the smallest
topology that can prove containerlab-to-gNMI reachability, grown later only
if a real reason shows up (`BACKLOG.md` item 5). Each node reserves a second
interface (`e1-2`), undeclared for now, for a planned future Kubernetes/Cilium
underlay attachment (`BACKLOG.md` item 4) — the lab is designed to nest under
that layer eventually, not sit beside it as an unrelated environment.

**Collector engine.** `gnmic`, config-driven via subscription YAML, not a
hand-written gNMI/gRPC client. This was a deliberate trade against
"impressive-looking" custom protocol code: writing a raw gNMI client would
have spent effort re-implementing something well-solved, at the cost of time
that belongs in the architecture and security decisions that actually
differentiate this project. Every component from here on reuses the same
pattern (a real, maintained tool, config-driven, containerized as its own
topology node) rather than reinventing infrastructure plumbing.

**Metrics path.** Direct scrape from `gnmic`'s own Prometheus output, no
Kafka buffer. The roadmap names Kafka explicitly; it was deliberately not
built in phase 1 because a second real consumer of the same telemetry stream
didn't exist yet to justify it (`BACKLOG.md` item 1) — a buffer with one
consumer is complexity without a benefit, and the project's whole build
discipline is proving a need before building for it.

**Dashboards as code.** Grafana's datasource and dashboard JSON are both
committed to the repo and auto-provisioned, not hand-built through the UI —
the dashboard is reproducible from git the same way the topology and
collector config are, not a manual artifact that could silently drift from
what's actually deployed.

## What went wrong, and what it taught

The single most consequential bug of this phase had nothing to do with
networking protocols: SR Linux's post-deploy commit step failed with
`Operation not permitted` because the lab directory lived on WSL2's `DrvFs`
mount of the Windows drive (`/mnt/c/...`), which doesn't support the POSIX
permission bits SR Linux needs to `chmod` its own config files during commit.
The fix — keep the git-tracked topology on the Windows drive as the source of
truth, but always run `clab deploy` against a synced copy on native Linux
filesystem (`~/netmind-lab/`) — became the load-bearing pattern for this
entire project's workflow (`scripts/sync-to-lab.sh`), and it is also this
project's single biggest remaining piece of process friction (see the
`docs/journal` entry on operational friction for the live discussion of
whether to keep it).

A second real bug, less dramatic but more instructive about failure modes:
`gnmic`'s file output failed completely silently at default log level when
its target directory (`/var/log/gnmic/`) didn't exist inside the image —
`docker logs` showed nothing at all. Only running with `--debug` surfaced the
real error. The lesson carried forward explicitly into every component after
this one: a component that appears to start cleanly and simply produces no
output is not verified, it's unverified in a way that looks like success —
worth remembering because this exact failure shape (looks-fine, produces
nothing) recurred in phase 2 with Chroma's collection-config mismatch and
the anomaly detector's silent `interface="unknown"` labeling bug.

A third, smaller but recurring pattern: two components (Grafana's dashboard
directory, later Chroma's server-image version) broke on first deploy because
of assumptions that were never checked against the real running system before
being written into code or config — an empty directory git doesn't track, a
`:latest` image tag that silently moved to a newer, incompatible version.
Both were fixed by pinning to something explicit and verified rather than
trusting a default.

## Verified

All four components closed out with a real exit criterion checked against
live output, not code review alone: `srl1`/`srl2` responding to real gNMI
`capabilities` calls; `gnmic` streaming real interface state/counter events
continuously to a file; Prometheus's own Targets page showing the scrape
`UP` with `netmind_`-prefixed series for both nodes; and the Grafana
dashboard rendering live panels across all 22 confirmed metric series,
including packet-type and additional-counter rows added only after the real
metric list was pulled from Prometheus's own browser rather than assumed.

## Open, tracked on the backlog, not forgotten

Kafka buffering (item 1), Prometheus retention/downsampling policy (item 2)
and persistent storage (item 3), growing the lab past two nodes (item 5),
and the Kubernetes/Cilium underlay itself (item 4) are all real, named,
deliberately deferred decisions — not oversights. See `docs/roadmap/BACKLOG.md`
for the current status of each.
