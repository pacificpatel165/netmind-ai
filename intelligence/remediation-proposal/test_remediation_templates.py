"""NetMind AI — component #8, automated tests for remediation_templates.py
(BACKLOG.md item 30, added 2026-09-17).

Scope, deliberately: `interface_admin_up()` is a pure function -- no
device connection, no Prometheus, nothing live. But it builds the
exact payload shapes this project fired for real, by hand, against
srl1 (PROGRESS_LOG entries 31 and 33), and a config-push executor
(component #10) now fires whatever this function returns without
re-deriving it. A silent change here -- a typo'd field name, a
namespace edit, a dropped commit RPC -- would not be caught by any
live test unless someone happened to run the exact same scenario
again. These tests pin the exact shapes already proven live, so any
future edit that changes them fails loudly and immediately, not
three components downstream.

Run:
    cd intelligence/remediation-proposal
    source .venv/bin/activate
    pytest test_remediation_templates.py -v
"""

import remediation_templates as templates


def test_interface_admin_up_returns_all_expected_fields():
    record = templates.interface_admin_up("ethernet-1/1", current_value="disable")
    for field in (
        "interface", "yang_path", "current_value", "proposed_value",
        "json_rpc_set_payload", "netconf_edit_config_xml",
        "netconf_commit_xml", "executed",
    ):
        assert field in record


def test_interface_admin_up_executed_always_starts_false():
    # Load-bearing, not a formality (per this module's own docstring) --
    # nothing in component #8 is allowed to claim a change was applied.
    record = templates.interface_admin_up("ethernet-1/1", current_value="disable")
    assert record["executed"] is False


def test_yang_path_matches_live_verified_shape():
    record = templates.interface_admin_up("ethernet-1/1", current_value="disable")
    assert record["yang_path"] == "/interface[name=ethernet-1/1]/admin-state"


def test_current_value_is_passed_through_not_requeried():
    # interface_admin_up() must trust the caller's current_value, not
    # silently re-derive it -- state_client.py owns reading device
    # state, this function only owns building the record (see this
    # module's own docstring on why that split matters).
    record = templates.interface_admin_up("ethernet-1/1", current_value="disable")
    assert record["current_value"] == "disable"
    assert record["proposed_value"] == "enable"


def test_json_rpc_set_payload_matches_live_verified_shape():
    # Exact shape fired for real against srl1 and confirmed working,
    # PROGRESS_LOG entry 31 -- and again via component #10's live
    # execution test, entry 42. A change here must be deliberate.
    record = templates.interface_admin_up("ethernet-1/1", current_value="disable")
    assert record["json_rpc_set_payload"] == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "set",
        "params": {
            "commands": [
                {"action": "update", "path": "/interface[name=ethernet-1/1]/admin-state", "value": "enable"}
            ]
        },
    }


def test_netconf_edit_config_xml_matches_live_verified_shape():
    # Namespace confirmed directly from srl1's own NETCONF <hello>
    # exchange (entry 32), not guessed -- and the candidate-target,
    # two-phase (edit-config then separate commit) structure proven
    # necessary the hard way (entry 33: edit-config alone returned
    # <ok/> but left device state unchanged).
    record = templates.interface_admin_up("ethernet-1/1", current_value="disable")
    xml = record["netconf_edit_config_xml"]
    assert 'xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"' in xml
    assert "<edit-config>" in xml
    assert "<target><candidate/></target>" in xml
    assert 'xmlns="urn:nokia.com:srlinux:chassis:interfaces"' in xml
    assert "<name>ethernet-1/1</name>" in xml
    assert "<admin-state>enable</admin-state>" in xml


def test_netconf_commit_xml_is_a_separate_rpc():
    # This being separate from edit-config is the whole point of entry
    # 33's finding -- a regression that merged them back together (or
    # dropped the commit RPC) would look identical to a diff-review but
    # silently break the "changes don't apply without commit" behavior.
    record = templates.interface_admin_up("ethernet-1/1", current_value="disable")
    assert "<commit/>" in record["netconf_commit_xml"]
    assert "edit-config" not in record["netconf_commit_xml"]


def test_different_interfaces_produce_different_paths():
    a = templates.interface_admin_up("ethernet-1/1", current_value="disable")
    b = templates.interface_admin_up("ethernet-2/3", current_value="disable")
    assert a["yang_path"] != b["yang_path"]
    assert a["json_rpc_set_payload"]["params"]["commands"][0]["path"] != \
        b["json_rpc_set_payload"]["params"]["commands"][0]["path"]
