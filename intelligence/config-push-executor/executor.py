"""NetMind AI — component #10, config-push executor. First real build
(2026-09-16).

Applies an *already-approved* proposal record (component #9's output)
to the device, using one of the two payload shapes component #8 already
built and proved by hand: the JSON-RPC `set` call (PROGRESS_LOG entry
31) or the NETCONF `edit-config` + `commit` RPC pair (entry 33). This
module doesn't build either payload -- it only fires what
`remediation_templates.py` already generated and `gate.py` already
displayed to a human for approval.

**Credential, per PROGRESS_LOG entry 41's decision, stated plainly, not
silently assumed:** this uses the full `admin`/`NokiaSrl1!` credential,
same as every other component. Entry 41 live-tested and confirmed that
a non-superuser SR Linux local-AAA role gets no YANG-path read/write
access at all via NETCONF or JSON-RPC on this image -- not restricted
access, none -- so there is currently no scoped credential this
component *could* use instead. The real security boundary for this
project is component #9's human-approval gate and audit log, not
credential scoping. See `docs/roadmap/BACKLOG.md` item 27 for the real,
untried alternatives (sr_cli-scoped writes, TACACS+, a newer SR Linux
release) that weren't closed off, just not pursued yet.

Two protocols, one flag, not two separate executors -- both payload
shapes already exist on every proposal record (`remediation_templates.py`
builds both regardless of which one ends up used), so there's no
upstream cost to supporting either at execution time.

**NETCONF path has NOT been run live yet as of this module's first
commit.** Every NETCONF RPC in this project so far was applied by hand
over a raw `ssh -p 830 -s admin@<node-ip> netconf` session (see
`docs/testing/TESTING.md` section for component #8) -- nothing here has
used a real Python NETCONF client before. `ncclient` is used below as
the standard library for it, via `manager.dispatch()` to send the
already-built RPC XML directly rather than reconstructing the config
through ncclient's own high-level `edit_config()` helper -- keeping
`remediation_templates.py`'s proven XML as the actual source of truth
instead of two versions of the same RPC existing in the codebase. This
needs a real live test before it's trusted -- see README.md's
"Not yet done".
"""

import os
import sys

import requests

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "remediation-proposal"))
from state_client import DeviceQueryError, get_admin_state  # noqa: E402

NODE_USER = os.environ.get("SRL_USER", "admin")
NODE_PASSWORD = os.environ.get("SRL_PASSWORD", "NokiaSrl1!")
VERIFY_TLS = False  # self-signed clab-profile cert, same as every prior check
NETCONF_PORT = 830


class ExecutionError(Exception):
    """Raised when applying an approved change fails -- deliberately not
    swallowed. A failed execution should stop loudly, the same posture
    state_client.py's DeviceQueryError takes for a failed read: this is
    exactly the kind of failure that shouldn't be silently absorbed."""


def execute_json_rpc(record: dict, node_ip: str, timeout: int = 10) -> dict:
    """Fires the exact json_rpc_set_payload already built and shown to
    the human approver -- nothing rebuilt or re-derived here."""
    resp = requests.post(
        f"https://{node_ip}/jsonrpc",
        auth=(NODE_USER, NODE_PASSWORD),
        json=record["json_rpc_set_payload"],
        verify=VERIFY_TLS,
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise ExecutionError(f"{node_ip} rejected the set: {payload['error']}")
    return {"protocol": "json-rpc", "raw_response": payload}


def execute_netconf(record: dict, node_ip: str, timeout: int = 30) -> dict:
    """Sends the exact netconf_edit_config_xml then netconf_commit_xml
    RPC strings already built and shown to the human approver, over a
    real ncclient session -- NOT yet live-tested, see module docstring.
    """
    try:
        from ncclient import manager
    except ImportError as exc:
        raise RuntimeError(
            "ncclient is not installed -- run: pip install -r requirements.txt"
        ) from exc

    with manager.connect(
        host=node_ip,
        port=NETCONF_PORT,
        username=NODE_USER,
        password=NODE_PASSWORD,
        hostkey_verify=False,
        timeout=timeout,
    ) as m:
        edit_reply = m.dispatch(_parse_rpc_body(record["netconf_edit_config_xml"]))
        if not edit_reply.ok:
            raise ExecutionError(f"{node_ip} rejected edit-config: {edit_reply.xml}")
        commit_reply = m.dispatch(_parse_rpc_body(record["netconf_commit_xml"]))
        if not commit_reply.ok:
            raise ExecutionError(f"{node_ip} rejected commit: {commit_reply.xml}")
        return {
            "protocol": "netconf",
            "raw_response": {"edit_config": edit_reply.xml, "commit": commit_reply.xml},
        }


def _parse_rpc_body(rpc_xml: str):
    """ncclient's manager.dispatch() wants the RPC's inner element (the
    <edit-config>/<commit> body), not the full <rpc message-id=...>
    envelope -- ncclient builds and tracks its own envelope/message-id.
    remediation_templates.py's XML includes that outer <rpc> wrapper
    (needed for the by-hand raw-SSH test this project used before), so
    it's stripped here rather than changing the proven template.

    Live-verified bug fix (2026-09-16, PROGRESS_LOG entry 43): this
    must parse with lxml.etree, not the stdlib xml.etree.ElementTree.
    ncclient's Dispatch.request() checks `etree.iselement(rpc_command)`
    using *its own* lxml-backed etree import -- a stdlib
    ElementTree.Element fails that check silently, falls through to
    being treated as a literal tag-name string, and produces exactly
    the "Invalid tag name" error this fix resolves. Confirmed by
    reading ncclient's actual installed source
    (operations/retrieve.py's Dispatch.request, xml_.py's to_ele),
    not assumed from documentation."""
    from lxml import etree

    root = etree.fromstring(rpc_xml.encode("utf-8"))
    # first (and only) child of <rpc> is the actual operation element
    return list(root)[0]


def execute(record: dict, node_ip: str, protocol: str) -> dict:
    if protocol == "json-rpc":
        result = execute_json_rpc(record, node_ip)
    elif protocol == "netconf":
        result = execute_netconf(record, node_ip)
    else:
        raise ValueError(f"unknown protocol: {protocol!r} (expected 'json-rpc' or 'netconf')")

    # Verify against the live device -- never trust the RPC reply alone.
    # entry 33 proved exactly this gap: edit-config can return <ok/>
    # while leaving device state unchanged if commit is missing/wrong.
    try:
        confirmed_value = get_admin_state(node_ip, record["interface"])
    except DeviceQueryError as exc:
        raise ExecutionError(
            f"execution RPC succeeded but post-execution state read failed: {exc}"
        ) from exc

    result["confirmed_value"] = confirmed_value
    result["matches_proposed"] = confirmed_value == record["proposed_value"]
    if not result["matches_proposed"]:
        raise ExecutionError(
            f"RPC reply looked successful but device state is still"
            f" {confirmed_value!r}, not the proposed {record['proposed_value']!r}"
        )
    return result
