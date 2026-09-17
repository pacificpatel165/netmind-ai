"""NetMind AI — component #10, automated tests for executor.py
(BACKLOG.md item 30, added 2026-09-17).

Scope: `_parse_rpc_body()` (the direct regression test for the real
ncclient/lxml bug found and fixed live 2026-09-16, PROGRESS_LOG entry
43) and `execute()`'s protocol dispatch / always-reverify-device-state
behavior, with the actual RPC and HTTP calls mocked. The live-device
execution paths (`execute_json_rpc()`/`execute_netconf()` actually
talking to srl1) stay exactly where they belong -- live-verified in
TESTING.md and PROGRESS_LOG entries 42-43, not re-implemented as a
mock that could drift from what the real device actually does.

Run:
    cd intelligence/config-push-executor
    source .venv/bin/activate  # needs lxml -- see requirements.txt
    pytest test_executor.py -v
"""

from unittest.mock import patch

import pytest
from lxml import etree

import executor

SAMPLE_EDIT_CONFIG_XML = """<rpc message-id="101" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <edit-config>
    <target><candidate/></target>
    <config>
      <interface xmlns="urn:nokia.com:srlinux:chassis:interfaces">
        <name>ethernet-1/1</name>
        <admin-state>enable</admin-state>
      </interface>
    </config>
  </edit-config>
</rpc>"""

SAMPLE_COMMIT_XML = (
    '<rpc message-id="102" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">'
    "<commit/></rpc>"
)


def test_parse_rpc_body_returns_a_real_lxml_element():
    # The exact regression this test exists to catch: PROGRESS_LOG
    # entry 43 found that a stdlib xml.etree.ElementTree.Element fails
    # ncclient's internal etree.iselement() check silently, producing
    # "Invalid tag name" deep inside ncclient's own code. This asserts
    # the fix's actual contract, not just "it doesn't crash".
    result = executor._parse_rpc_body(SAMPLE_EDIT_CONFIG_XML)
    assert etree.iselement(result)


def test_parse_rpc_body_strips_the_outer_rpc_envelope():
    # ncclient builds and tracks its own <rpc>/message-id -- passing
    # our own envelope through would double-wrap it.
    result = executor._parse_rpc_body(SAMPLE_EDIT_CONFIG_XML)
    assert etree.QName(result).localname == "edit-config"


def test_parse_rpc_body_preserves_config_content():
    result = executor._parse_rpc_body(SAMPLE_EDIT_CONFIG_XML)
    serialized = etree.tostring(result).decode()
    assert "ethernet-1/1" in serialized
    assert "<admin-state>enable</admin-state>" in serialized


def test_parse_rpc_body_handles_self_closing_commit_rpc():
    result = executor._parse_rpc_body(SAMPLE_COMMIT_XML)
    assert etree.iselement(result)
    assert etree.QName(result).localname == "commit"


def _sample_record():
    return {
        "interface": "ethernet-1/1",
        "yang_path": "/interface[name=ethernet-1/1]/admin-state",
        "proposed_value": "enable",
        "json_rpc_set_payload": {"jsonrpc": "2.0", "id": 1, "method": "set", "params": {}},
        "netconf_edit_config_xml": SAMPLE_EDIT_CONFIG_XML,
        "netconf_commit_xml": SAMPLE_COMMIT_XML,
    }


def test_execute_rejects_unknown_protocol():
    with pytest.raises(ValueError):
        executor.execute(_sample_record(), "172.100.100.11", "carrier-pigeon")


def test_execute_raises_when_device_state_does_not_match_after_success():
    # This is entry 33's real finding, generalized into a test: an RPC
    # can claim success while the device didn't actually move -- never
    # trust the reply alone.
    with patch.object(executor, "execute_json_rpc", return_value={"protocol": "json-rpc", "raw_response": {}}), \
         patch.object(executor, "get_admin_state", return_value="disable"):  # still disable, proposed was enable
        with pytest.raises(executor.ExecutionError, match="still"):
            executor.execute(_sample_record(), "172.100.100.11", "json-rpc")


def test_execute_succeeds_when_device_state_confirms_the_change():
    with patch.object(executor, "execute_json_rpc", return_value={"protocol": "json-rpc", "raw_response": {}}), \
         patch.object(executor, "get_admin_state", return_value="enable"):
        result = executor.execute(_sample_record(), "172.100.100.11", "json-rpc")
        assert result["matches_proposed"] is True
        assert result["confirmed_value"] == "enable"


def test_execute_json_rpc_raises_execution_error_on_device_rejection():
    class _MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"error": {"code": -1, "message": "mocked rejection"}, "id": 1, "jsonrpc": "2.0"}

    with patch.object(executor.requests, "post", return_value=_MockResponse()):
        with pytest.raises(executor.ExecutionError):
            executor.execute_json_rpc(_sample_record(), "172.100.100.11")
