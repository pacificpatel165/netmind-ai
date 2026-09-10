# metrics/

Component #3 — the metrics store. Prometheus, learning PromQL and
retention/downsampling trade-offs rather than just wiring it up (per
`docs/roadmap/SIGNAL_PATH.md`).

## Design decisions (2026-09-10)

- **Path from collector to store: direct scrape, no Kafka buffer.**
  gnmic exposes a Prometheus scrape endpoint directly
  (`telemetry-prometheus` output in `telemetry/collectors/gnmic.yaml`,
  port 9804); Prometheus scrapes it. A Kafka buffer between them —
  gnmic publishes to a topic, a separate consumer feeds Prometheus —
  is real architecture but a third moving part before Prometheus
  itself is proven working. Matches how components #1 and #2 were
  both built: smallest thing that proves the pipeline first, add
  complexity once that's solid. Revisit Kafka if/when a second
  consumer of the same stream shows up (e.g. component #6's retrieval
  index also wanting it).
- **Retention: Prometheus's 15-day default, not touched yet.** The
  roadmap explicitly calls out retention/downsampling trade-offs as a
  learning goal for this component — deliberately *not* addressed
  today, because there isn't enough real accumulated data yet to make
  those trade-offs concrete. Revisit as its own explicit topic later,
  not bundled into getting the pipeline working.
- **Deployment: containerized**, added as its own node (`prometheus`)
  in `lab/topologies/netmind-2node.clab.yml`, same pattern as `gnmic`.
  No persistent data volume yet — a bind-mounted `/prometheus` would
  hit the same container-user-vs-host-owner permission mismatch that
  broke gnmic's file output initially, for no benefit at this stage;
  data can live and die with the container until that's worth solving.

## Layout

- `prometheus/prometheus.yml` — the scrape config. This is where
  scrape-target and interval changes go, not the topology file.

## Running it

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/lab/topologies
sudo clab destroy -t netmind-2node.clab.yml --cleanup   # new bind mounts/ports need a full redeploy
sudo clab deploy -t netmind-2node.clab.yml
```

## Verifying it's actually working

Open http://localhost:9090 from a browser on Windows — WSL2 forwards
the container's published port automatically. In Prometheus's own UI:

- **Status → Targets** should show the `netmind-gnmic` job as `UP`.
- Run a query like `netmind_interface_state_oper_state` (exact metric
  name depends on how gnmic's `metric-prefix`/`append-subscription-name`
  settings shaped it — check what actually shows up under **Graph** if
  that specific name doesn't resolve) and confirm you see series for
  both `srl1` and `srl2`.

That's the exit criterion for component #3 stage 1 — real interface
telemetry queryable through PromQL, not just sitting in a file.
