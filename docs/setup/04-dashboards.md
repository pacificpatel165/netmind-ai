# Component #4 setup: dashboards (Grafana)

Step-by-step "how" per this folder's convention. For the *why* —
dashboards provisioned as code rather than clicked together, anonymous
viewer access for a single-user local lab — see `grafana/README.md` and
`PROGRESS_LOG.md` entries dated 2026-09-10.

Prerequisite: component #3 (metrics store) is deployed and scraping
successfully — this component only visualizes what Prometheus already
has.

---

## 1. Nothing extra to install

Grafana runs as a container (`grafana` node in
`lab/topologies/netmind-2node.clab.yml`). The datasource
(`grafana/provisioning/datasources/prometheus.yml`) and dashboard-loader
config (`grafana/provisioning/dashboards/dashboards.yml`) are both
bind-mounted and auto-loaded on start — no manual datasource setup in
the UI.

## 2. Deploy

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/lab/topologies
sudo clab deploy -t netmind-2node.clab.yml
```

## 3. Known gotcha: empty `dashboards/` directory

Git doesn't track empty directories. If `grafana/dashboards/` has no
dashboard JSON committed and no tracked `.gitkeep`, the directory
simply won't exist after a fresh clone/sync, and `clab deploy`'s
bind-mount validation fails with `Failed to verify bind path: stat
.../grafana/dashboards: no such file or directory`. Same class of issue
as component #2's missing output directory — already fixed with a
tracked `.gitkeep`, but worth recognizing immediately if it ever
resurfaces after adding a new dashboard-only directory elsewhere.

## 4. Verify

Open `http://localhost:3000` from Windows — no login required
(anonymous viewer access is enabled for this local-only lab; admin
credentials exist for editing, see the topology file). The "NetMind"
folder should show the provisioned dashboard with live panels
reflecting `srl1`/`srl2` interface state, sourced from the same
Prometheus scrape verified in component #3's setup doc.

That's the exit criterion — the pipeline visibly real, not just
checkable through `tail -f` and ad hoc PromQL. Full design detail:
`grafana/README.md`.
