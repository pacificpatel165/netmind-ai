# Component #8 setup: remediation proposal

Step-by-step "how" per this folder's convention. For the *why* — both
NETCONF and JSON-RPC built for the same change, deterministic templates
only (never LLM-authored), the standalone-then-chained trigger design —
see `intelligence/remediation-proposal/README.md` and `PROGRESS_LOG.md`
entries dated 2026-09-14/15.

Prerequisite: component #1 (lab) is deployed. `diagnose_and_propose.py`
(the chained entry point) additionally needs component #7's full stack
— Chroma, Prometheus, a host-installed Ollama — see
`07-diagnosis-assistant.md`.

---

## 1. Python environment

Host-level, same placement as component #7. Since 2026-09-17
(`BACKLOG.md` item 32), every `intelligence/` component shares **one**
venv rather than its own — if you've already created
`intelligence/.venv` for another component, skip straight to running
it below.

If `python3 -m venv` isn't available yet on this distro, install it
first (same package-name gotcha as component #7's setup —
`python3-venv` is not the real package name on this distro; it's tied
to the specific interpreter version):

```bash
sudo apt update
sudo apt install -y python3-pip python3.11-venv   # or whatever `python3 --version` reports
```

Create the shared venv once:

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/intelligence
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate
```

## 2. Running it — standalone trigger (no component #7 dependency)

```bash
cd ~/netmind-lab/intelligence/remediation-proposal
source ../.venv/bin/activate
python propose.py 172.100.100.11 ethernet-1/1
```

If the interface is already up, it correctly says so and proposes
nothing — not a bug. To exercise the proposal path, manually disable
the interface first (`sr_cli` on `srl1`: `enter candidate`, `interface
ethernet-1/1`, `admin-state disable`, `commit now`), then re-run.

## 3. Running it — chained through component #7

Needs the full diagnosis-assistant stack up (Chroma, Prometheus,
Ollama — see `07-diagnosis-assistant.md`):

```bash
python diagnose_and_propose.py 172.100.100.11 ethernet-1/1
```

Expect a real Ollama cold-load on the first call after Ollama starts
(~2–3 minutes, see `docs/testing/TESTING.md`) — not a hang.

## 4. Verify

Both protocols were proven live end-to-end (`PROGRESS_LOG.md` entries
31–33): a real fault created by hand, `propose.py` detecting it and
generating a correct JSON-RPC `set` payload / NETCONF `edit-config`+
`commit` pair, each fired and independently confirmed against real
device state afterward — not just a trusted "ok" reply. Re-running
`propose.py` after manually toggling the interface, and confirming its
output matches what actually changed on the device via `sr_cli`, is
the same exit criterion for a fresh setup.

Full design detail, the trigger/rationale split, and the two verified
end-to-end runs: `intelligence/remediation-proposal/README.md`.

## 5. Automated tests (optional, no lab or device needed)

`test_remediation_templates.py` pins the JSON-RPC/NETCONF payload
shapes against the exact values proven live above; `test_state_client.py`
covers `get_admin_state()`'s error handling, including the real
silently-empty-read regression from entry 41. Uses the shared
`intelligence/.venv` from §1 — see `docs/testing/TESTING.md`.
