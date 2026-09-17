"""Automated tests for component #5 (anomaly-detection), added 2026-09-17
as part of closing BACKLOG.md item 30b.

Scope, same discipline as items 30's tests: only the pure/mockable logic
-- series_by_interface()'s label-key handling (a direct regression test
for the real interface_name/name bug found live 2026-09-13, entry 26/27)
and evaluate_leaf()'s z-score math, especially the sd==0 guard. This does
NOT need a container or the live lab -- detector.py's only dependencies
are `requests` and `prometheus_client`, both plain host-installable, so
unlike ingest.py/query.py (component #6) there was no real reason this
needed a different pattern than components #7-#10's host-venv pytest.

Prometheus itself is mocked at the `detector.query()` boundary (a plain
`requests.get` wrapper) -- no live Prometheus needed.
"""

from unittest.mock import patch

import detector


def _series(pairs):
    """Build a fake Prometheus /api/v1/query `result` list.

    pairs: list of (interface_name_or_None, value) tuples. A None label
    key means "no interface_name label present at all" (the real shape
    a malformed/mislabeled series would have).
    """
    out = []
    for iface, value in pairs:
        metric = {"interface_name": iface} if iface is not None else {}
        out.append({"metric": metric, "value": [0, str(value)]})
    return out


class TestSeriesByInterface:
    def test_maps_interface_name_label_to_value(self):
        results = _series([("ethernet-1/1", 123.45), ("ethernet-1/2", 0.0)])
        assert detector.series_by_interface(results) == {
            "ethernet-1/1": 123.45,
            "ethernet-1/2": 0.0,
        }

    def test_missing_interface_name_label_defaults_to_unknown(self):
        # Direct regression test for the real 2026-09-13 bug: the code
        # used to read the wrong label key entirely and silently bucket
        # every series under "unknown". This confirms the *current*
        # correct key is what's read, and that a genuinely absent label
        # still degrades safely rather than raising.
        results = _series([(None, 5.0)])
        assert detector.series_by_interface(results) == {"unknown": 5.0}

    def test_empty_results_returns_empty_dict(self):
        assert detector.series_by_interface([]) == {}


class TestEvaluateLeaf:
    def _run(self, current, mean, stddev):
        """Call evaluate_leaf() with detector.query() mocked to return
        `current`, then `mean`, then `stddev` in that call order (matching
        evaluate_leaf()'s own three query() calls)."""
        with patch.object(detector, "query", side_effect=[current, mean, stddev]):
            detector.evaluate_leaf("in_octets")

    def test_zscore_computed_against_baseline(self):
        current = _series([("ethernet-1/1", 200.0)])
        mean = _series([("ethernet-1/1", 100.0)])
        stddev = _series([("ethernet-1/1", 25.0)])
        self._run(current, mean, stddev)

        # z = (200 - 100) / 25 = 4.0
        z = detector.anomaly_score.labels(interface="ethernet-1/1", stat="in_octets")._value.get()
        assert z == 4.0

        flagged = detector.anomaly_detected.labels(interface="ethernet-1/1", stat="in_octets")._value.get()
        assert flagged == 1  # |4.0| > default ZSCORE_THRESHOLD (3.0)

    def test_zero_stddev_scores_zero_instead_of_dividing_by_zero(self):
        # The exact scenario detector.py's own comment calls out: a flat
        # interface with no baseline variance yet. Must not raise
        # ZeroDivisionError and must not falsely flag an anomaly.
        current = _series([("ethernet-1/2", 42.0)])
        mean = _series([("ethernet-1/2", 42.0)])
        stddev = _series([("ethernet-1/2", 0.0)])
        self._run(current, mean, stddev)

        z = detector.anomaly_score.labels(interface="ethernet-1/2", stat="in_octets")._value.get()
        assert z == 0.0
        flagged = detector.anomaly_detected.labels(interface="ethernet-1/2", stat="in_octets")._value.get()
        assert flagged == 0

    def test_interface_with_no_baseline_series_defaults_mean_and_stddev_to_zero(self):
        # current has a series for an interface that never showed up in
        # the mean/stddev query results at all (e.g. brand new interface,
        # baseline window not built up yet) -- must not KeyError.
        current = _series([("ethernet-1/9", 10.0)])
        mean = _series([])
        stddev = _series([])
        self._run(current, mean, stddev)

        z = detector.anomaly_score.labels(interface="ethernet-1/9", stat="in_octets")._value.get()
        assert z == 0.0  # sd defaults to 0.0 -> the divide-by-zero guard applies
