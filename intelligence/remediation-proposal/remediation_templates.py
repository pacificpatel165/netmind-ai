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

Both payload shapes have been fired for real against the live lab and
confirmed working, not just reviewed against documentation:

- json_rpc_set_payload (PROGRESS_LOG entry 31) -- a real fault was
  created, this exact payload shape was applied by hand, and the
  device's own state confirmed the fix took effect.
- netconf_edit_config_xml / netconf_commit_xml (PROGRESS_LOG entry
  33), using a namespace captured directly from srl1's own NETCONF
  <hello> exchange (entry 32), not guessed:
  urn:nokia.com:srlinux:chassis:interfaces?module=srl_nokia-interfaces
  The same <hello> advertises candidate:1.0 and confirmed-commit:1.1
  -- NETCONF here follows the identical candidate-then-commit
  two-phase model already confirmed working via sr_cli (entry 31),
  and entry 33 proved it by hand: edit-config alone returned <ok/>
  but left device state unchanged (confirmed via a JSON-RPC get
  immediately after), and only the separate <commit/> RPC actually
  applied the change.
"""

INTERFACES_NAMESPACE = "urn:nokia.com:srlinux:chassis:interfaces"
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

    netconf_edit_config_xml = f"""<rpc message-id="101" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <edit-config>
    <target><candidate/></target>
    <config>
      <interface xmlns="{INTERFACES_NAMESPACE}">
        <name>{interface}</name>
        <admin-state>{target_value}</admin-state>
      </interface>
    </config>
  </edit-config>
</rpc>"""

    # Stages the change into candidate only -- SR Linux's NETCONF server
    # requires this second, separate RPC to actually apply it (same
    # candidate/commit model as sr_cli's "commit now"; see module
    # docstring).
    netconf_commit_xml = (
        '<rpc message-id="102" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">'
        "<commit/></rpc>"
    )

    return {
        "interface": interface,
        "yang_path": path,
        "current_value": current_value,
        "proposed_value": target_value,
        "json_rpc_set_payload": json_rpc_set_payload,
        "netconf_edit_config_xml": netconf_edit_config_xml,
        "netconf_commit_xml": netconf_commit_xml,
        "executed": False,
    }
