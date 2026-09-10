# grafana/

Component #4 — dashboards on top of Prometheus. Lowest design complexity
of the pipeline so far: the point isn't new protocol learning, it's
making components #1&ndash;3 visibly real instead of only checkable
through `tail -f` and PromQL ad-hoc queries.

## Design decisions (2026-09-10)

- **Deployment: containerized, in the topology.** Added as its own node
  (`grafana`) in `lab/topologies/netmind-2node.clab.yml`, same pattern as
  `gnmic` and `prometheus` &mdash; stood up/torn down with the rest of the
  lab rather than living as a separate long-running process.
- **Dashboards: provisioned as code, not built in the UI.** Datasource
  and dashboard JSON both live in this folder and are bind-mounted into
  the container, auto-loaded on start via Grafana's provisioning system.
  Matches how `gnmic.yaml` and `prometheus.yml` are already handled &mdash;
  the dashboard is reproducible from a fresh `clab deploy`, not something
  that has to be re-clicked together after every `clab destroy`.
- **Anonymous viewer access enabled.** `GF_AUTH_ANONYMOUS_ENABLED=true`
  so the dashboard is viewable at `http://localhost:3000` without a
  login prompt for a single-user local lab. Admin credentials are still
  set (`admin` / see the topology file) for editing. Not a production
  posture &mdash; fine here because nothing on this container is exposed
  past `localhost`.

**Known gotcha:** `dashboards/` starts out empty (no dashboard JSON has
been committed yet), and git doesn't track empty directories — so
without a placeholder file the folder simply doesn't exist after a
fresh clone/sync, and `clab deploy`'s bind-mount validation fails with
`Failed to verify bind path: stat .../grafana/dashboards: no such file
or directory`. Same class of issue as `telemetry/output/`'s missing
directory in component #2 — fixed the same way, with a tracked
`.gitkeep` so the directory always exists even while it's empty.

## Layout

- `provisioning/datasources/prometheus.yml` &mdash; points Grafana at the
  `prometheus` container by its containerlab DNS name, auto-loaded on
  start.
- `provisioning/dashboards/dashboards.yml` &mdash; tells Grafana to load
  any dashboard JSON found in `dashboards/` into a "NetMind" folder.
- `dashboards/` &mdash; the actual dashboard JSON files.

## Running it

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/lab/topologies
sudo clab deploy -t netmind-2node.clab.yml
```

## Verifying it

Open `http://localhost:3000` from Windows. No login required (anonymous
viewer). The NetMind folder should show the provisioned dashboard with
live panels reflecting `srl1`/`srl2` interface state, sourced from the
same Prometheus scrape verified in component #3.
