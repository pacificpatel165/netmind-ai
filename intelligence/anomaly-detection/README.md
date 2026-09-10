# intelligence/anomaly-detection/

Component #5 — the first piece of the intelligence layer (phase 5).
Closes out phase 4 (telemetry: #1&ndash;4) and opens the part of the
roadmap that isn't just wiring an existing tool together.

## Design decisions (2026-09-10)

- **Scope: interface counters only**, reusing the metrics already in
  the pipeline &mdash; traffic rate, errors, discards, link/carrier
  transitions (see `telemetry/collectors/gnmic.yaml`). No new
  telemetry, no new subscription paths. Admin/oper state changes are
  a more binary signal and a natural candidate for stage 2, not
  needed to prove the pattern first.
- **Rolling baseline, no ML/LLM yet.** A z-score against a rolling
  mean/stddev (`avg_over_time` / `stddev_over_time` over
  `BASELINE_WINDOW`, default 15m) is the whole algorithm. The roadmap
  explicitly sequences a real model (isolation forest or similar)
  *after* this baseline's real-world limits are understood, not
  before &mdash; guessing at model choice with zero real anomaly data
  to validate against would be backwards.
- **Statistics computed by Prometheus, not reimplemented in Python.**
  `avg_over_time`/`stddev_over_time` are native PromQL subquery
  functions; this service's job is orchestration (which metrics,
  which window, which threshold, turning the result into its own
  metric) rather than pulling raw samples and recomputing statistics
  Prometheus already provides.
- **A standalone service, not a Prometheus recording rule.** A
  recording rule could do the same avg/stddev/z-score math in pure
  config, no new container. Deliberately not chosen: this component's
  whole point is to *become* the real-model version later, and a
  recording rule has nowhere to put a trained model &mdash; a service
  does. Building the throwaway version as a recording rule would mean
  discarding it rather than evolving it.
- **Writes back to Prometheus as its own metrics** (`netmind_anomaly_*`
  on port 9805, scraped like every other component), not a separate
  file/log. Zero new dashboard plumbing &mdash; it shows up in Grafana
  the same way Prometheus itself did in component #4.
- **Directory structure: `intelligence/`, not a bare top-level folder.**
  Components #6&ndash;8 (retrieval index, diagnosis assistant,
  remediation proposal) are also intelligence-layer components per
  `PROGRESS_LOG.md`'s Component map &mdash; grouping now avoids a
  reshuffle later.

## Layout

- `detector.py` &mdash; the whole service: queries Prometheus for
  current rate + rolling mean/stddev per watched counter, computes a
  z-score per interface, exposes it back as Prometheus gauges.
- `requirements.txt`, `Dockerfile` &mdash; this is project code, not an
  off-the-shelf image, so it has to be built locally (see below)
  rather than pulled.

## Metrics this service exposes (`:9805/metrics`)

| Metric | Meaning |
|---|---|
| `netmind_anomaly_score{interface,stat}` | z-score of the current rate vs. the rolling baseline |
| `netmind_anomaly_detected{interface,stat}` | 1 if `\|z-score\|` exceeds `ZSCORE_THRESHOLD` (default 3.0), else 0 |
| `netmind_anomaly_baseline_mean{interface,stat}` | the rolling mean used for the z-score |
| `netmind_anomaly_baseline_stddev{interface,stat}` | the rolling standard deviation used for the z-score |

`stat` is one of the watched counter leaves (`in_octets`,
`out_error_packets`, `link_transitions`, &hellip;) &mdash; see
`WATCHED_LEAVES` in `detector.py` for the full list.

## Building the image (required before first deploy)

Unlike `gnmic`, `prometheus`, and `grafana`, there's no public image
to pull for this one &mdash; it has to be built locally once:

```bash
cd ~/netmind-lab/intelligence/anomaly-detection
docker build -t netmind-anomaly-detector:latest .
```

Do this from the native-fs copy (`~/netmind-lab/...`), same DrvFs
reason as everything else in this lab &mdash; run
`scripts/sync-to-lab.sh` first if you haven't already this session.
Rebuild any time `detector.py` or `requirements.txt` changes; `clab
deploy` won't pick up code changes on its own since the image is
tagged `:latest` locally, not re-pulled.

## Running it

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/intelligence/anomaly-detection
docker build -t netmind-anomaly-detector:latest .
cd ~/netmind-lab/lab/topologies
sudo clab deploy -t netmind-2node.clab.yml
```

## Verifying it

```bash
curl -s http://localhost:9805/metrics | grep netmind_anomaly
```

Should show `netmind_anomaly_score`/`_detected`/`_baseline_mean`/
`_baseline_stddev` series for every interface/stat combination once
the first evaluation cycle completes (`EVAL_INTERVAL_SECONDS`, default
30s, after container start). Everything should read `z &asymp; 0` /
`detected = 0` on an idle lab link &mdash; that's the expected healthy
state, not a sign nothing is working. The Grafana "Anomaly detection"
row (see `grafana/dashboards/netmind-overview.json`) shows the same
data without needing `curl`.

That's the exit criterion for component #5 stage 1: real z-scores
computed against real rolling baselines, visible in both Prometheus
and Grafana, sitting near zero on a quiet lab.
