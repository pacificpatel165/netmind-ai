"""NetMind AI — component #8, remediation proposal. First real build.

Stage 1, standalone (PROGRESS_LOG entry 30): takes an interface name,
reads its real current state, and — only if it's actually disabled —
builds a proposal record. Nothing in this component ever applies a
change; "executed": false in the output is load-bearing, not a
formality. Chaining this off a real component #7 diagnosis (rather
than running standalone against a bare interface name) is a deliberate
next step, not done yet -- see README.md.

Usage:
    python propose.py <node-ip> <interface>
    python propose.py 172.100.100.11 ethernet-1/1

Both protocols have now been fired for real against the live lab and
confirmed working: the json_rpc_set_payload (PROGRESS_LOG entry 31)
and the netconf_edit_config_xml / netconf_commit_xml pair (entry 33,
using a namespace confirmed directly from srl1's own NETCONF <hello>
exchange in entry 32). Each protocol independently had a real fault
created, propose.py detect and build the payload, the payload applied
by hand, and propose.py independently confirm the fix took effect --
standing in for the human-approval step component #9 will formalize
later. See README.md.
"""

import json
import sys

import remediation_templates as templates
from state_client import DeviceQueryError, get_admin_state


def propose(node_ip: str, interface: str) -> dict | None:
    """Returns a proposal record if the interface is actually down,
    or None if it's already up -- there's nothing to propose for an
    interface that isn't broken, and this function should say so
    plainly rather than returning an empty-ish record."""
    current = get_admin_state(node_ip, interface)
    if current == "enable":
        return None
    return templates.interface_admin_up(interface, current_value=current)


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: python propose.py <node-ip> <interface>")
        sys.exit(1)
    node_ip, interface = sys.argv[1], sys.argv[2]

    try:
        record = propose(node_ip, interface)
    except DeviceQueryError as exc:
        print(f"could not read current state: {exc}")
        sys.exit(1)

    if record is None:
        print(f"{interface} on {node_ip} is already admin-state enable -- nothing to propose.")
        return

    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
