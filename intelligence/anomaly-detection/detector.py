"""NetMind AI — component #5, anomaly detection, stage 1.

Rolling-baseline z-score detector, no ML/LLM: per the roadmap, a
statistical baseline comes first, and a real model (isolation forest or
similar) is only worth adding once this baseline's actual limits are
understood from real data.

Design (2026-09-10): rather than pull raw samples out of Prometheus and
compute statistics in Python, the baseline mean/stddev are computed by
Prometheus itself via PromQL's avg_over_time/stddev_over_time subquery
functions — this service's job is orchestration (which metrics, which
window, which threshold) and turning the result back into a metric,
not reimplementing what Prometheus already does natively. A Prometheus
recording rule could technically do the avg/stddev/z-score math too,
but a standalone service was chosen deliberately: it's the same shape
this component will keep once the "real model" replaces the z-score
math internally — a recording rule can't host a trained model, a
service can, so this isn't throwaway scaffolding.

Bug found and fixed 2026-09-13 (while building component #7, which
queries these same raw metrics directly and hit it first): the actual
label gnmic attaches to each interface series is `interface_name`, not
`name`. `series_by_interface()`/`evaluate_leaf()` were reading the
wrong key, which silently defaulted to "unknown" for every series --
meaning every anomaly Gauge this component has ever emitted was
labeled `interface="unknown"`, merging all interfaces (both nodes,
every port) into one bucket rather than distinguishing them. This
went unnoticed through this component's original "verified" closeout
because something still rendered on the Grafana dashboard -- the bug
was in per-interface labeling, not in whether data flowed at all, so
a visual check didn't catch it. See PROGRESS_LOG.md for the full
writeup of how this was found.
"""

import logging
import os
import time

import requests
from prometheus_client import Gauge, start_http_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("netmind-anomaly-detector")

PROM_URL = os.environ.get("PROMETHEUS_URL", "http://clab-netmind-2node-prometheus:9090")
EVAL_INTERVAL_SECONDS = int(os.environ.get("EVAL_INTERVAL_SECONDS", "30"))
BASELINE_WINDOW = os.environ.get("BASELINE_WINDOW", "15m")
ZSCORE_THRESHOLD = float(os.environ.get("ZSCORE_THRESHOLD", "3.0"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9805"))

# Matches component #2/#3's naming convention: metric-prefix "netmind" +
# subscription name "interface-state" + the srl_nokia path, underscored.
METRIC_PREFIX = "netmind_interface_state_srl_nokia_interfaces_interface_statistics_"

# Deliberately just the counters gnmic already streams — see
# telemetry/collectors/gnmic.yaml. No new telemetry for stage 1.
WATCHED_LEAVES = [
    "in_octets",
    "out_octets",
    "in_packets",
    "out_packets",
    "in_error_packets",
    "out_error_packets",
    "in_discarded_packets",
    "out_discarded_packets",
    "link_transitions",
    "carrier_transitions",
]

anomaly_score = Gauge(
    "netmind_anomaly_score",
    "Z-score of the current per-second rate vs its rolling baseline",
    ["interface", "stat"],
)
anomaly_detected = Gauge(
    "netmind_anomaly_detected",
    "1 if |z-score| exceeds ZSCORE_THRESHOLD, else 0",
    ["interface", "stat"],
)
baseline_mean = Gauge(
    "netmind_anomaly_baseline_mean",
    "Rolling baseline mean (avg_over_time) used for the z-score",
    ["interface", "stat"],
)
baseline_stddev = Gauge(
    "netmind_anomaly_baseline_stddev",
    "Rolling baseline standard deviation (stddev_over_time) used for the z-score",
    ["interface", "stat"],
)


def query(promql: str):
    resp = requests.get(f"{PROM_URL}/api/v1/query", params={"query": promql}, timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload}")
    return payload["data"]["result"]


def series_by_interface(results) -> dict:
    return {s["metric"].get("interface_name", "unknown"): float(s["value"][1]) for s in results}


def evaluate_leaf(leaf: str) -> None:
    metric = f"{METRIC_PREFIX}{leaf}"
    current = query(f"rate({metric}[1m])")
    mean = query(f"avg_over_time(rate({metric}[1m])[{BASELINE_WINDOW}:1m])")
    stddev = query(f"stddev_over_time(rate({metric}[1m])[{BASELINE_WINDOW}:1m])")

    mean_by_iface = series_by_interface(mean)
    stddev_by_iface = series_by_interface(stddev)

    for series in current:
        iface = series["metric"].get("interface_name", "unknown")
        value = float(series["value"][1])
        m = mean_by_iface.get(iface, 0.0)
        sd = stddev_by_iface.get(iface, 0.0)

        # No baseline variance yet (e.g. a flat, idle interface, or not
        # enough history built up since startup) — score 0 rather than
        # divide by zero or flag a false anomaly on day one.
        z = 0.0 if sd == 0 else (value - m) / sd

        anomaly_score.labels(interface=iface, stat=leaf).set(z)
        baseline_mean.labels(interface=iface, stat=leaf).set(m)
        baseline_stddev.labels(interface=iface, stat=leaf).set(sd)

        flagged = 1 if abs(z) > ZSCORE_THRESHOLD else 0
        anomaly_detected.labels(interface=iface, stat=leaf).set(flagged)
        if flagged:
            log.warning(
                "anomaly: interface=%s stat=%s z=%.2f value=%.4f mean=%.4f stddev=%.4f",
                iface, leaf, z, value, m, sd,
            )


def main() -> None:
    log.info(
        "netmind-anomaly-detector starting: prometheus=%s interval=%ss window=%s threshold=%s",
        PROM_URL, EVAL_INTERVAL_SECONDS, BASELINE_WINDOW, ZSCORE_THRESHOLD,
    )
    start_http_server(LISTEN_PORT)
    while True:
        for leaf in WATCHED_LEAVES:
            try:
                evaluate_leaf(leaf)
            except Exception:
                log.exception("failed evaluating leaf=%s", leaf)
        time.sleep(EVAL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
