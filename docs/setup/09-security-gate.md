# Component #9 setup: security gate

Step-by-step "how" per this folder's convention. For the *why* —
explicit default-deny approval, append-only (not yet tamper-evident)
audit log, the live-proven credential-scoping ceiling on this SR Linux
image — see `intelligence/security-gate/README.md` and
`PROGRESS_LOG.md` entries dated 2026-09-15/16.

Prerequisite: component #8 (remediation proposal) is set up and
working — `gate.py` imports `diagnose_and_propose()` from
`remediation-proposal/` as a library, so it needs that component's full
stack (lab, Chroma, Prometheus, Ollama).

---

## 1. Python environment

Shares `intelligence/.venv` (item 32) with every other host-level
component. If you've already created it (see `08-remediation-proposal.md`
§1), nothing new to install — `security-gate`'s own `requirements.txt`
is a subset of what's already in the shared venv's union file.

```bash
cd ~/netmind-lab/intelligence/security-gate
source ../.venv/bin/activate
```

**If you're on a machine that still has the old per-component venv
layout** (from before 2026-09-17's item 32 consolidation), create
`security-gate`'s own venv instead — this was a real, live-found gap
(entry 43: every `gate.py` run was silently borrowing
`remediation-proposal/.venv` because `security-gate/.venv` never
existed) fixed the same day by item 33:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Running it

```bash
python gate.py 172.100.100.11 ethernet-1/1
```

Same dependencies and expected runtime as `diagnose_and_propose.py`
directly — a full Ollama cold-load, roughly 2–3 minutes on first call.
You'll be prompted to approve or reject the proposed change: anything
other than a literal `y`/`yes` — including a blank Enter — is a
rejection, by design (default-deny, no exceptions).

## 3. Verify

```bash
cat audit_log.jsonl
```

Should show one JSON line per decision made (`"event": "decision"`,
plus `"event": "execution"` once component #10 is chained in — see
`10-config-push-executor.md`). Live-verified 2026-09-15 (entry 40):
a rejection via blank Enter and an approval via `y`, each checked
against this file afterward, with the "nothing applied" claim for the
pre-#10 approval independently confirmed against the live device
itself (`sr_cli`) — not just the printed message trusted at face value.

Full design detail, the credential-scoping investigation and its
conclusion, and the audit-log schema: `intelligence/security-gate/README.md`.

## 4. Automated tests (optional, no lab or device needed)

`test_gate.py` covers `proposal_hash()`'s rationale-exclusion behavior,
the audit log's schema/correlation, and default-deny logic with
`builtins.input` mocked — no live lab required. Uses the shared
`intelligence/.venv` from §1.
