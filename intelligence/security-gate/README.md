# intelligence/security-gate/

Component #9 — the security gate: the differentiator, per the
roadmap, that makes this an architecture story rather than an
AI-integration demo. Every proposal from component #8 is meant to
pass through here before anything could ever apply it.

## Design decisions (2026-09-15)

- **Scope, stage 1: explicit approval + audit log. Credential
  scoping deliberately deferred.** The roadmap names three things
  for this component: least-privilege credential scoping, explicit
  human approval (no default-approve), and an immutable audit log.
  Every component built so far reuses the lab's single
  `admin`/`NokiaSrl1!` credential. Building a genuinely scoped SR
  Linux AAA role — one restricted to just the `admin-state` leaf this
  project's remediation actually touches — means first checking,
  live against `srl1`, whether this image's local-AAA system
  actually supports that kind of restriction. That's a real,
  separately-verified next step (same discipline every NETCONF/
  JSON-RPC claim in this project has gone through), not something to
  guess at and bolt on. Stage 1 builds the two pieces that don't
  depend on that answer.
- **Default-deny, literally.** The approval prompt treats anything
  other than an explicit `y`/`yes` — including a blank Enter — as a
  rejection. There is no code path anywhere in this component that
  applies a change without an explicit yes.
- **Audit log: append-only JSONL, honest about what that does and
  doesn't guarantee.** `gate.py` only ever opens `audit_log.jsonl` in
  `"a"` mode. That's real, but it is append-only in this code's own
  behavior, not filesystem-enforced or tamper-evident against someone
  editing the file directly. Real tamper-evidence — `chattr +a`, or a
  hash chain linking each entry to the previous one — is a legitimate
  stage-2 item, not something claimed here that isn't actually true
  yet.
- **Logs the decision, not an executed change.** Component #10 (the
  config-push executor) doesn't exist yet, so nothing in this project
  can actually apply a change to a device yet, approved or not. Every
  audit entry records what was proposed, what was decided, and by
  whom — proof of a decision, ready for #10 to consume later, not
  proof of an action that hasn't happened.
- **Rationale shown, but visually and textually de-emphasized.**
  Component #8's `rationale` field (from component #7) is printed
  last, labeled explicitly as a best-effort AI explanation to verify
  independently — not evidence. This follows directly from
  `PROGRESS_LOG.md` entry 38's real finding: a `rationale` field's
  depth depends entirely on whether there's real content to ground
  it in, and it can come back honest-but-thin. A human approving a
  device change should see that caveat every time, not just once in
  a design doc.
- **Reuses component #8 as a library, doesn't duplicate it.** `gate.py`
  imports `diagnose_and_propose()` from the sibling
  `remediation-proposal/` directory — same pattern component #8 used
  to reuse component #7, and component #7 used to reuse component #6.

## Layout

- `gate.py` — the whole component. `proposal_hash()` (SHA-256 over
  just the deterministic proposal fields — excludes `rationale`
  deliberately, since its wording can vary run to run without the
  underlying proposal changing), `display_proposal()`,
  `append_audit_entry()`, and `gate()` tying it together.
