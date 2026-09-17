# Component #3 setup: metrics store (Prometheus)

Step-by-step "how" per this folder's convention. For the *why* — direct
scrape over a Kafka buffer, retention left at Prometheus's 15-day
default deliberately, no persistent volume yet — see `metrics/README.md`
and `PROGRESS_LOG.md` entries dated 2026-09-10.

Prerequisite: component #2 (telemetry collector) is deployed and
streaming — this component scrapes `gnmic`'s Prometheus output directly.

---

## 1. Nothing extra to install

Prometheus runs as a container (`prometheus` node in
`lab/topologies/netmind-2node.clab.yml`) — no host-level install. The
scrape config lives at `metrics/prometheus/prometheus.yml`, not in the
topology file — change scrape targets/intervals there.

## 2. Deploy

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/lab/topologies
sudo clab destroy -t netmind-2node.clab.yml --cleanup   # new bind mounts/ports need a full redeploy, not just an up-to-date sync
sudo clab deploy -t netmind-2node.clab.yml
```

The full-redeploy step matters the first time this component is added
to an already-running lab (new port publish, new bind mount) — a plain
`clab deploy` over an already-running topology won't pick those up.
Not needed on later deploys once Prometheus is already part of the
topology you're redeploying from.

## 3. Verify

Open `http://localhost:9090` from a browser on Windows — WSL2 forwards
the container's published port automatically.

- **Status → Targets** should show the `netmind-gnmic` job as `UP`.
- Run a query like `netmind_interface_state_oper_state` under
  **Graph** (the exact metric name depends on how `gnmic`'s
  `metric-prefix`/`append-subscription-name` settings shaped it — if
  that specific name doesn't resolve, browse what's actually there) and
  confirm series exist for both `srl1` and `srl2`.

That's the exit criterion — real interface telemetry queryable through
PromQL, not just sitting in a file. Full design detail:
`metrics/README.md`.
