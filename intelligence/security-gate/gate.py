"""NetMind AI — component #9, security gate. First real build (2026-09-15).

Design confirmed explicitly before writing this file (see PROGRESS_LOG.md
for the session): stage 1 builds the two pieces that don't depend on
anything not yet real -- an explicit-approval gate and an append-only
audit log -- against component #8's already-verified chained proposal
(diagnose_and_propose.py). Least-privilege credential scoping is
deliberately NOT built here: every component so far reuses the lab's one
admin/NokiaSrl1! credential, and building a genuinely scoped SR Linux
AAA role requires checking, live, whether this image's local-AAA system
actually supports restricting a user to just the admin-state leaf --
not guessed at and bolted on later. That's a separate, explicitly
verified next step, not silently skipped.

What this component actually enforces, stage 1:
- **Explicit human approval, default-deny.** Nothing here auto-approves.
  Anything other than a literal "y"/"yes" at the prompt -- including a
  blank Enter -- is a rejection. There is no code path that applies a
  change without a human saying yes to it.
- **An audit trail of the decision**, not of an executed change --
  component #10 (the config-push executor) doesn't exist yet, so
  nothing here ever actually applies anything to a device, approved or
  not. The audit log records what was proposed, what was decided, and
  by whom -- proof of the decision, not proof of an action.

What this component does NOT yet guarantee, stated plainly rather than
implied:
- **The audit log is append-only in this code's own behavior, not
  filesystem-enforced or tamper-evident.** Every write here opens the
  file in "a" mode -- nothing in this module ever opens it "w" -- but
  someone with direct file access could still edit or truncate it with
  a text editor. Real tamper-evidence (append-only file permissions via
  `chattr +a`, or a hash chain linking each entry to the one before it)
  is a legitimate stage-2 item, not something to claim exists today.
- **No credential scoping** (see above) -- this stage-1 gate decides
  whether a human approved a change, not what permissions would be used
  to apply one.

Usage:
    python gate.py <node-ip> <interface>
    python gate.py 172.100.100.11 ethernet-1/1
"""

import getpass
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# diagnose_and_propose.py (component #8) lives in the sibling
# remediation-proposal/ directory -- reused as a library, same
# "prove a piece in isolation, then chain" pattern used throughout
# this project rather than duplicating its logic here.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "remediation-proposal"))

from diagnose_and_propose import diagnose_and_propose
from state_client import DeviceQueryError

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


def append_audit_entry(record: dict, decision: str, decided_by: str) -> None:
    """Appends one JSON line. Opens the file in "a" mode only -- see
    this module's docstring for exactly what that does and doesn't
    guarantee."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "interface": record["interface"],
        "node_ip": record.get("node_ip"),
        "yang_path": record["yang_path"],
        "current_value": record["current_value"],
        "proposed_value": record["proposed_value"],
        "decision": decision,
        "decided_by": decided_by,
        "proposal_hash": proposal_hash(record),
        "rationale_included": "rationale" in record,
    }
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def gate(node_ip: str, interface: str) -> None:
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

    append_audit_entry(record, decision, decided_by)

    if approved:
        print(
            f"\nRecorded: APPROVED by {decided_by}. Nothing was applied --"
            " component #10 (config-push executor) doesn't exist yet."
            " This decision is recorded for when it does."
        )
    else:
        print(f"\nRecorded: REJECTED by {decided_by}. No change was proposed for execution.")


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: python gate.py <node-ip> <interface>")
        sys.exit(1)
    gate(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
