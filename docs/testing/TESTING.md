# NetMind AI — Testing Guide

One place to find every setup step and verification command for
components #1–8, so nothing gets missed before component #9 (the
security gate) starts gating them. This consolidates what's already
scattered across each component's own README "Running it"/"Verifying
it" sections — those remain the source of truth for design reasoning;
this file exists so a full-stack test pass doesn't require opening
eight READMEs in sequence.

Each section names its real exit criterion — the thing that was
actually run against the live lab and produced evidence, not just "it
compiles" — with a `PROGRESS_LOG.md` entry reference where one exists.
If a command here ever disagrees with a component's own README, the
README is more likely current; update this file to match rather than
the other way around.

**Known gap (`docs/roadmap/BACKLOG.md` item 31):** this file's
per-component sections below currently only cover #1–8 — components #9
(security gate) and #10 (config-push executor) aren't documented here
yet, even though both are built and live-verified (see
`intelligence/security-gate/README.md`, `intelligence/config-push-executor/README.md`,
and `docs/journal/2026-09-phase2-ai-layer-security-gate.md` in the
meantime).

## Automated tests (BACKLOG.md item 30, added 2026-09-17)

Everything below this point is **manual, live-device verification** —
correct and necessary for anything that requires watching real state
change on the actual lab, but it needs the lab up and a human typing
commands. A real subset of what this project verifies doesn't need
either: payload shapes matching what was proven live by hand, the
security gate's hashing/audit/default-deny logic, the config-push
executor's RPC-body parsing (this is a real regression test — it
directly catches the ncclient/lxml bug found and fixed live 2026-09-16,
PROGRESS_LOG entry 43), and the diagnosis assistant's deterministic
PromQL template routing.

Run every component's automated suite in one shot:

```bash
bash scripts/run-all-tests.sh
```

