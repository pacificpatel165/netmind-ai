# Component #10 setup: config-push executor

Step-by-step "how" per this folder's convention. For the *why* —
chained into `gate.py` rather than standalone, both protocols supported
via `--protocol`, the full `admin` credential (per entry 41's
credential-scoping finding), never trusting an RPC's "ok" reply alone —
see `intelligence/config-push-executor/README.md` and `PROGRESS_LOG.md`
entries dated 2026-09-16.

Prerequisite: component #9 (security gate) is set up and working — this
component isn't run standalone, only through `gate.py`.

---

## 1. Python environment

Shares `intelligence/.venv` (item 32) with every other host-level
component, same as component #9. `ncclient` (this component's one new
dependency, for the NETCONF path) is already included in the shared
venv's union `requirements.txt` — nothing extra to install if that venv
already exists.

If you're still on the older per-component layout, install this
component's dependency into `security-gate`'s venv specifically (this
is how it was originally set up, before the shared venv existed):

```bash
cd ~/netmind-lab/intelligence/security-gate
source .venv/bin/activate
pip install -r ../config-push-executor/requirements.txt
```

## 2. Running it (through `gate.py`, not standalone)

```bash
cd ~/netmind-lab/intelligence/security-gate
source ../.venv/bin/activate   # or ./.venv/bin/activate on the older per-component layout
python gate.py 172.100.100.11 ethernet-1/1                     # json-rpc (default)
python gate.py 172.100.100.11 ethernet-1/1 --protocol netconf  # netconf
```

An approval (`y`/`yes` at the prompt) now actually attempts execution
against the live device, using the same full `admin`/`NokiaSrl1!`
credential every other component uses.

## 3. Verify

Both protocol paths are live-verified end-to-end (`PROGRESS_LOG.md`
entries 42–43): a real fault created by hand, approved through
`gate.py`, executed, and independently re-confirmed against live
device state via `state_client.get_admin_state()` — not just a trusted
RPC reply. Check the result the same way:

```bash
cat ~/netmind-lab/intelligence/security-gate/audit_log.jsonl
```

Should show a `"event": "decision"` entry followed by a correlated
`"event": "execution"` entry (same `proposal_hash`) recording whether
the RPC succeeded and whether the device's real state confirmed it.
Cross-check against `sr_cli` (`info interface ethernet-1/1`) — the
actual proof, not just what the audit log claims.

Full design detail, the real ncclient/lxml bug found and fixed on the
NETCONF path, and the audit-log two-event schema:
`intelligence/config-push-executor/README.md`.

## 4. Automated tests (optional, no lab or device needed)

`test_executor.py` covers `_parse_rpc_body()` (a direct regression test
for the ncclient/lxml bug above), protocol dispatch, and the
always-reverify-device-state behavior, all against mocked RPC
responses. Uses the shared `intelligence/.venv` from §1.
