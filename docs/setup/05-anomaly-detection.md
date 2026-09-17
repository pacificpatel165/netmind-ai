# Component #5 setup: anomaly detection

Step-by-step "how" per this folder's convention. For the *why* —
rolling z-score baseline before any real model, statistics computed by
Prometheus rather than reimplemented in Python — see
`intelligence/anomaly-detection/README.md` and `PROGRESS_LOG.md`
entries dated 2026-09-10, 2026-09-13.

Prerequisite: components #1–4 (lab, telemetry, metrics, dashboards) are
deployed and verified — this component queries Prometheus, which needs
real data flowing first.

---

## 1. Build the image (required before first deploy)

Unlike `gnmic`/`prometheus`/`grafana`, this is project code — no public
image to pull:

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/intelligence/anomaly-detection
docker build -t netmind-anomaly-detector:latest .
```

Rebuild any time `detector.py` or its `requirements.txt` changes —
`clab deploy` won't pick up code changes on its own since the image is
tagged `:latest` locally, not re-pulled.

## 2. Deploy

```bash
cd ~/netmind-lab/lab/topologies
sudo clab deploy -t netmind-2node.clab.yml
```

## 3. Verify

```bash
curl -s http://localhost:9805/metrics | grep netmind_anomaly
```

Should show `netmind_anomaly_score`/`_detected`/`_baseline_mean`/
`_baseline_stddev` series for every interface/stat combination once the
first evaluation cycle completes (`EVAL_INTERVAL_SECONDS`, default 30s,
after container start). Reading `z ≈ 0` / `detected = 0` on an idle
lab link is the expected healthy state, not a sign nothing is working.
The Grafana "Anomaly detection" dashboard row shows the same data
without needing `curl`.

That's the exit criterion — real z-scores against real rolling
baselines, visible in both Prometheus and Grafana. Full design detail
and the exposed-metrics table: `intelligence/anomaly-detection/README.md`.

## 4. Automated tests (optional, no lab needed)

Since 2026-09-17 (`BACKLOG.md` item 30b), `test_detector.py` covers
this component's pure logic (z-score math, the `interface_name` label
handling) with Prometheus mocked — no lab or deploy required. Uses the
shared venv at `intelligence/.venv` (item 32) — see
`docs/testing/TESTING.md`'s "Automated tests" section for setup.