Needs each covered component's `.venv` already created with its
`requirements.txt` installed (`pytest` is now listed there) — the
script skips (doesn't fail) any component whose venv doesn't exist yet
and tells you the exact commands to create it.

Covered: `diagnosis-assistant` (`test_router.py`), `remediation-proposal`
(`test_remediation_templates.py`, `test_state_client.py`),
`security-gate` (`test_gate.py`), `config-push-executor`
(`test_executor.py`). Not covered by design, and correctly so: anything
requiring a real device connection, a real Ollama call, or real
Prometheus/Chroma data — that's what the rest of this file is for.

---

## 0. Environment prerequisites (all components)

Everything below assumes the lab is up. From the `Containerlab` WSL2
distro (not the default WSL distro — see `lab/README.md`):

```bash
wsl -d Containerlab
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/lab-up.sh
```

This syncs the repo to native fs (`~/netmind-lab/`, required — WSL2's
DrvFs under `/mnt/c/...` can't hold the POSIX permission bits SR Linux
needs during commit), restarts any stopped containers, and reconciles
the rest with `clab deploy`. Tear down with:

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/lab-down.sh
```

**After any code change to a component with a local Docker image**
(anomaly-detection, retrieval-index), the image has to be rebuilt —
`clab deploy` does not repull a `:latest` tag that was built locally.
Rebuild commands are listed per component below.

**Anything that runs host-level** (`diagnosis-assistant`,
`remediation-proposal`) uses its own per-component `.venv/`, created
once inside the `Containerlab` distro on native fs — never
`pip install --break-system-packages` against system Python (see
`docs/setup/07-diagnosis-assistant.md` §6). Each such `.venv/` has its
own exclude in `scripts/sync-to-lab.sh` so a sync never wipes it.

Quick reference — container/service endpoints, all reachable directly
from the WSL host shell with no port-publishing (native Linux Docker,
not Docker Desktop):

| Service | Address |
|---|---|
| SR Linix `srl1` | `172.100.100.11` (NETCONF: 830, JSON-RPC: 443) |
| SR Linix `srl2` | `172.100.100.12` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |
| Chroma | `localhost:8000` (host) / `netmind-mgmt` network (containers) |
| Ollama | `http://localhost:11434` (host-installed, not containerized) |
| anomaly-detector metrics | `http://localhost:9805/metrics` |

---

## 1. Network lab (`lab/`)

**Setup:**
```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/lab-up.sh
```

**Verify:**
```bash
docker ps -a --filter "name=clab-netmind-2node-" --format 'table {{.Names}}\t{{.Status}}'
```
Every container (`srl1`, `srl2`, `gnmic`, `prometheus`, `grafana`,
`anomaly-detector`, `chroma`) should show `Up`. If `srl1`/`srl2` show
`Exited`, check why they're actually crashing rather than just
stopped:
```bash
docker start clab-netmind-2node-srl1 && docker logs -f clab-netmind-2node-srl1
```

**Exit criterion:** both SR Linux nodes reachable via `sr_cli`:
```bash
docker exec -it clab-netmind-2node-srl1 sr_cli
```

---

## 2. Telemetry collector (`telemetry/`)

**Setup:** included in `lab-up.sh` (the `gnmic` node deploys with the
rest of the topology) — no separate step.

**Verify — the real streaming check:**
```bash
tail -f ~/netmind-lab/telemetry/output/netmind-telemetry.jsonl
```

**Exit criterion:** interface state/counter events for both `srl1`
and `srl2` arriving roughly every 10 seconds.

---

## 3. Metrics store (`metrics/`)

**Setup:** included in `lab-up.sh`. If `metrics/prometheus/prometheus.yml`
changed, a full redeploy is needed (new bind mounts/ports don't apply
to a running container):
```bash
cd ~/netmind-lab/lab/topologies
sudo clab destroy -t netmind-2node.clab.yml --cleanup
sudo clab deploy -t netmind-2node.clab.yml
```

**Verify:** open `http://localhost:9090` from Windows.
- **Status → Targets** → `netmind-gnmic` job should show `UP`.
- **Graph** → query an interface metric (exact name depends on
  gnmic's `metric-prefix`/`append-subscription-name` config — check
  what's actually exposed if a guessed name doesn't resolve) and
  confirm series exist for both `srl1` and `srl2`.

**Exit criterion:** real interface telemetry queryable through PromQL,
not just sitting in the raw `.jsonl` file from component #2.

---

## 4. Dashboards (`grafana/`)

**Setup:** included in `lab-up.sh`.

**Verify:** open `http://localhost:3000` from Windows (anonymous
viewer access, no login). The **NetMind** folder should show the
provisioned dashboard with live panels reflecting `srl1`/`srl2`
interface state.

**Known bug history worth re-checking after any dashboard JSON edit:**
the `interface_name` vs `name` label key mismatch (fixed and verified
— see `PROGRESS_LOG.md` for the fix and `docs/roadmap/BACKLOG.md`
item 26 for the still-open cosmetic `{{name}}` legend-format
follow-up). If a panel shows "No data" after an edit, check the label
key first before assuming the query itself is wrong.

**Exit criterion:** panels render live, non-empty data sourced from
the same Prometheus verified in component #3.

---

## 5. Anomaly detection (`intelligence/anomaly-detection/`)

**Setup — build the image before first deploy, and after any code change:**
```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/intelligence/anomaly-detection
docker build -t netmind-anomaly-detector:latest .
cd ~/netmind-lab/lab/topologies
sudo clab deploy -t netmind-2node.clab.yml
```

**Verify:**
```bash
curl -s http://localhost:9805/metrics | grep netmind_anomaly
```
Should show `netmind_anomaly_score` / `_detected` / `_baseline_mean` /
`_baseline_stddev` series per interface/stat, once the first
evaluation cycle completes (`EVAL_INTERVAL_SECONDS`, default 30s,
after container start). `z ≈ 0` / `detected = 0` on an idle lab is
the expected healthy state, not a failure sign. Same data also
visible in Grafana's "Anomaly detection" row, no `curl` needed.

**Exit criterion:** real z-scores computed against real rolling
baselines, visible in both Prometheus and Grafana.

---

## 6. Retrieval index (`intelligence/retrieval-index/`)

**Setup — build the image, then ingest:**
```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/intelligence/retrieval-index
docker build -t netmind-retrieval-tools:latest .
cd ~/netmind-lab/lab/topologies
sudo clab deploy -t netmind-2node.clab.yml
docker run --rm --network netmind-mgmt \
  -v ~/netmind-lab:/repo:ro \
  netmind-retrieval-tools:latest python ingest.py
```

**Re-ingest whenever the doc corpus changes, and always after a
`lab-down.sh`/`lab-up.sh` cycle** — Chroma has no persistent storage
yet (`BACKLOG.md` item 16, deliberately deferred, but it has already
cost real debugging time twice — see `PROGRESS_LOG.md` entries 28/29
— so check doc count first if retrieval looks empty, don't assume
code is broken):
```bash
docker run --rm --network netmind-mgmt \
  netmind-retrieval-tools:latest python query.py "why was Kafka skipped for the metrics store?"
```

**Verify:** should return chunks from `docs/roadmap/BACKLOG.md` (item
1) and/or `metrics/README.md` near the top, with a low distance
score. Try more than one real question — that's the actual test, not
just "the container started."

**Exit criterion:** real retrieval against real content.

---

## 7. Diagnosis assistant (`intelligence/diagnosis-assistant/`)

**Setup — host-level, inside the `Containerlab` distro, lab up, Ollama
installed** (`docs/setup/07-diagnosis-assistant.md`):
```bash
cd ~/netmind-lab/intelligence/diagnosis-assistant
python3 -m venv .venv          # first time only
source .venv/bin/activate
pip install -r requirements.txt
```

**Verify — the real, closed-out exit test** (`PROGRESS_LOG.md` entry
29), combining metrics + retrieval + citations in one real question:
```bash
bash run.sh "what's the current traffic rate on ethernet-1/1, and why don't we use Kafka to buffer this telemetry?"
```
Expect a real traffic number (via the `octet_rate` template) cited
with its exact PromQL, plus the Kafka-deferral reasoning cited to a
real `PROGRESS_LOG.md`/`BACKLOG.md` chunk — both halves grounded, not
hallucinated. If retrieval citations come back empty or generic,
check Chroma's doc count first (see component #6 above) before
suspecting `router.py` or `assistant.py`.

**Ad-hoc single question, no `run.sh` wrapper:**
```bash
python assistant.py "ethernet-1/1 just flagged an anomaly on carrier transitions, what's going on?"
```

**Known limits, worth re-checking rather than assuming fixed:**
LLM-generated PromQL validation is syntactic only (Prometheus accepts
it, doesn't mean it's the *right* query); no retry/repair loop on a
rejected generated query — a genuinely off-template question can
still fail cleanly rather than self-correct (`BACKLOG.md` item 23).

**Exit criterion:** one real question through `assistant.py`/`run.sh`
with retrieval, metrics, and citations all showing up correctly
together — met and evidenced in entry 29.

---

## 8. Remediation proposal (`intelligence/remediation-proposal/`)

**Setup — host-level, same pattern as component #7:**
```bash
cd ~/netmind-lab/intelligence/remediation-proposal
python3 -m venv .venv          # first time only
source .venv/bin/activate
pip install -r requirements.txt
```

**Verify — read-only check (safe to run any time, proposes nothing if healthy):**
```bash
python propose.py 172.100.100.11 ethernet-1/1
```
If already `admin-state enable`, prints "nothing to propose" — that's
correct behavior, not a bug.

**Full end-to-end validation (both protocols — only needed after a
change to `remediation_templates.py`, `state_client.py`, or
`propose.py`; both protocols already proven once, see
`PROGRESS_LOG.md` entries 31 and 33):**

1. Create a real fault via `sr_cli` on `srl1`:
   ```
   enter candidate
   interface ethernet-1/1
   admin-state disable
   commit now
   ```
2. Confirm `propose.py` detects it and builds a proposal (`current_value: "disable"`, `executed: false`).
3. **JSON-RPC path** — fire the printed `json_rpc_set_payload` by hand:
   ```bash
   curl -sk -u admin:'NokiaSrl1!' -X POST https://172.100.100.11/jsonrpc \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"set","params":{"commands":[{"action":"update","path":"/interface[name=ethernet-1/1]/admin-state","value":"enable"}]}}'
   ```
   Expect SR Linux's success shape (`{"result": [{}], ...}`).
4. **NETCONF path** (re-disable the interface first if step 3 already re-enabled it) — open a manual NETCONF-over-SSH session:
   ```bash
   ssh -p 830 -s admin@172.100.100.11 netconf
   ```
   Send a client `<hello>` advertising only `base:1.0` (keeps the
   whole exchange on simple `]]>]]>` framing, avoiding RFC 6242
   chunked framing for a hand-pasted session), then the
   `netconf_edit_config_xml` RPC (expect `<rpc-reply><ok/></rpc-reply>`
   — this only stages into candidate, doesn't apply yet), then the
   `netconf_commit_xml` RPC (expect another `<ok/>` — this is what
   actually applies it). Exact XML: see `remediation_templates.py`'s
   `interface_admin_up()` or the README's "Verified" section.
5. Confirm independently via JSON-RPC `get` or `propose.py` re-run
   that the interface is genuinely back to `admin-state enable` —
   the real exit criterion is the device state changing, not the
   RPC reply alone (`edit-config` returning `<ok/>` with the device
   still `disable` is exactly the trap step 5 catches).

**Exit criterion (met, both protocols):** a generated proposal, when
applied by hand, produces the exact device-state change it claimed it
would — proven for JSON-RPC (entry 31) and NETCONF (entry 33)
independently.

**Chained entry point (`diagnose_and_propose.py`) — verified
2026-09-15, PROGRESS_LOG entries 37–38:**
```bash
python diagnose_and_propose.py 172.100.100.11 ethernet-1/1
```
Same trigger and same proposal fields as `propose.py`, plus a
`"rationale"` field from component #7's `assistant.answer()`, added
only after a real fault is confirmed. Needs `chromadb` installed in
this component's `.venv` (see `requirements.txt`) and the full stack
up — Chroma, Prometheus, and a host-installed Ollama. Expect it to
take **2–3 minutes** (a full cold Ollama model load happens on every
call — `ollama_client.py`'s timeout is 300s specifically because a
real run measured 164s), not a quick response. Confirmed live: every
deterministic field matches a plain `propose.py` run on the same
state exactly, and the `"rationale"` field comes back grounded
rather than hallucinated — though its depth depends on whether
there's real content (docs/metrics) to ground it in; a synthetic
fault like the one used for this test won't produce a deeply
specific rationale, and that's expected, not a bug.

**Not yet covered by any test here:** any scenario beyond the one
admin-state case.

---

## 9. Security gate (`intelligence/security-gate/`)

**Setup — host-level, same pattern as #7/#8:**
```bash
cd ~/netmind-lab/intelligence/security-gate
python3 -m venv .venv          # first time only
source .venv/bin/activate
pip install -r requirements.txt
```

**Verified 2026-09-15, PROGRESS_LOG entry 40:**
```bash
python gate.py 172.100.100.11 ethernet-1/1
```
1. Create a real fault first (same `sr_cli` steps as component #8).
2. Run `gate.py`, review the printed proposal, and type `y` at the
   prompt. Confirm `audit_log.jsonl` gets a new line with
   `"decision": "approved"` and a `proposal_hash`.
3. Create a fault again, run `gate.py` again, and this time press
   Enter with no input at the prompt. **This is the actual
   default-deny test** — confirm it's recorded as
   `"decision": "rejected"`.
4. Inspect `audit_log.jsonl` (`cat` or `python -m json.tool` per
   line) — confirm both entries are well-formed JSON with real
   timestamps. **Do not expect the two `proposal_hash` values to
   differ** — `proposal_hash()` deliberately excludes `rationale`, so
   the same interface in the same state hashes identically across
   runs regardless of how the rationale text varies. Confirmed live:
   both hashes came back identical, which is correct, not a bug.
5. Confirm on the device itself (`sr_cli`, `info interface
   ethernet-1/1`) that the interface's real state didn't change after
   the "approved" run — component #10 doesn't exist, so approval
   should have zero effect on the wire. Confirmed live: still
   `admin-state disable` after approval.

**Exit criterion (met):** a real approval and a real rejection, both
correctly recorded, default-deny proven with an actual blank-Enter
test, and the "nothing applied" claim checked against the live device
rather than just trusted.

---

## Full-stack smoke test (all components in one pass)

Useful before starting component #9, or after any lab-wide change
(image rebuild, topology edit, laptop restart):

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/lab-up.sh
docker ps -a --filter "name=clab-netmind-2node-" --format 'table {{.Names}}\t{{.Status}}'   # #1
tail -n 5 ~/netmind-lab/telemetry/output/netmind-telemetry.jsonl                            # #2
curl -s http://localhost:9805/metrics | grep netmind_anomaly                                # #5
docker run --rm --network netmind-mgmt netmind-retrieval-tools:latest \
  python query.py "why was Kafka skipped for the metrics store?"                            # #6
cd ~/netmind-lab/intelligence/diagnosis-assistant && source .venv/bin/activate && \
  bash run.sh "what's the current traffic rate on ethernet-1/1?"                            # #7
cd ~/netmind-lab/intelligence/remediation-proposal && source .venv/bin/activate && \
  python propose.py 172.100.100.11 ethernet-1/1                                             # #8
```
Components #3 and #4 (Prometheus/Grafana) are browser checks, not
scriptable in this pass — open `http://localhost:9090` and
`http://localhost:3000` separately.

If any step here fails, that's real signal worth chasing before #9 —
a security gate sitting in front of a pipeline with an undiagnosed
gap just gates a broken thing more safely.
