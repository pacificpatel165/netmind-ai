# intelligence/remediation-proposal/

Component #8 — the diagnosis assistant's output extended one step
further into a concrete config change. This is a *proposal*, never an
execution: components #9 (security gate) and #10 (config-push
executor) don't exist yet, and nothing here applies anything to a
device.

## Design decisions (2026-09-14)

- **Protocol: both NETCONF and JSON-RPC, built for the same change.**
  Confirmed live against `srl1` that both are enabled by default on
  this lab image (`ghcr.io/nokia/srlinux:latest`) — NETCONF-over-SSH
  on port 830, JSON-RPC over HTTP/HTTPS on the `mgmt` network-instance
  — see `PROGRESS_LOG.md` entry 30. SR Linux's actual HTTP config API
  is JSON-RPC, not standard RESTCONF; worth naming that precisely
  rather than calling it "RESTCONF" out of habit from earlier planning
  docs. Both protocols operate on the same `srl_nokia` YANG model
  family gnmic already streams telemetry from — one schema, two
  transports, not two schemas to learn.
- **The LLM never authors the structured payload — deterministic
  templates only.** Component #7's hybrid strategy (LLM-generated
  PromQL as a validated fallback) doesn't carry over here. A rejected
  PromQL query fails cleanly with no side effect; a wrong or
  hallucinated config path/value is a different risk class entirely —
  exactly the kind of mistake the security gate (#9) exists to catch,
  and this component shouldn't be the thing generating that risk. Any
  future LLM involvement near this component is limited to writing
  human-readable rationale text citing a diagnosis, never the YANG
  path or the value being set.
- **Scope: one scenario for stage 1** — bringing a disabled interface
  back to `admin-state enable`. There's no fault-injection mechanism
  in the lab yet, so this is the realistic, safe, fully reversible
  problem to demonstrate: manually disable an interface to create a
  real fault, then have this component detect it and propose the
  fix.
- **Trigger: standalone first, then chained (2026-09-15).**
  `propose.py` takes a node IP and interface name directly — the
  original "prove the piece in isolation before wiring it into the
  bigger pipeline" pattern `router.py` went through before
  `assistant.py` called it, and it's kept exactly as-is. A second
  entry point, `diagnose_and_propose.py`, was added once component #8
  itself was fully proven (see "Verified" below): same node-IP +
  interface arguments, same deterministic device-state trigger, same
  proposal-record fields — but once a real fault is confirmed, it
  also calls component #7's `assistant.answer()` and attaches the
  result as a new `"rationale"` string field. See "Chaining #7 into
  #8" below for why that split (trigger vs. rationale) matters and is
  kept strict.
- **Placement: host-level, same reasoning as component #7** — reaches
  `srl1`/`srl2` directly over their container IPs on `netmind-mgmt`,
  confirmed directly reachable from the host shell with no
  port-publishing needed (native Linux Docker, not Docker Desktop —
  see `PROGRESS_LOG.md` entry 30).

## Layout

- `state_client.py` — reads an interface's current `admin-state` via
  JSON-RPC `get`, confirmed live against `srl1` before any code was
  written around it (`PROGRESS_LOG.md` entry 30/31).
- `remediation_templates.py` — the one templated scenario
  (`interface_admin_up`). Builds the JSON-RPC `set` payload (reviewed
  against Nokia's documented shape, not yet fired against the live
  lab — see "Not yet done"). The NETCONF `edit-config` XML is
  deliberately left unbuilt (`None`) until the real
  `srl_nokia-interfaces` YANG namespace is confirmed — see "Not yet
  done".
- `propose.py` — the original CLI entry point. Reads current state,
  and only if the interface is genuinely down, builds and prints a
  proposal record (`executed: false`, always). No dependency on
  component #7 at all — still the right tool for a bare state check.
- `diagnose_and_propose.py` — the chained entry point (2026-09-15).
  Same trigger and same proposal record as `propose.py`, plus a
  `"rationale"` field from component #7's diagnosis assistant, called
  only after a real fault is already confirmed. See "Chaining #7 into
  #8" below.

## Running it

```bash
cd ~/netmind-lab/intelligence/remediation-proposal
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python propose.py 172.100.100.11 ethernet-1/1
```

If the interface is already up, it says so and proposes nothing —
that's correct behavior, not a bug. To actually exercise the
proposal path, manually disable the interface first (from `sr_cli` on
`srl1`: `enter candidate`, `interface ethernet-1/1`, `admin-state
disable`, `commit now`), then re-run `propose.py`.

`diagnose_and_propose.py` runs the same way, but additionally needs
this component's `.venv` to have `chromadb` installed (see
`requirements.txt`) and the full stack up — Chroma, Prometheus, and a
host-installed Ollama, the same dependencies component #7 itself
needs (`docs/setup/07-diagnosis-assistant.md`):

