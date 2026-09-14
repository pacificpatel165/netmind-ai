"""NetMind AI — component #8, remediation proposal.

Deterministic templates only, by design -- unlike component #7's
hybrid PromQL strategy (LLM fallback allowed, validated before
trusting), nothing here ever gets its structured payload from an LLM.
Pushing config to a network device is a different risk class than
reading a metric: a rejected PromQL query just fails cleanly, but a
wrong or LLM-hallucinated config path/value is exactly the kind of
mistake the security gate (component #9) exists to catch, and this
component shouldn't be the thing generating that risk in the first
place. The LLM's role anywhere near this component is limited to
writing human-readable rationale text citing a diagnosis -- never the
YANG path or the value being set. See README.md.

Only one scenario is templated for stage 1 (2026-09-14): bringing a
disabled interface back to admin-state enable. See
docs/roadmap/BACKLOG.md for what's deliberately out of scope for now.

JSON-RPC "set" payload shape follows the same {path, ...} style
confirmed live for "get" (PROGRESS_LOG entry 31) -- the "set" method
and its action/value fields are Nokia's documented JSON-RPC API shape,
but have NOT yet been executed against the live lab (see propose.py's
docstring and BACKLOG.md) -- treat json_rpc_set_payload as a reviewed,
not-yet-fired proposal until that validation happens.

The NETCONF edit-config XML is intentionally NOT built here yet -- the
exact srl_nokia-interfaces YANG module namespace hasn't been confirmed
against this lab (get it wrong and NETCONF silently rejects or ignores
the edit), so writing it now would mean guessing at something this
project has explicitly committed to never guessing at. See
PROGRESS_LOG entry 30/BACKLOG.md for the open item to confirm it via
gnmic's own capabilities output before this gets filled in.
"""

YANG_PATH_TEMPLATE = "/interface[name={interface}]/admin-state"


def interface_admin_up(interface: str, current_value: str) -> dict:
    """Build a proposal record for re-enabling a disabled interface.

    current_value is passed in, not re-queried here -- state_client.py
    owns reading device state; this function only owns building the
    record from what the caller already observed, so there's exactly
    one place a "current state" read can go wrong, not two."""
    path = YANG_PATH_TEMPLATE.format(interface=interface)
    target_value = "enable"

    json_rpc_set_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "set",
        "params": {
            "commands": [
                {"action": "update", "path": path, "value": target_value}
            ]
        },
    }

    return {
        "interface": interface,
        "yang_path": path,
        "current_value": current_value,
        "proposed_value": target_value,
        "json_rpc_set_payload": json_rpc_set_payload,
        "netconf_edit_config_xml": None,  # pending confirmed YANG namespace -- see module docstring
        "executed": False,
    }
