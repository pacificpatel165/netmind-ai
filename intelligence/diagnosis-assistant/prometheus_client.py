"""NetMind AI — component #7, diagnosis assistant.

Thin Prometheus query client. Same request shape as component #5's
detector.py (GET /api/v1/query, raise on non-success) — no reason to
reinvent it, just factored out so both the template path and the
LLM-fallback path share one place that talks to Prometheus.

Runs host-level (see README.md's placement decision), so it reaches
Prometheus via the port already published to the host in the topology
rather than a container-network hostname.
"""

import os

import requests

PROM_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")


class PrometheusQueryError(Exception):
    """Raised on a malformed query or a non-success Prometheus response —
    the signal router.py's LLM-fallback path uses to know a generated
    query was invalid and shouldn't be trusted."""


def query(promql: str, timeout: int = 10) -> list[dict]:
    resp = requests.get(f"{PROM_URL}/api/v1/query", params={"query": promql}, timeout=timeout)
    if resp.status_code != 200:
        # Prometheus returns 400 with a JSON body describing the parse
        # error for bad PromQL -- surface that message, it's exactly what
        # tells us an LLM-generated query was malformed.
        raise PrometheusQueryError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    payload = resp.json()
    if payload.get("status") != "success":
        raise PrometheusQueryError(str(payload))
    return payload["data"]["result"]


def format_result(result: list[dict]) -> str:
    """Render a query result as plain text for the LLM prompt -- no need
    for the model to parse Prometheus's JSON shape itself."""
    if not result:
        return "(no data returned for this query)"
    lines = []
    for series in result:
        labels = ", ".join(f"{k}={v}" for k, v in series["metric"].items())
        value = series["value"][1]
        lines.append(f"{{{labels}}} = {value}")
    return "\n".join(lines)
