"""NetMind AI — component #9, security gate. Extended 2026-09-16 to chain
into component #10.

Design confirmed explicitly before writing this file (see PROGRESS_LOG.md
for the session): stage 1 built the two pieces that don't depend on
anything not yet real -- an explicit-approval gate and an append-only
audit log -- against component #8's already-verified chained proposal
(diagnose_and_propose.py).

**Credential scoping was investigated live, not deferred forever --
see PROGRESS_LOG.md entry 41.** A non-superuser SR Linux local-AAA role
was configured and tested; it gets zero YANG-path read/write access via
NETCONF or JSON-RPC on this image regardless of services/operations
granted, confirmed by an isolated superuser-only flip. Real,
untried alternatives are on `docs/roadmap/BACKLOG.md` item 27 (sr_cli
command-list scoping, TACACS+, a newer SR Linux release) -- not closed
off, just not pursued yet. The decision: component #10 uses the full
admin/NokiaSrl1! credential, same as every other component, and this
gate's approval + audit trail carry the actual security boundary.

What this component actually enforces:
- **Explicit human approval, default-deny.** Nothing here auto-approves.
  Anything other than a literal "y"/"yes" at the prompt -- including a
  blank Enter -- is a rejection. There is no code path that applies a
  change without a human saying yes to it.
- **An audit trail of both the decision and, now that component #10
  exists, the execution outcome** -- as two separate append-only
  entries correlated by `proposal_hash`, not one mutated entry. A
  decision entry is written the moment a human answers the prompt,
  before execution is attempted; an execution entry is written after,
  recording whether the RPC succeeded and whether the live device
  actually confirmed the change (see `config-push-executor/executor.py`
  -- it never trusts an RPC's "ok" reply alone, the same trap entry 33
  found: a reply can say ok while device state doesn't move).

What this component does NOT yet guarantee, stated plainly rather than
implied:
- **The audit log is append-only in this code's own behavior, not
  filesystem-enforced or tamper-evident.** Every write here opens the
  file in "a" mode -- nothing in this module ever opens it "w" -- but
  someone with direct file access could still edit or truncate it with
  a text editor. Real tamper-evidence (append-only file permissions via
  `chattr +a`, or a hash chain linking each entry to the one before it)
  is a legitimate stage-2 item, not something to claim exists today.

Usage:
    python gate.py <node-ip> <interface> [--protocol json-rpc|netconf]
    python gate.py 172.100.100.11 ethernet-1/1
    python gate.py 172.100.100.11 ethernet-1/1 --protocol netconf
Default protocol is json-rpc -- the one already live-verified end to
end (entries 31, 41); netconf has NOT been live-tested through this
executor yet, see config-push-executor/README.md.
"""

import getpass
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# diagnose_and_propose.py (component #8) and executor.py (component #10)
# live in sibling directories -- reused as libraries, same "prove a
# piece in isolation, then chain" pattern used throughout this project
# rather than duplicating their logic here.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "remediation-proposal"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "config-push-executor"))

from diagnose_and_propose import diagnose_and_propose
from state_client import DeviceQueryError
from executor import ExecutionError, execute

AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_log.jsonl"

# The fields that make up the actual, deterministic proposal -- exactly
# what "approving" this change means. "rationale" is deliberately
# excluded from the hash: it's an AI-generated explanation, not part of
# the change being approved, and its wording can legitimately vary
# between runs (different retrieval hits, different model sampling)
# without that meaning the underlying proposal changed at all.
DETERMINISTIC_FIELDS = (
    "interface",
    "yang_path",
    "current_value",
    "proposed_value",
    "json_rpc_set_payload",
    "netconf_edit_config_xml",
    "netconf_commit_xml",
    "executed",
)


