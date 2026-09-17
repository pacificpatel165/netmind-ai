"""NetMind AI — component #9, automated tests for gate.py
(BACKLOG.md item 30, added 2026-09-17).

Scope: `proposal_hash()`, the audit-log writers, and the default-deny
decision logic -- all pure/mockable, no live device or LLM needed.
`diagnose_and_propose()` and `execute()` are mocked here specifically
so these tests can run standalone; the real end-to-end path (a real
fault, a real approval, a real device-state change) stays exactly
where it belongs, in TESTING.md, verified against the live lab.

Run:
    cd intelligence/security-gate
    source .venv/bin/activate
    pytest test_gate.py -v
"""

import json
from unittest.mock import patch

import pytest

import gate


def _sample_record(rationale_text="rationale A"):
    return {
        "interface": "ethernet-1/1",
        "node_ip": "172.100.100.11",
        "yang_path": "/interface[name=ethernet-1/1]/admin-state",
        "current_value": "disable",
        "proposed_value": "enable",
        "json_rpc_set_payload": {"jsonrpc": "2.0", "id": 1, "method": "set", "params": {}},
        "netconf_edit_config_xml": "<rpc/>",
        "netconf_commit_xml": "<rpc/>",
        "executed": False,
        "rationale": rationale_text,
    }


def test_proposal_hash_excludes_rationale():
    # The exact behavior PROGRESS_LOG entry 40 proved live, and that an
    # earlier version of this project's own testing instructions got
    # wrong (see that entry) -- pinned here so it can never silently
    # regress again.
    record_a = _sample_record(rationale_text="the model said X")
    record_b = _sample_record(rationale_text="a completely different explanation entirely")
    assert gate.proposal_hash(record_a) == gate.proposal_hash(record_b)


def test_proposal_hash_changes_with_a_deterministic_field():
    record_a = _sample_record()
    record_b = _sample_record()
    record_b["current_value"] = "enable"  # a real deterministic-field change
    assert gate.proposal_hash(record_a) != gate.proposal_hash(record_b)


def test_proposal_hash_is_stable_regardless_of_dict_key_order():
    record = _sample_record()
    reordered = dict(reversed(list(record.items())))
    assert gate.proposal_hash(record) == gate.proposal_hash(reordered)


@pytest.fixture
def audit_log(tmp_path, monkeypatch):
    path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(gate, "AUDIT_LOG_PATH", path)
    return path


def test_append_decision_entry_writes_correct_schema(audit_log):
    record = _sample_record()
    gate.append_decision_entry(record, decision="approved", decided_by="test-user")
    lines = audit_log.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event"] == "decision"
    assert entry["decision"] == "approved"
    assert entry["decided_by"] == "test-user"
    assert entry["proposal_hash"] == gate.proposal_hash(record)
    assert entry["rationale_included"] is True


def test_append_execution_entry_writes_correct_schema_and_correlates_to_decision(audit_log):
    record = _sample_record()
    gate.append_decision_entry(record, decision="approved", decided_by="test-user")
    gate.append_execution_entry(record, protocol="json-rpc", success=True, detail="confirmed device state: enable")
    lines = audit_log.read_text().strip().splitlines()
    assert len(lines) == 2
    decision_entry = json.loads(lines[0])
    execution_entry = json.loads(lines[1])
    assert execution_entry["event"] == "execution"
    assert execution_entry["protocol"] == "json-rpc"
    assert execution_entry["success"] is True
    # The correlation this project's audit trail relies on: same hash,
    # two events, never one mutated entry (append-only design).
    assert execution_entry["proposal_hash"] == decision_entry["proposal_hash"]


def test_append_execution_entry_records_failures_too(audit_log):
    # A failed execution is exactly the kind of event this audit trail
    # exists to capture, not something to leave unrecorded (gate.py's
    # own docstring) -- pinned so a future edit can't quietly make
    # failures silent.
    record = _sample_record()
    gate.append_execution_entry(record, protocol="netconf", success=False, detail="mocked ExecutionError")
    entry = json.loads(audit_log.read_text().strip())
    assert entry["success"] is False
    assert entry["detail"] == "mocked ExecutionError"


def test_gate_rejects_on_blank_input(audit_log, monkeypatch):
    # Default-deny, literally -- PROGRESS_LOG entry 40's real proof,
    # pinned here so it runs on every future change without needing
    # the live lab up.
    monkeypatch.setattr("builtins.input", lambda _: "")
    with patch.object(gate, "diagnose_and_propose", return_value=_sample_record()), \
         patch.object(gate, "execute") as mock_execute:
        gate.gate("172.100.100.11", "ethernet-1/1")
        mock_execute.assert_not_called()
    entry = json.loads(audit_log.read_text().strip())
    assert entry["decision"] == "rejected"


def test_gate_rejects_on_anything_other_than_y_or_yes(audit_log, monkeypatch):
    # "Y " / "  yes  " are deliberately NOT in this list -- gate.py's
    # own .strip().lower() correctly treats those as approval, and an
    # earlier version of this test wrongly asserted otherwise (caught
    # by actually running the test, not by re-reading it more closely
    # -- see PROGRESS_LOG entry 40 for this project's other example of
    # exactly this class of mistake).
    for junk_answer in ("n", "no", "maybe", "approve", ""):
        monkeypatch.setattr("builtins.input", lambda _, a=junk_answer: a)
        with patch.object(gate, "diagnose_and_propose", return_value=_sample_record()), \
             patch.object(gate, "execute") as mock_execute:
            gate.gate("172.100.100.11", "ethernet-1/1")
            mock_execute.assert_not_called()


def test_gate_approves_and_executes_on_y_or_yes(audit_log, monkeypatch):
    for good_answer in ("y", "Y", "yes", "YES"):
        monkeypatch.setattr("builtins.input", lambda _, a=good_answer: a)
        with patch.object(gate, "diagnose_and_propose", return_value=_sample_record()), \
             patch.object(gate, "execute", return_value={"confirmed_value": "enable"}) as mock_execute:
            gate.gate("172.100.100.11", "ethernet-1/1")
            mock_execute.assert_called_once()


def test_gate_does_nothing_when_already_in_desired_state(audit_log, monkeypatch):
    # diagnose_and_propose() returning None means "nothing to propose" --
    # gate() must not prompt for approval or touch the audit log at all.
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("should not prompt")))
    with patch.object(gate, "diagnose_and_propose", return_value=None):
        gate.gate("172.100.100.11", "ethernet-1/1")
    assert not audit_log.exists()
