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
- **Trigger: standalone first, not yet chained off component #7.**
  `propose.py` takes a node IP and interface name directly rather than
  requiring a real diagnosis-assistant citation as input — same
  "prove the piece in isolation before wiring it into the bigger
  pipeline" pattern `router.py` went through before `assistant.py`
  called it. Chaining a real #7 diagnosis into this is a deliberate
  next step, not done yet.
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
- `propose.py` — the CLI entry point. Reads current state, and only
  if the interface is genuinely down, builds and prints a proposal
  record (`executed: false`, always).

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

- **Chaining a real component #7 diagnosis into this**, rather than
  running standalone against a bare interface name.
- **Scope beyond the one admin-state scenario** — deliberately not
  built until this one is proven end-to-end.
- **Component #9 (security gate)** hasn't started — the natural
  next step now that #8 produces real, verifiable proposals for it
  to gate.
