# telemetry/

Component #2 — the telemetry collector. gNMI/gRPC streaming off the lab,
normalized for ingestion by the future metrics store (component #3).

## Design decisions (2026-09-10)

- **Engine: `gnmic`**, config-driven, not a hand-written gNMI client.
  `gnmic` is a mature, production-grade tool — the design work here is
  choosing subscription paths, sample intervals, and output routing,
  not re-implementing gRPC/protobuf handling. Matches the project's
  "architecture over coding depth" positioning while still requiring
  real gNMI subscription design.
- **Deployment: containerized**, declared as its own node (`gnmic`) in
  `lab/topologies/netmind-2node.clab.yml`, on the same `netmind-mgmt`
  network as `srl1`/`srl2`. Stood up and torn down with the rest of the
  lab rather than living as a separate process with its own lifecycle —
  the same pattern the metrics store and dashboards will use next, and
  the one Kubernetes will use later.

## Layout

- `collectors/gnmic.yaml` — the subscription config: which gNMI targets,
  which paths, which outputs. This is where subscription design changes
  go, not the topology file.
- `output/` — where the `gnmic` container's file output actually lands,
  bind-mounted from `/var/log/gnmic` inside the container. Generated
  data, not source — ignored by git except for `.gitkeep`. It only ever
  exists on the native-fs copy (`~/netmind-lab/telemetry/output/`) since
  that's where the lab actually runs; nothing here syncs back to the
  Windows-drive copy of the repo.

## Scope

Subscribes to interface operational/admin state and statistics on both
nodes, sampled every 10s, fed to two outputs: a file
(`output/netmind-telemetry.jsonl`, readable directly from the WSL shell
— the original stage-1 validation output, still useful for raw
inspection) and, since 2026-09-10, a Prometheus scrape endpoint on port
9804 — see `metrics/README.md` for the metrics-store side of that same
pipeline. Same subscription set feeds both; adding Prometheus didn't
require touching the subscription design at all.

**Known gotcha:** `gnmic`'s file output does not create a missing parent
directory — `/var/log/gnmic/` doesn't exist in the image, so without the
bind mount below every write silently fails (only visible with
`gnmic ... --debug`, default log level shows nothing). Fixed by
bind-mounting `telemetry/output/` onto `/var/log/gnmic`, which makes
Docker create the mount point automatically.

## Running it

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/lab/topologies
sudo clab deploy -t netmind-2node.clab.yml
```

## Verifying it's actually streaming

```bash
tail -f ~/netmind-lab/telemetry/output/netmind-telemetry.jsonl
```

You should see interface state/counter events for both `srl1` and
`srl2` arriving roughly every 10 seconds. That's the exit criterion for
component #2 stage 1 — a reliable, containerized stream of real
telemetry off the lab.
