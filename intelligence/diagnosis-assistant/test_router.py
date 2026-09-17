"""NetMind AI — component #7, automated tests for the deterministic
routing logic (BACKLOG.md item 30, added 2026-09-17).

Scope, deliberately: `match_template()` and `extract_interface()` are
pure functions with zero live dependency (no Prometheus, no Ollama) --
exactly the kind of logic that's been manually eyeballed every session
instead of just... run. `generate_and_validate()` and `resolve_metrics()`
are NOT covered here since they need a real Prometheus connection or a
real/mocked LLM call -- that's still `TESTING.md` territory, correctly,
not a gap.

Run:
    cd intelligence/diagnosis-assistant
    source .venv/bin/activate  # or install pytest into it first
    pytest test_router.py -v
"""

import router


def test_extract_interface_finds_real_naming_pattern():
    assert router.extract_interface("what about ethernet-1/1?") == "ethernet-1/1"
    assert router.extract_interface("and ethernet-2/3 too") == "ethernet-2/3"


def test_extract_interface_returns_none_when_absent():
    assert router.extract_interface("what's the traffic rate overall?") is None


def test_match_template_returns_none_without_an_interface():
    # A keyword match with no interface name is not enough -- every
    # template function requires an interface argument.
    assert router.match_template("any errors lately?") is None


def test_match_template_flap_keywords_route_to_flap_history():
    # "flap", "transition", "carrier" all route to the same template --
    # this is the exact keyword set PROGRESS_LOG entry 24/28 built and
    # entry 37 exercised live.
    expected = router.templates.flap_history("ethernet-1/1")
    for question in (
        "has ethernet-1/1 been flapping?",
        "any transition history for ethernet-1/1?",
        "carrier issues on ethernet-1/1?",
    ):
        assert router.match_template(question) == expected


def test_match_template_traffic_keywords_route_to_octet_rate():
    # This exact keyword set (traffic/octet/throughput/bandwidth) was
    # added in entry 28 specifically because the LLM fallback failed on
    # "what's the traffic rate" -- a regression here would silently
    # reopen that exact bug.
    expected = router.templates.octet_rate("ethernet-1/1")
    for question in (
        "what's the current traffic rate on ethernet-1/1?",
        "octet count for ethernet-1/1",
        "throughput on ethernet-1/1 right now",
        "bandwidth usage for ethernet-1/1",
    ):
        assert router.match_template(question) == expected


def test_match_template_error_and_discard_are_distinct_templates():
    assert router.match_template("errors on ethernet-1/1?") == router.templates.error_rate("ethernet-1/1")
    assert router.match_template("any discards on ethernet-1/1?") == router.templates.discard_rate("ethernet-1/1")
    assert router.match_template("drops on ethernet-1/1?") == router.templates.discard_rate("ethernet-1/1")


def test_match_template_anomaly_keywords():
    expected = router.templates.anomaly_score("ethernet-1/1")
    for question in (
        "any anomaly on ethernet-1/1?",
        "z-score for ethernet-1/1",
        "zscore ethernet-1/1",
    ):
        assert router.match_template(question) == expected


def test_match_template_returns_none_for_genuinely_off_template_question():
    # A real off-template question -- has an interface, but no known
    # keyword. This is the case that's supposed to fall through to the
    # LLM-generated-PromQL path in resolve_metrics(), not silently
    # match something wrong.
    assert router.match_template("describe ethernet-1/1 to me") is None


def test_known_metrics_list_includes_every_template_leaf():
    # Regression guard: generate_and_validate()'s prompt tells the LLM
    # fallback exactly which metric names it may use (KNOWN_METRICS).
    # If a new template is ever added to promql_templates.py without
    # its underlying metric also being added here, the fallback path
    # would silently be told a narrower truth than the templates know.
    for leaf_metric in (
        "netmind_interface_state_srl_nokia_interfaces_interface_statistics_in_octets",
        "netmind_interface_state_srl_nokia_interfaces_interface_statistics_out_octets",
        "netmind_interface_state_srl_nokia_interfaces_interface_statistics_link_transitions",
        "netmind_interface_state_srl_nokia_interfaces_interface_statistics_carrier_transitions",
    ):
        assert leaf_metric in router.KNOWN_METRICS