def proposal_hash(record: dict) -> str:
    """SHA-256 over exactly the deterministic fields, canonical (sorted
    keys, no whitespace variance) so the same proposal always hashes the
    same way regardless of dict ordering. This is what the audit log
    actually proves was shown at decision time -- not the rationale
    text, which can vary run to run without the proposal itself having
    changed."""
    deterministic = {k: record[k] for k in DETERMINISTIC_FIELDS}
    canonical = json.dumps(deterministic, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def display_proposal(record: dict) -> None:
    print("=== Proposed Remediation ===")
    print(f"Interface:       {record['interface']}")
    print(f"YANG path:       {record['yang_path']}")
    print(f"Current value:   {record['current_value']}")
    print(f"Proposed value:  {record['proposed_value']}")
    print()
    print("--- JSON-RPC set payload ---")
    print(json.dumps(record["json_rpc_set_payload"], indent=2))
    print()
    print("--- NETCONF edit-config ---")
    print(record["netconf_edit_config_xml"])
    print()
    print("--- NETCONF commit ---")
    print(record["netconf_commit_xml"])
    print()
    if "rationale" in record:
        print("--- AI-generated rationale (component #7) ---")
        print("NOTE: best-effort explanation, not evidence. Verify")
        print("independently before relying on it -- see")
        print("PROGRESS_LOG.md entry 38 for a real example of this")
        print("being honest-but-thin rather than deeply grounded.")
        print()
        print(record["rationale"])
        print()


def _base_audit_fields(record: dict) -> dict:
    """Fields shared by both a decision entry and an execution entry --
    factored out so the two entries are correlated by more than just
    proposal_hash (same interface/node/values), without duplicating the
    field list twice."""
    return {
        "interface": record["interface"],
        "node_ip": record.get("node_ip"),
        "yang_path": record["yang_path"],
        "current_value": record["current_value"],
        "proposed_value": record["proposed_value"],
        "proposal_hash": proposal_hash(record),
    }


def append_decision_entry(record: dict, decision: str, decided_by: str) -> None:
    """Appends one JSON line recording the human decision. Opens the
    file in "a" mode only -- see this module's docstring for exactly
    what that does and doesn't guarantee."""
    entry = {
        "event": "decision",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **_base_audit_fields(record),
        "decision": decision,
        "decided_by": decided_by,
        "rationale_included": "rationale" in record,
    }
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def append_execution_entry(record: dict, protocol: str, success: bool, detail: str) -> None:
    """Appends one JSON line recording what happened when an approved
    change was actually applied -- a second, separate entry rather than
    mutating the decision entry above, preserving append-only. Written
    whether execution succeeded or failed: a failed execution is exactly
    the kind of event this audit trail exists to capture, not something
    to leave unrecorded."""
    entry = {
        "event": "execution",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **_base_audit_fields(record),
        "protocol": protocol,
        "success": success,
        "detail": detail,
    }
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def gate(node_ip: str, interface: str, protocol: str = "json-rpc") -> None:
    try:
        record = diagnose_and_propose(node_ip, interface)
    except DeviceQueryError as exc:
        print(f"could not read current state: {exc}")
        sys.exit(1)

    if record is None:
        print(f"{interface} on {node_ip} is already admin-state enable -- nothing to propose, nothing to approve.")
        return

    record["node_ip"] = node_ip
    display_proposal(record)

    answer = input("Approve this change? [y/N]: ").strip().lower()
    approved = answer in ("y", "yes")
    decision = "approved" if approved else "rejected"
    decided_by = getpass.getuser()

    append_decision_entry(record, decision, decided_by)

    if not approved:
        print(f"\nRecorded: REJECTED by {decided_by}. No change was proposed for execution.")
        return

    print(f"\nRecorded: APPROVED by {decided_by}. Applying via {protocol}...")
    try:
        result = execute(record, node_ip, protocol)
    except ExecutionError as exc:
        append_execution_entry(record, protocol, success=False, detail=str(exc))
        print(f"\nEXECUTION FAILED: {exc}")
        print("Recorded in audit log as a failed execution -- approval alone never means it took effect.")
        sys.exit(1)

    append_execution_entry(
        record, protocol, success=True,
        detail=f"confirmed device state: {result['confirmed_value']}",
    )
    print(f"\nEXECUTION SUCCEEDED via {protocol}. Confirmed live device state: {result['confirmed_value']!r}.")


def main() -> None:
    args = sys.argv[1:]
    protocol = "json-rpc"
    if "--protocol" in args:
        idx = args.index("--protocol")
        try:
            protocol = args[idx + 1]
        except IndexError:
            print("usage: python gate.py <node-ip> <interface> [--protocol json-rpc|netconf]")
            sys.exit(1)
        del args[idx:idx + 2]
    if protocol not in ("json-rpc", "netconf"):
        print(f"unknown protocol: {protocol!r} (expected 'json-rpc' or 'netconf')")
        sys.exit(1)
    if len(args) != 2:
        print("usage: python gate.py <node-ip> <interface> [--protocol json-rpc|netconf]")
        sys.exit(1)
    gate(args[0], args[1], protocol)


if __name__ == "__main__":
    main()
