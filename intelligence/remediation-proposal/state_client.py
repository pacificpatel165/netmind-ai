"""NetMind AI — component #8, remediation proposal.

Thin JSON-RPC client for reading current device state before proposing
a change. Same request shape confirmed live against srl1 on 2026-09-14
(PROGRESS_LOG entry 30/31): POST to https://<node-ip>/jsonrpc with a
"get" method and a "commands" list of {path, datastore}.

Runs host-level, same placement reasoning as component #7: this lab is
native Linux Docker (the Containerlab distro), so container IPs on
netmind-mgmt (172.100.100.11/.12) are directly reachable from the host
shell with no port-publishing needed -- confirmed directly, not
assumed (see PROGRESS_LOG entry 30).
"""

import os

import requests

# admin/NokiaSrl1! is this lab's fixed credential (component #1's
# topology file), same one gnmic and every prior curl check has used.
NODE_USER = os.environ.get("SRL_USER", "admin")
NODE_PASSWORD = os.environ.get("SRL_PASSWORD", "NokiaSrl1!")
VERIFY_TLS = False  # self-signed clab-profile cert, same as every prior check

# Real, live-confirmed values for interface admin-state (SR Linux YANG
# enum). Used only to validate a read actually returned device state,
# not to restrict what a *write* could ever propose to -- that's
# remediation_templates.py's job, deliberately kept separate.
KNOWN_ADMIN_STATE_VALUES = {"enable", "disable"}


class DeviceQueryError(Exception):
    """Raised when a device's JSON-RPC endpoint returns something other
    than a clean, single-result success -- the signal that a path was
    wrong, the device was unreachable, or the response shape wasn't
    what propose.py expected. Deliberately not swallowed/defaulted:
    getting a device's current state wrong is exactly the kind of
    mistake that shouldn't be silently absorbed in this component."""


def get_admin_state(node_ip: str, interface: str, timeout: int = 10) -> str:
    """Returns the interface's current admin-state ("enable"/"disable"),
    read fresh from the device -- never cached, never assumed, since a
    remediation proposal is only as trustworthy as the state it was
    built from.

    Validates the returned value looks like real device state, not
    just that the RPC didn't error (fixed 2026-09-17, BACKLOG.md item
    28, found 2026-09-16 during the credential-scoping investigation:
    a non-superuser credential's read came back as {"result": [{}]},
    a *successful* RPC response with no actual leaf data in it -- no
    "error" key, correctly-shaped single-item list, and the previous
    version of this function returned {} as if it were a legitimate
    admin-state value. That's a real gap for anything feeding a
    remediation decision: a silently-empty authorized read is worse
    than an outright rejection, since nothing distinguished it from a
    real answer downstream.)"""
    path = f"/interface[name={interface}]/admin-state"
    resp = requests.post(
        f"https://{node_ip}/jsonrpc",
        auth=(NODE_USER, NODE_PASSWORD),
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "get",
            "params": {"commands": [{"path": path, "datastore": "state"}]},
        },
        verify=VERIFY_TLS,
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise DeviceQueryError(f"{node_ip} rejected query for {path}: {payload['error']}")
    result = payload.get("result")
    if not isinstance(result, list) or len(result) != 1:
        raise DeviceQueryError(f"{node_ip} returned an unexpected shape for {path}: {payload}")
    value = result[0]
    if not isinstance(value, str) or value not in KNOWN_ADMIN_STATE_VALUES:
        raise DeviceQueryError(
            f"{node_ip} returned a successful-looking but empty/invalid value for {path}: "
            f"{value!r} (expected one of {sorted(KNOWN_ADMIN_STATE_VALUES)}) -- this usually "
            "means the RPC succeeded but the caller's credential isn't authorized to see the "
            "actual leaf data (see PROGRESS_LOG.md entry 41), not that the interface has no state."
        )
    return value
