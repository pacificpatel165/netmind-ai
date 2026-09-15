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

## Not yet done

- **Not run against the live stack yet** — built and reviewed, same
  "prove it before calling it done" pattern as every other component
  here. The real test: propose a fault, approve it, confirm
  `audit_log.jsonl` gets a correct entry; propose again (or a fresh
  fault), reject it (including via a blank Enter, to prove
  default-deny is real), confirm that's recorded correctly too.
- **Least-privilege credential scoping** — deliberately deferred, see
  above. Needs live verification of what SR Linux's local-AAA role
  system actually supports before it's designed, not guessed at.
- **Audit log tamper-evidence** beyond "the code only appends" —
  file permissions or a hash chain, not built yet.
- **Component #10 (config-push executor)** doesn't exist — nothing
  approved through this gate can actually be applied to a device
  yet, by design.
