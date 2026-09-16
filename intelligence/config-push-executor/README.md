# intelligence/config-push-executor/

Component #10 — the config-push executor. Applies an *approved*
proposal (component #9's output) to the device. Per the roadmap, this
is "the one component that isn't new learning" — it's the same
NETCONF/RESTCONF config-push pattern this project's background already
has production experience with, unlike gNMI telemetry or the AI layer.

## Design decisions (2026-09-16)

- **Chained into `gate.py`, not a separate script.** Approved via
  AskUserQuestion during design: execution happens in the same run as
  approval, immediately after a `y`. Mirrors the #7→#8 and #8→#9
  chaining pattern already used twice in this project — one run, one
  decision, one execution, one correlated audit trail — rather than a
  standalone executor that scans `audit_log.jsonl` for unexecuted
  approvals (a real, more production-realistic design, but one that
  needs an "already executed" marker to avoid double-applying; not
  needed yet at this project's current scale).
- **Both protocols supported, chosen via `--protocol`.** Also an
  explicit choice over picking one: `remediation_templates.py` already
  builds both the `json_rpc_set_payload` and the
  `netconf_edit_config_xml`/`netconf_commit_xml` pair on every
  proposal, so supporting both at execution time costs nothing
  upstream. Default is `json-rpc` — the path already live-verified
  end to end, including through today's credential-scoping
  investigation (PROGRESS_LOG entry 41). `netconf` exists in the code
  but has **not** been run live yet — see "Not yet done" below.
- **Full `admin` credential, per PROGRESS_LOG entry 41's decision.**
  Every component in this project has used the lab's one shared
  `admin`/`NokiaSrl1!` credential; entry 41 investigated whether a
  scoped credential was possible for this component specifically and
  found, live, that it isn't — not on this SR Linux image via NETCONF
  or JSON-RPC. The real security boundary is component #9's
  human-approval gate and audit log, not credential scoping. This
  isn't a shortcut taken here — it's the direct consequence of a
  separately verified finding, stated plainly in `executor.py`'s
  docstring rather than left implicit.
- **Never trusts an RPC's "ok" reply alone.** `execute()` always
  re-reads the device's real state via `state_client.get_admin_state()`
  after firing either protocol's RPC, and raises `ExecutionError` if
  the confirmed value doesn't match what was proposed. This is a
  direct response to PROGRESS_LOG entry 33's real finding: SR Linux's
  NETCONF `edit-config` can return `<ok/>` while only staging into
  candidate, leaving device state genuinely unchanged until a separate
  `commit` RPC lands — a reply that "looks successful" isn't proof by
  itself, on this device, and this component doesn't pretend otherwise.
- **The audit log now has two event types, not one.** `gate.py`'s
  `audit_log.jsonl` previously recorded only a decision (approved/
  rejected). Now that execution is real, a second entry type
  (`"event": "execution"`) is appended after an approved change is
  applied, correlated to the decision entry by `proposal_hash` —
  **not** a mutated version of the decision entry, since the log stays
  append-only. A failed execution is recorded too, not just
  successes: an approval that couldn't actually be applied is exactly
  the kind of event this audit trail exists to catch.
  **Schema note:** the two audit entries from entry 40's earlier live
  test predate the `"event"` field and won't have it — worth knowing
  if anything ever parses the full log programmatically, not
  something silently glossed over.

## Layout

- `executor.py` — `execute_json_rpc()`, `execute_netconf()`, and
  `execute()` (picks the protocol, then always re-verifies against
  live device state regardless of which one ran).
- `requirements.txt` — `requests` (already used elsewhere in this
  project) plus `ncclient` (new — the standard Python NETCONF client
  library, not previously used anywhere in this project since every
  prior NETCONF RPC was applied by hand over raw SSH).

## Running it

Not run standalone — invoked through `gate.py`:

```bash
cd ~/netmind-lab/intelligence/security-gate
source .venv/bin/activate
pip install -r ../config-push-executor/requirements.txt  # ncclient, new dependency
python gate.py 172.100.100.11 ethernet-1/1                    # json-rpc, default
python gate.py 172.100.100.11 ethernet-1/1 --protocol netconf # not yet live-tested
```

## Verified (2026-09-16, PROGRESS_LOG entry 42)

JSON-RPC path run end-to-end against a real fault: `ethernet-1/1`
disabled, `gate.py` run and approved, `execute_json_rpc()` fired the
real `set` payload, and the post-execution `get_admin_state()` re-check
confirmed the device's real state matched the proposed value. This is
this project's first live proof of the full #7→#8→#9→#10 chain working
together, not just each component verified in isolation. The audit
log's new two-event shape (`"event": "decision"` / `"event":
"execution"`, correlated by `proposal_hash`) came out exactly as
designed.

## Not yet done

- **Live test, netconf path — genuinely unverified.** `execute_netconf()`
  uses `ncclient.manager.dispatch()` to send the exact RPC XML
  `remediation_templates.py` already built, stripped of its outer
  `<rpc>` envelope (ncclient builds and tracks its own). This exact
  call shape has not been exercised against `srl1` yet — `ncclient`
  itself hasn't been used anywhere in this project before today. Don't
  treat this path as proven until it's actually been run and the
  device's real state checked afterward, same discipline as every
  other protocol claim in this project.
- **Audit log tamper-evidence** — unchanged from component #9, still
  not built (file permissions or a hash chain).
- **The "already executed" marker problem** doesn't exist yet since
  execution is chained synchronously into approval — would need
  designing for real if this component is ever split into a separate
  standalone executor later (see design decisions above).
