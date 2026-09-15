"""NetMind AI — component #8, chained trigger (2026-09-15 design).

Replaces propose.py's bare interface-name argument with a real
component #7 diagnosis as the trigger's rationale -- but only as
rationale, never as the trigger and never anywhere near the payload.
This is the explicit design this session settled on before starting
component #9 (the security gate): give #9 a realistic diagnosis-driven
proposal to gate, rather than one triggered by a hand-typed CLI arg.

The split, stated plainly because it's the whole point of this file:
- The trigger -- whether a proposal gets built at all, and what its
  json_rpc_set_payload / netconf_edit_config_xml / netconf_commit_xml
  actually contain -- is exactly the same deterministic device-state
  check propose.py already used (state_client.get_admin_state +
  remediation_templates.interface_admin_up). Unchanged, not touched.
- component #7's diagnosis assistant (assistant.answer()) is called
  ONLY after that check already found a real, confirmed fault, and its
  output is attached to the proposal record as a new "rationale"
  string field -- read-only, human-facing, never parsed back into
  code. This mirrors remediation_templates.py's own long-standing
  rule (see that module's docstring): the LLM never authors the
  structured payload. Chaining #7 in as *context* doesn't relax that
  rule -- it was the whole reason the split needed spelling out before
  writing any code.

Usage:
    python diagnose_and_propose.py <node-ip> <interface>
    python diagnose_and_propose.py 172.100.100.11 ethernet-1/1

Requires the diagnosis-assistant component's dependencies (chromadb,
in addition to requests) -- see this component's requirements.txt and
README.md's "Chaining #7 into #8" section for why, and for the actual
live services (Chroma, Prometheus, Ollama) this now depends on beyond
propose.py's original scope.

Not yet run against the live stack -- built and reviewed, same "prove
it before calling it done" pattern as every other build in this
project. See PROGRESS_LOG.md for the session this was designed in and
docs/testing/TESTING.md for the actual verification command once run.
"""

import json
import sys
from pathlib import Path

# assistant.answer() lives in the sibling diagnosis-assistant/
# component -- reused as a library rather than duplicated, the same
# "prove a piece in isolation, then chain" pattern component #7 itself
# followed reusing component #6's Chroma collection via
# retrieval_client.py. Path inserted before the import, not relative
# to cwd, so this script works regardless of which directory it's run
# from (see diagnosis-assistant/run.sh's own docstring for a real
# mix-up this exact kind of fragility caused before).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "diagnosis-assistant"))

import remediation_templates as templates
from state_client import DeviceQueryError, get_admin_state

RATIONALE_QUESTION_TEMPLATE = (
    "Interface {interface} on {node_ip} is currently admin-state "
    "{current_value}. Given its recent carrier transition history, "
    "explain what admin-state disable means for this interface and "
    "why bringing it back to admin-state enable is the appropriate "
    "fix, citing any relevant project documentation if it applies."
)
# Deliberately phrased to include "carrier transition" -- not padding,
# and not just dodging router.py's fallback path either. It's a
# genuinely useful thing to ground the rationale in: a manually
# disabled interface with zero recent transitions is a clean one-off
# fix; one with a recent flap history might be masking a flapping
# problem the fix alone won't address. It also happens to match
# promql_templates.py's "carrier"/"transition" keywords, which routes
# this through the fixed flap_history template (see promql_templates.py)
# instead of router.py's LLM-generated-PromQL fallback. Found in code
# review before this file was ever run against the live stack: the
# original wording matched no template keyword at all, so every call
# would have silently cost two Ollama round-trips (one wasted
# generating an unneeded PromQL query, one for the real answer) and
# exercised the fallback's known repair-loop gap (BACKLOG.md item 23)
# on every single proposal, for no reason.


def diagnose_and_propose(node_ip: str, interface: str) -> dict | None:
    """Same deterministic trigger as propose.py: reads real device
    state, proposes nothing if the interface isn't actually down. Only
    once a real fault is confirmed does this call the diagnosis
    assistant, purely for a human-readable "rationale" field attached
    to the same proposal record propose.py already produces -- the
    record's json_rpc_set_payload/netconf_*_xml fields are built
    identically either way.

    If the assistant call itself fails (Ollama unreachable, Chroma
    empty, a malformed response, ...), that failure is captured into
    the rationale text rather than raised -- the proposal's validity
    never depended on the rationale being generatable, and a diagnosis
    outage shouldn't silently block a real, already-confirmed fix from
    being proposed."""
    current = get_admin_state(node_ip, interface)
    if current == "enable":
        return None

    record = templates.interface_admin_up(interface, current_value=current)

    # Imported here, not at module load: assistant.py's own imports
    # (chromadb, the Ollama HTTP client) should only be required on
    # the path that actually needs them -- a real, confirmed fault --
    # not on every run of this script, most of which (same as
    # propose.py) find nothing to propose.
    try:
        import assistant
    except ImportError as exc:
        # Not a live-service failure -- a setup step was skipped (this
        # component's own requirements.txt now includes chromadb
        # specifically for this import chain; see requirements.txt's
        # comment). Re-raised with a pointed message rather than
        # folded into the generic "rationale unavailable" case below,
        # so a missing `pip install` doesn't get mistaken for Ollama/
        # Chroma being down mid-test.
        raise RuntimeError(
            f"diagnose_and_propose.py needs component #7's dependencies "
            f"installed in this .venv -- run `pip install -r "
            f"requirements.txt` here first ({exc})"
        ) from exc

    try:
        rationale = assistant.answer(
            RATIONALE_QUESTION_TEMPLATE.format(
                interface=interface, node_ip=node_ip, current_value=current
            )
        )
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: any
        # *runtime* failure in the rationale path (Ollama unreachable,
        # Chroma empty, a malformed response, ...) must degrade to a
        # plain note, never propagate and block or alter the proposal
        # itself. A missing dependency is handled above, separately,
        # because that's a setup mistake, not a live-service outage.
        rationale = f"(rationale unavailable: {exc})"

    record["rationale"] = rationale
    return record


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: python diagnose_and_propose.py <node-ip> <interface>")
        sys.exit(1)
    node_ip, interface = sys.argv[1], sys.argv[2]

    try:
        record = diagnose_and_propose(node_ip, interface)
    except DeviceQueryError as exc:
        print(f"could not read current state: {exc}")
        sys.exit(1)

    if record is None:
        print(f"{interface} on {node_ip} is already admin-state enable -- nothing to propose.")
        return

    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
