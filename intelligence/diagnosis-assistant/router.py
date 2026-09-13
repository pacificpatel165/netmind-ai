"""NetMind AI — component #7, diagnosis assistant.

The hybrid router (PROGRESS_LOG entry 21): try a fixed template first,
fall back to asking the model to generate PromQL only when nothing
matches. This is the piece that makes the hybrid strategy real rather
than just a decision on paper.
"""

import re

import promql_templates as templates
from prometheus_client import PrometheusQueryError, format_result, query

# Matches SR Linux interface names like "ethernet-1/1". Deliberately
# narrow to this project's actual naming, not a generic pattern.
INTERFACE_PATTERN = re.compile(r"ethernet-\d+/\d+")

KNOWN_METRICS = [
    f"{templates.METRIC_PREFIX}{leaf}"
    for leaf in (
        "in_octets", "out_octets", "in_packets", "out_packets",
        "in_error_packets", "out_error_packets",
        "in_discarded_packets", "out_discarded_packets",
        "link_transitions", "carrier_transitions",
    )
] + ["netmind_anomaly_score", "netmind_anomaly_detected"]


def extract_interface(question: str) -> str | None:
    match = INTERFACE_PATTERN.search(question)
    return match.group(0) if match else None


def match_template(question: str) -> str | None:
    """Try every known keyword in order; return the first template match's
    PromQL, or None if nothing in the question matches a known shape."""
    interface = extract_interface(question)
    if not interface:
        return None
    q_lower = question.lower()
    for keyword, template_fn in templates.KEYWORD_TEMPLATES.items():
        if keyword in q_lower:
            return template_fn(interface)
    return None


def generate_and_validate(question: str, generate_fn) -> tuple[str | None, str | None]:
    """LLM-generated-PromQL fallback. `generate_fn` is injected (rather than
    importing ollama_client directly) so this stays testable without a
    live model. Returns (promql, error) — exactly one is set.

    Validation here means "does Prometheus accept it and return
    something", not "is it semantically the right query" -- that's a
    real limit of this stage-1 fallback, not an oversight, and is worth
    revisiting once this path actually gets exercised (see
    docs/roadmap/BACKLOG.md)."""
    prompt = (
        "Write ONE PromQL query, and nothing else -- no explanation, no "
        "markdown formatting, just the raw query -- that would help answer "
        "this question about a network interface. Only use these metric "
        "names, exactly as written:\n"
        + "\n".join(KNOWN_METRICS)
        + "\n\nTo filter by interface, use the label `interface_name` "
        '(e.g. `{interface_name="ethernet-1/1"}`), not `interface` or `name` '
        "-- confirmed directly against Prometheus, see promql_templates.py.\n"
        f"\nQuestion: {question}\nPromQL query:"
    )
    candidate = generate_fn(prompt).strip().strip("`").strip()
    try:
        query(candidate)
    except PrometheusQueryError as exc:
        return None, f"generated query rejected by Prometheus: {exc}"
    return candidate, None


def resolve_metrics(question: str, generate_fn) -> tuple[str | None, str, bool]:
    """Top-level entry point: returns (promql, result_text, used_fallback)."""
    promql = match_template(question)
    used_fallback = False
    if promql is None:
        used_fallback = True
        promql, error = generate_and_validate(question, generate_fn)
        if promql is None:
            return None, f"(no metrics retrieved: {error})", used_fallback
    try:
        result = query(promql)
    except PrometheusQueryError as exc:
        return promql, f"(query failed: {exc})", used_fallback
    return promql, format_result(result), used_fallback