```bash
python diagnose_and_propose.py 172.100.100.11 ethernet-1/1
```

## Chaining #7 into #8 (2026-09-15)

Before starting component #9 (the security gate), the explicit
decision this session was: give #9 a realistic diagnosis-driven
proposal to gate, rather than one triggered by a hand-typed CLI arg —
closer to the real end-to-end story (diagnose → propose → gate →
execute).

**The split is strict, and it's the whole design:**
- **The trigger stays exactly what it was** — `state_client.
  get_admin_state()` reading real device state, unchanged. Whether a
  proposal gets built at all, and everything in its
  `json_rpc_set_payload` / `netconf_edit_config_xml` /
  `netconf_commit_xml`, comes from that deterministic check and
  `remediation_templates.py`'s templates — exactly as before.
- **Component #7 is called only after a fault is already confirmed**,
  and its answer is attached as a new `"rationale"` string field —
  read-only, human-facing context for whoever reviews the proposal
  later (component #9's approval step). It is never parsed, never
  used to pick a template, never anywhere near the YANG path or the
  value being set.
- This is the same rule `remediation_templates.py`'s own docstring
  already states for a different reason (an LLM shouldn't author a
  structured config payload) — chaining #7 in as *context* doesn't
  relax that rule. If anything, it's the reason this split needed
  spelling out explicitly before writing `diagnose_and_propose.py`,
  rather than just wiring `assistant.answer()` in wherever seemed
  convenient.
- If the diagnosis call itself fails (Ollama down, Chroma empty, a
  bad response), that degrades to a plain "(rationale unavailable:
  ...)" note in the rationale field — it does not block or alter the
  proposal. A diagnosis outage is not a reason to withhold an already
  confirmed, already-correct fix.

## Verified (2026-09-14, PROGRESS_LOG entries 31–33)

Both protocols have now been proven end-to-end against the live lab,
not just reviewed — component #8 stage 1 is genuinely done for both,
not half-done.

**JSON-RPC:** a real fault was created by hand (`ethernet-1/1`
disabled via `sr_cli`), `propose.py` correctly detected it and
generated a JSON-RPC `set` payload, that exact payload was fired by
hand and returned SR Linux's success shape, and `propose.py`
independently confirmed the interface was genuinely back to
`admin-state enable`.

**NETCONF:** the namespace was captured directly from `srl1`'s own
NETCONF `<hello>` capabilities exchange (`ssh -p 830 -s
admin@<node-ip> netconf`) rather than assumed from documentation —
`urn:nokia.com:srlinux:chassis:interfaces?module=srl_nokia-interfaces`.
The same `<hello>` confirmed SR Linux's NETCONF server advertises
`candidate:1.0` and `confirmed-commit:1.1`, meaning NETCONF here
follows the identical candidate-then-commit two-phase model already
proven via `sr_cli`. Both real RPCs were then fired by hand over a
manual NETCONF-over-SSH session: `netconf_edit_config_xml` returned
`<ok/>` but a JSON-RPC `get` right after still showed `"disable"`,
confirming `edit-config` alone only stages the change into
candidate; `netconf_commit_xml` then returned `<ok/>` and the same
JSON-RPC `get` afterward showed `"enable"` — the device genuinely
changed state. (The manual client `<hello>` advertised only
`base:1.0` to keep the hand-pasted exchange on simple `]]>]]>`
framing rather than RFC 6242 chunked framing.)

## Not yet done

- **`diagnose_and_propose.py` has not yet been run against the live
  stack** — built and reviewed, same "prove it before calling it
  done" pattern as everything else here. That run (confirm a real
  fault, confirm the rationale field comes back grounded rather than
  empty/hallucinated, confirm the proposal record is byte-for-byte
  the same as `propose.py` would have produced) is the next real
  step, not a formality.
- **Scope beyond the one admin-state scenario** — deliberately not
  built until this one is proven end-to-end.
- **Component #9 (security gate)** hasn't started — the natural
  next step now that #8 produces real, verifiable, diagnosis-grounded
  proposals for it to gate.
