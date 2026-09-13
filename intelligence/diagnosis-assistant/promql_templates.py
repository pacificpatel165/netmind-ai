"""NetMind AI — component #7, diagnosis assistant.

The "fixed" half of the hybrid PromQL strategy (PROGRESS_LOG entry 21):
a small, hand-written set of parameterized queries for the question
shapes we actually expect. Deliberately narrow — this is the safe,
testable path that should cover most real questions; anything it
can't match falls through to router.py's LLM-generated-PromQL
fallback, not an ever-growing template list.

Label key correction (2026-09-13): the raw gnmic-sourced metrics label
the interface as `interface_name`, not `name` -- confirmed directly
against Prometheus (`curl .../api/v1/query?query=...in_error_packets`).
The first version of this file assumed `name` by copying component
#5's detector.py, which had the same wrong assumption -- both are
fixed together, see detector.py's own docstring and PROGRESS_LOG.md.
"""

METRIC_PREFIX = "netmind_interface_state_srl_nokia_interfaces_interface_statistics_"


def error_rate(interface: str, window: str = "15m") -> str:
    """Combined in+out error-packet rate for one interface."""
    return (
        f'sum(rate({METRIC_PREFIX}in_error_packets{{interface_name="{interface}"}}[{window}])) '
        f'+ sum(rate({METRIC_PREFIX}out_error_packets{{interface_name="{interface}"}}[{window}]))'
    )


def discard_rate(interface: str, window: str = "15m") -> str:
    """Combined in+out discarded-packet rate for one interface."""
    return (
        f'sum(rate({METRIC_PREFIX}in_discarded_packets{{interface_name="{interface}"}}[{window}])) '
        f'+ sum(rate({METRIC_PREFIX}out_discarded_packets{{interface_name="{interface}"}}[{window}]))'
    )


def flap_history(interface: str, window: str = "15m") -> str:
    """Link + carrier transition count over the window (increase, not rate —
    a count of events is more directly answerable than a per-second rate
    for "has this interface been flapping" questions)."""
    return (
        f'sum(increase({METRIC_PREFIX}link_transitions{{interface_name="{interface}"}}[{window}])) '
        f'+ sum(increase({METRIC_PREFIX}carrier_transitions{{interface_name="{interface}"}}[{window}]))'
    )


def octet_rate(interface: str, window: str = "15m") -> str:
    """Combined in+out byte rate for one interface -- the basic "how much
    traffic" question. Added 2026-09-13 after the LLM-generated-PromQL
    fallback failed on exactly this question (invalid syntax: it tried
    `by {...}` on a bare range vector, which isn't legal PromQL anywhere
    -- `by` only follows an aggregation function, with parentheses, not
    braces). Traffic volume is common enough to deserve a template
    rather than depend on the model getting aggregation syntax right."""
    return (
        f'sum(rate({METRIC_PREFIX}in_octets{{interface_name="{interface}"}}[{window}])) '
        f'+ sum(rate({METRIC_PREFIX}out_octets{{interface_name="{interface}"}}[{window}]))'
    )


def anomaly_score(interface: str, stat: str | None = None) -> str:
    """Current z-score(s) from component #5's anomaly detector for this
    interface, optionally narrowed to one stat (e.g. "carrier_transitions")."""
    if stat:
        return f'netmind_anomaly_score{{interface="{interface}", stat="{stat}"}}'
    return f'netmind_anomaly_score{{interface="{interface}"}}'


def anomaly_flagged(interface: str) -> str:
    """Which stats are currently flagged (=1) for this interface."""
    return f'netmind_anomaly_detected{{interface="{interface}"}} == 1'


# Keyword -> template function. router.py matches on these; order matters
# only in that the first keyword match wins, so more specific terms
# ("flap", "anomaly") are listed ahead of generic ones.
KEYWORD_TEMPLATES = {
    "flap": flap_history,
    "transition": flap_history,
    "carrier": flap_history,
    "anomaly": anomaly_score,
    "z-score": anomaly_score,
    "zscore": anomaly_score,
    "error": error_rate,
    "discard": discard_rate,
    "drop": discard_rate,
    "traffic": octet_rate,
    "octet": octet_rate,
    "throughput": octet_rate,
    "bandwidth": octet_rate,
}
