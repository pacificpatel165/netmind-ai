# ADR-002 — Phase 2: AI Layer, Closed-Loop Remediation, Security Gate (components #5–#10)

**Status:** Done, live-verified across all six components, both write-back
protocols proven. **Dates:** 2026-09-10 through 2026-09-16.
**Components:** #5 anomaly detection, #6 retrieval index, #7 diagnosis
assistant, #8 remediation proposal, #9 security gate, #10 config-push
executor.

## Context

This phase is the project's actual thesis, stated plainly in the root
README: the difference between a system that can *answer questions about* a
network and one that can *act on* it safely. A read-only RAG assistant over
logs is a solved, well-understood pattern (and this author already has one
shipped elsewhere — LightYear-AI). The interesting and harder half is closing
the loop back to real device configuration, with a human approving every
write and a security design that makes an untrustworthy AI proposal harmless
by construction, rather than trusted by default.

Six components, one continuous chain: **detect → diagnose → propose → gate →
execute**, with an audit trail threaded through the whole thing. Each was
proved standalone before being chained into the next — the same "prove a
piece, then chain" discipline used throughout — so that by the time the full
pipeline ran end to end for the first time (entry 42), every link in it had
already been independently verified in isolation.

## Decisions

**No ML/LLM in anomaly detection (#5).** A rolling-baseline z-score over
`avg_over_time`/`stddev_over_time` PromQL subqueries, not a trained model.
The component's actual job at this stage is orchestration — turning
statistics Prometheus already computes into a metric a human or downstream
component can act on — not reimplementing statistics. A real model is an
explicit future step, deferred until this baseline's real limits are
understood from real data (`BACKLOG.md` item 13), not chosen speculatively.

**The LLM's authority is bounded by construction, not by prompt instruction.**
This is the single most important design decision of the phase, and it
threads through every component from #7 onward. The diagnosis assistant (#7)
retrieves and answers with citations, but the actual metrics query is a
hybrid: fixed, parameterized PromQL templates are tried first, and only a
genuinely off-template question falls through to LLM-generated PromQL — which
is then validated by actually running it against Prometheus before ever being
trusted, not accepted on the model's say-so. The remediation proposal
component (#8) goes further: the LLM is never in the path that decides what
YANG path or value to change at all. `remediation_templates.py`'s
docstring states this directly — the config-change payloads are 100%
deterministic templates; the LLM's only role anywhere near a config write is
producing human-readable rationale text, attached as a clearly-labeled,
read-only field that a human approver is explicitly told to verify
independently, never evidence. A rejected or hallucinated LLM output can
degrade the *explanation* quality; it can never touch the actual change being
proposed.

**Explicit human approval, default-deny, literally.** The security gate (#9)
treats anything other than a literal `y`/`yes` — including a blank Enter — as
a rejection. There is no code path anywhere in this component that applies a
change without an explicit yes.

**Credential scoping was investigated live, not designed from documentation
alone, and the honest answer changed the architecture.** General SR Linux
documentation implied per-YANG-leaf authorization granularity was available.
Live testing against the actual device (configuring a real restricted role,
testing reads and writes, isolating variables one at a time down to a single
clean before/after/before test flipping only the `superuser` flag) proved
that non-superuser local AAA roles get zero YANG-path data access via NETCONF
or JSON-RPC on this platform — not restricted access, none. Rather than quietly
downgrade the claim or keep chasing a dead end, the decision was made
explicitly (via a direct choice presented and answered): component #10 uses
the same full credential every component has used, and the real security
boundary for this project is the approval gate and the audit log, not
credential scoping. The real, untried alternatives (sr_cli command-list
scoping, TACACS+ external authorization, a newer SR Linux release) are
recorded on the backlog rather than closed off as impossible.

**Two protocols, not one, at the execution layer (#10).** JSON-RPC `set` and
NETCONF `edit-config`+`commit` are both built by #8's templates on every
proposal, and both are supported at execution time via a flag — since the
upstream cost of supporting both is zero, there was no reason to pick one.

**Never trust an RPC's own "success" reply.** This is a rule earned the hard
way, not assumed: a real test (entry 33) proved SR Linux's NETCONF
`edit-config` can return `<ok/>` while only staging a change into the
candidate datastore, leaving live device state completely unchanged until a
separate `commit` RPC lands. Every execution path re-reads real device state
afterward and treats a mismatch as a failure, regardless of what the RPC
reply claimed.

## What went wrong, and what it taught

Three real bugs in this phase are worth calling out specifically, because
each one was diagnosed by reading real system state or real source code
rather than guessed at, and each one changed something about how later work
was done.

**A label-key assumption, stated once, silently propagated through three
components over three days** (entry 26). Component #4's dashboard
description asserted interface metrics carried a label key `name`; component
#5's anomaly detector and component #7's PromQL templates both copied that
assumption unchecked. The real label key, confirmed by a direct Prometheus
query, was `interface_name` — `name` never existed on these series at all.
The practical damage: every anomaly score this project had ever emitted was
silently labeled `interface="unknown"`, merging both nodes and every port
into one indistinguishable bucket, and it passed component #5's original
verification because *something* still rendered on the dashboard — the
failure was in per-interface correctness, not in whether data flowed at all,
and a visual check never caught that distinction. The lesson applied from
that point forward: check a raw query against the actual source of truth the
first time a label or field name is used in code, not on the fourth time it's
copied from an earlier doc.

**Ollama's cold-load timing had no real margin, and the first fix attempt
would have just re-guessed a bigger number.** A chained diagnosis+proposal
call timed out at 180 seconds; instead of arbitrarily raising the timeout,
the actual cause was isolated — confirmed Ollama was healthy, confirmed
memory wasn't starved, then timed a direct call, which took 164 seconds, only
16 seconds under the old timeout. The real cause (`keep_alive: 0` means every
call pays a full cold model load) explains why 180s never had real margin.
The fix (300s) carries the measured number in its own docstring, so the
value has a stated reason rather than being an arbitrary constant that will
look unexplainable to a future reader.

**An `ncclient` failure traced all the way to a library-internal type check,
found by reading the installed source, not guessing at the API.** The first
live NETCONF execution failed with `Invalid tag name`, deep inside
`ncclient`'s own code. Rather than iterate blindly on the calling code, the
actual installed package was inspected directly on the lab host —
`grep`-ing for where `dispatch` was really defined, reading `Dispatch.request()`'s
real source, confirming it checks `lxml.etree.iselement()` specifically,
and confirming the stdlib `xml.etree.ElementTree` object being passed in
fails that check silently. The fix was one import statement, but finding it
required verifying the actual library contract rather than assuming one. A
second gotcha during the same debugging session, worth remembering as a
process lesson on its own: the identical traceback reappeared after the fix
was written, not because the fix was wrong, but because the fix had only
been written to the source-of-truth repo and never actually re-synced to the
native lab path before retrying — caught by `grep`-checking the file that
actually ran, rather than re-theorizing about the code a second time.

## Verified

Every component in this phase closed with a real, live exit criterion, and
the full chain has now been proven end-to-end twice — once per write-back
protocol — with independent device-state confirmation each time, not a
trusted RPC reply: a real fault (`ethernet-1/1` manually disabled) diagnosed
by #7 with a correctly grounded, cited explanation; a deterministic
remediation proposal built by #8 exactly matching hand-verified payload
shapes; an explicit human approval and a correctly-shaped, append-only audit
trail from #9 (including a caught-and-corrected mistake in this project's own
test instructions, proving the verification process itself is taken as
seriously as the code); and a real device-state transition applied and
independently confirmed by #10, via both JSON-RPC and NETCONF.

## Open, tracked on the backlog, not forgotten

Audit log tamper-evidence beyond "the code only appends," whether
`audit_log.jsonl` belongs in git, the real alternatives for credential
scoping named above, a validation gap in `state_client.py` that lets a
silently-empty authorized read pass as legitimate state, and `security-gate`
missing its own dedicated virtualenv are all real, named items — see
`docs/roadmap/BACKLOG.md`.
