"""NetMind AI — component #8, automated tests for state_client.py
(BACKLOG.md item 30, added 2026-09-17).

Scope: `get_admin_state()`'s response-handling logic, with `requests`
mocked -- no live device needed. These tests exist specifically to
pin the fix for BACKLOG.md item 28 (found 2026-09-16 during the
credential-scoping investigation): a real, live response
(`{"result": [{}]}`) that looks successful but carries no actual
device data must be rejected loudly, not returned as if it were a
real value. The mocked payloads below are the *actual* shapes seen
live during that investigation (see PROGRESS_LOG.md entries 41-43),
not invented edge cases.

Run:
    cd intelligence/remediation-proposal
    source .venv/bin/activate
    pytest test_state_client.py -v
"""

from unittest.mock import MagicMock, patch

import pytest

import state_client


def _mock_response(json_body, status_ok=True):
    resp = MagicMock()
    resp.json.return_value = json_body
    if status_ok:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = state_client.requests.HTTPError("mocked failure")
    return resp


def test_get_admin_state_returns_real_value_on_success():
    # The real shape a healthy admin-credential read returns
    # (PROGRESS_LOG entry 41's admin-credential curl).
    with patch.object(state_client.requests, "post", return_value=_mock_response(
        {"result": ["disable"], "id": 1, "jsonrpc": "2.0"}
    )):
        assert state_client.get_admin_state("172.100.100.11", "ethernet-1/1") == "disable"


def test_get_admin_state_raises_on_explicit_rpc_error():
    with patch.object(state_client.requests, "post", return_value=_mock_response(
        {"error": {"code": -1, "message": "mocked device rejection"}, "id": 1, "jsonrpc": "2.0"}
    )):
        with pytest.raises(state_client.DeviceQueryError):
            state_client.get_admin_state("172.100.100.11", "ethernet-1/1")


def test_get_admin_state_raises_on_malformed_result_shape():
    with patch.object(state_client.requests, "post", return_value=_mock_response(
        {"result": ["disable", "enable"], "id": 1, "jsonrpc": "2.0"}  # wrong length
    )):
        with pytest.raises(state_client.DeviceQueryError):
            state_client.get_admin_state("172.100.100.11", "ethernet-1/1")


def test_get_admin_state_raises_on_silently_empty_authorized_read():
    # This is the exact real payload a non-superuser credential
    # returned live (PROGRESS_LOG entry 41) -- a "successful" RPC
    # response with no actual leaf data. Before the 2026-09-17 fix,
    # this returned {} as if it were a legitimate admin-state value.
    with patch.object(state_client.requests, "post", return_value=_mock_response(
        {"result": [{}], "id": 1, "jsonrpc": "2.0"}
    )):
        with pytest.raises(state_client.DeviceQueryError, match="empty/invalid"):
            state_client.get_admin_state("172.100.100.11", "ethernet-1/1")


def test_get_admin_state_raises_on_unexpected_string_value():
    # Not one of the known admin-state enum values -- a real device
    # bug or a wrong YANG path would produce something like this
    # rather than a clean "enable"/"disable".
    with patch.object(state_client.requests, "post", return_value=_mock_response(
        {"result": ["not-a-real-admin-state"], "id": 1, "jsonrpc": "2.0"}
    )):
        with pytest.raises(state_client.DeviceQueryError):
            state_client.get_admin_state("172.100.100.11", "ethernet-1/1")