- `audit_log.jsonl` — created on first run, one JSON line per
  decision. Not yet decided whether this should be committed to git
  (an audit trail arguably belongs in version history) or left as
  local generated state (consistent with `telemetry/output/` and
  Chroma's data) — deliberately left open rather than decided
  unilaterally; worth a real conversation once there's actual audit
  data to look at.

## Running it

Host-level, same placement as components #7 and #8:

```bash
cd ~/netmind-lab/intelligence/security-gate
python3 -m venv .venv          # first time only
source .venv/bin/activate
pip install -r requirements.txt
python gate.py 172.100.100.11 ethernet-1/1
```

Same dependencies and expected runtime as `diagnose_and_propose.py`
(a full Ollama cold-load, ~2-3 minutes) — see
`intelligence/remediation-proposal/README.md` and
`docs/testing/TESTING.md`.

## Verified (2026-09-15, PROGRESS_LOG entry 40)

Both real paths tested, not just reviewed: a rejection via a blank
Enter (the actual proof default-deny is real, not a docstring claim)
and an approval via `y`, each checked against `audit_log.jsonl`
afterward. For the approval, the "nothing was applied" claim was
checked against the live device itself (`sr_cli`,
`info interface ethernet-1/1`) — still `admin-state disable`
afterward, confirming component #10's absence genuinely means
nothing changed on the wire, not just that the printed message
claimed so.

**Worth noting:** the two audit entries' `proposal_hash` values came
back identical across the reject-then-approve runs — this is the
design working correctly, not a bug. `proposal_hash()` deliberately
excludes `rationale` (see `gate.py`'s docstring), so the same
interface in the same state hashes the same way regardless of how
differently component #7 phrased the rationale each run. An earlier
version of this component's own testing instructions wrongly expected
the hashes to differ for that reason — corrected in entry 40.

## Credential scoping — investigated live, real ceiling found (2026-09-16, PROGRESS_LOG entry 41)

Not deferred anymore — actually tested against `srl1`'s real local AAA
system, and the answer turned out to be a hard platform limit rather
than a design choice. General Nokia documentation implied a
`role`/`rule`/`path`/`action` model down to individual YANG leaves;
live exploration of this device's actual `system aaa authorization
role <name>` command tree found no such structure (only `cli`,
`netconf`, `services`, `superuser`, `tacacs` exist at the role level
on `ghcr.io/nokia/srlinux:latest`, 26.7.2).

A `netmind-remediation` role and user were configured (`superuser
false`, `services [json-rpc netconf]`, restricted `netconf
allowed-operations`) and live-tested via both JSON-RPC read and write.
Both failed — a write was denied outright, a read came back silently
empty rather than erroring. Isolated by testing one variable at a
time (ruling out `allow-command-list` defaults and a missing `cli`
service first) down to a single clean before/after/before test:
flipping only `superuser` to `true` made both the read and write work
immediately; flipping it back to `false` broke both again, with
nothing else changed.

**The real, live-proven ceiling:** on this SR Linux image, a
non-superuser local AAA role gets *no* YANG-path data access at all
via NETCONF or JSON-RPC — not restricted access, none. `services` and
`netconf allowed-operations` only gate which RPCs a session may
attempt; whether an RPC can touch any path data underneath is
superuser-or-nothing. The one place real least-privilege restriction
does work on this device is `cli allow-command-list`/
`deny-command-list` — but that only governs interactive `sr_cli`
sessions, not the JSON-RPC/NETCONF path this project's components are
built on.

**Decision:** stop chasing credential scoping on this protocol path.
Component #10 uses the same full `admin`/`NokiaSrl1!` credential every
other component has used. The real security boundary for this project
is component #9's human-approval gate and audit log (both already
built and live-verified — see "Verified" above), not credential
scoping. Switching the write path to `sr_cli` to get real scoping was
considered and explicitly declined, since it would mean reworking
`state_client.py`/`remediation_templates.py`'s protocol choice for the
whole project rather than adding a component.

The `netmind-remediation` role/user are left configured on the device
as a documented record of what was tried, not torn down — inert for
this project's purposes now.

A real, separate gap surfaced during this investigation, worth fixing
regardless: `state_client.py`'s `DeviceQueryError` only checks for an
`"error"` key or a malformed result-list shape — it never validates
that a returned value looks like real device state. The scoped
credential's authorization-driven empty read (`{}` instead of
`"disable"`) sailed through that check exactly like a legitimate
read would. Not fixed yet — flagged here so it isn't lost.

## Not yet done

- **`state_client.py`'s `DeviceQueryError` doesn't catch a silently
  empty/malformed value** — see the credential-scoping section above.
  Real gap, not yet fixed.
- **Audit log tamper-evidence** beyond "the code only appends" —
  file permissions or a hash chain, not built yet.
- **Component #10 (config-push executor) now exists** (2026-09-16,
  see `../config-push-executor/README.md`), chained directly into
  `gate.py` — an approval now actually attempts execution, using the
  full `admin` credential per the decision above. Not yet live-tested
  either protocol path; that's the immediate next step.
