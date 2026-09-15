# NetMind AI — Progress Log

Running log of design sessions and implementation work, one entry per session. Newest entry on top. This is the working record; `docs/roadmap/SIGNAL_PATH.md` is the stable plan, `docs/architecture/OVERVIEW.md` is the stable design — this file is where decisions get made before they're stable enough to land there.

---

## Component map

NetMind AI breaks into 11 top-level components, grouped by role, in the order data flows through the system:

**Substrate**
1. **Network lab** — Containerlab + Kubernetes/Cilium cluster simulating the devices NetMind observes and configures. Nothing else works without this existing first.

**Telemetry & storage (phase 4 territory)**
2. **Telemetry collector** — gNMI/gRPC streaming off the lab, normalized for ingestion. The one genuinely new protocol in the project.
3. **Metrics store** — Prometheus (+ Kafka buffer). Learn PromQL and retention/downsampling trade-offs, don't just wire it up.
4. **Dashboards** — Grafana on top of Prometheus. Low design complexity; makes the pipeline visibly real.

**Intelligence layer (phase 5 territory)**
5. **Anomaly detection** — scheduled job, rolling baseline first, a real model (isolation forest or similar) only once the baseline's limits are understood. No LLM involved.
6. **Retrieval index** — runbooks/past incidents chunked, embedded, stored in a vector DB (Chroma or pgvector). Runs continuously in the background.
7. **Diagnosis assistant** — retrieval-grounded LLM: parallel vector search + structured Prometheus/log query, assembled into a prompt, sent to a local model (Ollama), answered with citations.
8. **Remediation proposal** — the diagnosis assistant's output extended one step further into a concrete NETCONF/RESTCONF config change.

**Security & control plane (the differentiator)**
9. **Security gate** — every proposal from #8 passes through here: least-privilege credential scoping, explicit human approval (no default-approve), immutable audit log. The component that makes this an architecture story, not an AI-integration demo.
10. **Config-push executor** — the NETCONF/RESTCONF client that applies an *approved* change, using the scoped credential from #9. Directly reuses production background — the one component that isn't new learning.

**Cross-cutting**
11. **IaC / environment provisioning** — Terraform/Ansible to stand up and tear down #1, #3, #4. Runs alongside the others rather than sitting in the data flow.

Build order follows the numbering: 1→4 is phase 4 (telemetry), 5→10 is phase 5 (AI layer + security gate), 11 runs alongside 1 and 3 throughout.

---

## Session log

### 2026-09-15 (36) — `diagnose_and_propose.py`: two real bugs caught in review, fixed before ever running it

**Focus:** a code review of entry 35's build, before the still-owed live test, caught two real problems worth fixing first rather than discovering during the test itself.

**Bug 1 — the rationale question silently doubled the Ollama calls.** `RATIONALE_QUESTION_TEMPLATE`'s original wording matched no `promql_templates.py` keyword, so `router.py`'s `match_template()` always returned `None` and every rationale call fell through to the LLM-generated-PromQL fallback — one wasted Ollama call generating a PromQL query nobody needed, on top of the real answer call, and exercising the fallback's known no-repair-loop gap (`BACKLOG.md` item 23) on every single proposal for no reason. Fixed by rewording the question to genuinely ask about recent carrier transition history (a real, useful thing to ground the rationale in — a manually disabled interface with a recent flap history might be masking a problem the fix alone won't address), which also happens to match the `flap_history` template's keywords and routes through the fixed template instead of the fallback. Deliberate double benefit, not a keyword chosen just to dodge the bug.

**Bug 2 — a missing `chromadb` install would have looked like a live-service outage.** The broad `except Exception` around the rationale-generation call would have caught `ImportError` too, turning a skipped `pip install -r requirements.txt` into a `"(rationale unavailable: No module named 'chromadb')"` note that reads like Ollama or Chroma being down. Fixed by splitting the `import assistant` out into its own `try/except ImportError`, re-raised as a pointed `RuntimeError` naming the actual fix, separate from the genuinely-broad catch around runtime failures (Ollama unreachable, Chroma empty, etc.).

**Not yet done:** the live test itself — still the same one described in entry 35.

**Next:** run it.
**Open questions:** none blocking.

### 2026-09-15 (35) — Chained component #7 into #8: `diagnose_and_propose.py`

**Focus:** the decision posed at the end of entry 33/34 — security gate (#9) now, against `propose.py` as-is, vs. chaining a real component #7 diagnosis into #8 first so #9 has a realistic diagnosis-driven trigger to gate. Decided: chain first.

**Design confirmed explicitly before writing code** (asked and approved this session): the deterministic state-check trigger (`state_client.get_admin_state` → `remediation_templates.interface_admin_up`) stays completely unchanged; component #7's `assistant.answer()` is called only after a real fault is already confirmed, and its output is attached to the proposal record as a new `"rationale"` string field — read-only, human-facing, never parsed back into code, never near the YANG path or value. Same rule `remediation_templates.py` already enforces for a different reason (LLM never authors the structured payload); chaining #7 in as context doesn't relax it.

**Built:** `intelligence/remediation-proposal/diagnose_and_propose.py` — a second entry point alongside the original `propose.py` (kept, unchanged, still the right tool for a bare state check with no component #7 dependency). Imports `assistant.answer()` from the sibling `diagnosis-assistant/` directory via a `sys.path` insert (same "reuse the proven piece as a library" pattern component #7 used for component #6's Chroma collection), deferred to inside the function so `assistant.py`'s own imports (chromadb, the Ollama client) are only required on the path that actually needs them. A rationale-generation failure (Ollama down, Chroma empty, ...) degrades to a plain note in the rationale field rather than blocking the proposal — a diagnosis outage shouldn't withhold an already-confirmed fix.

**Also updated:** `requirements.txt` (added `chromadb==0.5.23`, pinned to match `diagnosis-assistant/requirements.txt` and `retrieval-index`'s server image — see that component's own "known gotcha" about client/server pin drift); `README.md` (new "Chaining #7 into #8" section, layout/running-it entries for the new file, "Not yet done" updated).

**Not yet done:** `diagnose_and_propose.py` has not been run against the live stack yet — built and reviewed only. The real exit test: create a fault, run it, confirm the rationale field comes back grounded (not empty, not hallucinated) and the proposal record is otherwise identical to what `propose.py` would have produced for the same state.

**Next:** run that live test, then start component #9 (security gate) against the now-chained trigger.
**Open questions:** none blocking.

### 2026-09-15 (34) — Consolidated testing guide, before starting component #9

**Focus:** before starting the security gate (#9) — which exists specifically to sit in front of #8's proposals and everything upstream of it — consolidate every component's setup/verify commands into one place (`docs/testing/TESTING.md`), so nothing already proven gets silently missed or forgotten while building the gate. Each per-component README's own "Running it"/"Verifying it" section remains the source of truth for the reasoning behind each step; this file exists purely so a full-stack pass doesn't require opening eight READMEs in sequence.

**Built `docs/testing/TESTING.md`:** one section per component (#1–8), each with its real setup commands, its real verification commands (pulled from the actual READMEs and, where a genuine end-to-end proof exists, the exact command and expected result from its `PROGRESS_LOG.md` entry — e.g. component #7's entry 29 exit test, component #8's entries 31/33 JSON-RPC and NETCONF proofs), and an explicit "Exit criterion" line distinguishing what's actually been proven against the live lab from what's only been reviewed. Added a "Full-stack smoke test" section at the end — one script-shaped pass through everything scriptable (Prometheus/Grafana stay manual browser checks) — for exactly this moment: before #9 starts gating a pipeline, know for real whether every piece it's gating still works.

**Not yet done:** this file will need a fresh pass once #9 exists (it'll need its own setup/verify section, and #8's "how to fire a proposal" instructions will need an "…and now it goes through the gate first" caveat).

**Next:** decide the #9 vs. #7→#8-chaining question posed at the end of entry 33, then start on whichever is chosen.
**Open questions:** none blocking.

### 2026-09-14 (33) — Component #8 stage 1 closed: NETCONF fired and confirmed, both protocols proven

**Focus:** finish the "Not yet done" item from entry 32 — the NETCONF payloads had a confirmed namespace but had never actually been applied against the live lab. Same rigor already given to JSON-RPC (entry 31) was owed here before calling "both protocols, built together" (the entry 30 decision) genuinely done.

**Method:** manual NETCONF-over-SSH session (`ssh -p 830 -s admin@172.100.100.11 netconf`), client `<hello>` deliberately advertised only `base:1.0` (not `base:1.1`) so the whole exchange stays on simple `]]>]]>` end-of-message framing rather than RFC 6242 chunked framing — avoids a second framing variable while hand-pasting RPCs. Sent the real `netconf_edit_config_xml` generated by `remediation_templates.py`, watched for `<rpc-reply>`, independently checked device state via JSON-RPC `get` before committing.

**The full test, for real:**
1. Sent `edit-config` (message-id 101) — got `<rpc-reply><ok/></rpc-reply>`.
2. Checked immediately via JSON-RPC `get`: `admin-state` still `"disable"` — proves `edit-config` alone only stages into candidate, doesn't apply. Real evidence for the two-phase model, not just documentation.
3. First SSH session was interrupted (Ctrl-C) before `<commit/>` went out — candidate edit survived because SR Linux's candidate datastore is device-level, not session-scoped (same store `sr_cli`'s `enter candidate` uses).
4. Reopened the NETCONF session, sent `<commit/>` (message-id 102) — got `<rpc-reply><ok/></rpc-reply>`.
5. Checked via JSON-RPC `get` again: `admin-state` now `"enable"` — the device genuinely changed state.

**Component #8 stage 1 is now done for both protocols**, not half-done: JSON-RPC (entry 31) and NETCONF (this entry) have each independently been fired against the live lab and independently verified to produce the claimed effect.

**Not yet done:** chaining a real component #7 diagnosis into `propose.py` instead of running it standalone with a bare interface name; any scenario beyond the one admin-state case; component #9 (security gate) design hasn't started.

**Next:** decide between (a) starting component #9 (security gate — the differentiator, and the natural next step now that #8 produces real, verifiable proposals to gate) or (b) chaining #7→#8 first so the security gate has a realistic diagnosis-driven trigger to sit in front of, rather than a bare CLI arg. Worth a deliberate decision, not a default.
**Open questions:** none blocking.

### 2026-09-14 (32) — NETCONF namespace confirmed live, template finished

**Focus:** finish the NETCONF half of component #8's `interface_admin_up` template — blocked since entry 30/31 on confirming the real `srl_nokia-interfaces` YANG module namespace rather than guessing it.

**Confirmed directly from the device, not documentation:** captured `srl1`'s own NETCONF `<hello>` capabilities exchange (`ssh -p 830 -s admin@172.100.100.11 netconf` — first attempt used the wrong argument order, `-s` doesn't take its own argument, the subsystem name goes where the remote command would). The real namespace: `urn:nokia.com:srlinux:chassis:interfaces?module=srl_nokia-interfaces`. Also confirmed from the same `<hello>`: SR Linux's NETCONF server advertises `candidate:1.0` and `confirmed-commit:1.1` — meaning NETCONF here follows the identical candidate-then-commit two-phase model already proven manually via `sr_cli` in entry 31, not a single-shot edit.

**`remediation_templates.py` finished:** `interface_admin_up` now returns real `netconf_edit_config_xml` (stages the change into candidate, using the confirmed namespace) and a separate `netconf_commit_xml` (applies it) — both protocols built together, per the explicit decision in entry 30.

**Not yet done:** unlike the JSON-RPC half (entry 31, fired and verified for real), the NETCONF payloads have only been built with a confirmed namespace — not yet actually applied against the live lab. Same one-time manual validation still owed for this protocol.

**Next:** fire both NETCONF RPCs by hand against a real fault, confirm the interface actually changes state — the same rigor the JSON-RPC half already got, before calling "both protocols" genuinely done rather than half-done.
**Open questions:** none blocking.

### 2026-09-14 (31) — Component #8 stage 1 core: built and verified end-to-end for real

**Focus:** build the standalone JSON-RPC half of component #8 (deferring NETCONF pending its YANG namespace, entry 30) and actually prove the whole loop against the live lab — not just that the code runs, but that a generated proposal, when applied, genuinely fixes the problem it was built from.

**Built:** `intelligence/remediation-proposal/` — `state_client.py` (JSON-RPC `get`, confirmed schema from entry 30), `remediation_templates.py` (`interface_admin_up`, deterministic only — see the module's own docstring for why an LLM never authors this component's structured payload, unlike component #7's hybrid PromQL strategy), `propose.py` (CLI: read real state, propose only if actually broken). `scripts/sync-to-lab.sh` got a third `.venv` exclude for this component's own environment, same fix shape as component #7's.

**The full test, for real:**
1. `propose.py` against both `srl1`/`srl2`'s `ethernet-1/1` while healthy — correctly reported nothing to propose.
2. Created a real fault by hand in `sr_cli` — the first attempt to set `admin-state disable` failed with a parsing error because the CLI was in `running` (read-only) mode, not `candidate`; `enter candidate` first fixed it. Worth noting since it's a real, easy-to-hit SR Linux CLI gotcha, not a bug in anything built here.
3. `propose.py` against the now-actually-broken interface returned a correct proposal: `current_value: "disable"`, a real JSON-RPC `set` payload, `executed: false`.
4. Fired that exact generated payload by hand via `curl` — SR Linux returned `{"result": [{}], ...}`, its success shape.
5. Ran `propose.py` again — confirmed independently, through the same code path that detected the fault, that the interface was genuinely back to `admin-state enable`.

That closes the loop: the proposal wasn't just plausible-looking JSON, it was a payload that a real device actually accepted and that produced the exact effect it claimed it would. This is what "the AI proposes, but the output is real and verifiable" needs to mean for the security-gate story (#9) to hold up under questioning later — asserted here with evidence, not just designed on paper.

**Not yet done:** NETCONF `edit-config` XML, still blocked on confirming the real `srl_nokia-interfaces` YANG namespace (entry 30); chaining a real component #7 diagnosis into `propose.py` instead of running it standalone; any scenario beyond the one admin-state case.

**Next:** confirm the YANG namespace (via `gnmic ... capabilities` or a raw NETCONF `<hello>`) and finish the NETCONF half, since "both, built together" was the explicit decision for this component.
**Open questions:** none blocking.

### 2026-09-14 (30) — Component #8 kickoff: confirmed real NETCONF + JSON-RPC reachability on the lab

**Focus:** before designing component #8 (remediation proposal), verify — not assume — that this lab's SR Linux image (`ghcr.io/nokia/srlinux:latest`) actually exposes a config-push interface, given the roadmap names NETCONF/RESTCONF as the flagship differentiator and nothing had confirmed that against this specific lab yet. Also an explicit sequencing decision this session: continue building NetMind (component #8) rather than pausing for the personal platform or the Kubernetes/AWS gap-closing from the original `signal-path-plan.md` sequence — both still open, deliberately deferred again, recorded in the project's living plan doc.

**Checked directly on `srl1` via `sr_cli`, not assumed:**
- `info system netconf-server mgmt` — enabled by default, riding NETCONF-over-SSH on port 830 (`system ssh-server mgmt-netconf`, `disable-shell true` — a dedicated NETCONF subsystem listener, not an interactive shell, which is correct and expected).
- `info system json-rpc-server` — enabled by default, HTTP and HTTPS both, bound to the `mgmt` network-instance, HTTPS via a self-signed `clab-profile` TLS profile.
- **Important terminology correction:** SR Linux does not implement standard RESTCONF. Its actual config-push HTTP API is called JSON-RPC, using the same `srl_nokia` YANG model family gnmic already streams telemetry from for components #2 onward — not a third schema to learn, and worth naming accurately going forward rather than calling it "RESTCONF" out of habit from the original roadmap wording.

**Reachability tested for real, from the host shell (not inside the container) — this matters because `diagnosis-assistant` and any future remediation component run host-level, same placement decision as component #7:**
```
timeout 3 bash -c 'cat < /dev/null > /dev/tcp/172.100.100.11/830' && echo reachable
# -> port 830 reachable
curl -sk -u admin:'NokiaSrl1!' -X POST https://172.100.100.11/jsonrpc -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"get","params":{"commands":[{"path":"/system/name/host-name","datastore":"state"}]}}'
# -> {"result": ["srl1"], "id": 1, "jsonrpc": "2.0"}
```
Both confirmed reachable directly, with no port-publishing needed — this is native Linux Docker (the Containerlab distro), not Docker Desktop, so the `netmind-mgmt` bridge network's container IPs (`172.100.100.11`/`.12`) are directly routable from the host shell, unlike Prometheus/Chroma which needed explicit host-port publishing to cross the Windows/WSL2 boundary in this project's other flows.

**Not yet decided:** which interface component #8 actually uses to push config — NETCONF or JSON-RPC or both; what specific problem-to-remediation mappings make sense on a 2-node lab with no fault-injection mechanism yet; whether the same hybrid (template-first, LLM-fallback, validate-before-trust) pattern from component #7 applies here too; and what a "proposal" actually is as output, since components #9 (security gate) and #10 (executor) don't exist yet — nothing should execute anything from #8.

**Next:** work through those open design questions before writing any code for #8.
**Open questions:** see above — all open, none blocking further discussion.

### 2026-09-13 (29) — Component #7 stage 1: closed out

**Focus:** the actual exit criterion (`BACKLOG.md` item 24) — one real question through `assistant.py` with retrieval, metrics, and citations all showing up correctly together.

**Blocking issue found and fixed first:** Chroma's doc count was `0` — confirmed by direct query, and exactly as suspected in entry 28: `lab-down.sh`/`lab-up.sh` (run to redeploy the fixed anomaly-detector image) also destroyed and recreated the Chroma container, and it has no persistent storage (`BACKLOG.md` item 16, deferred since 2026-09-10). Rebuilt `netmind-retrieval-tools:latest` and re-ran `ingest.py` (211 chunks from 13 documents this time — doc count grew since component #6's original ingest, expected). Re-verified with `query.py` before trusting it: real, relevant matches for "why was Kafka skipped," `docs/roadmap/BACKLOG.md` item 1 and `metrics/README.md` both in the top 3.

**The actual exit test:**
```
bash run.sh "what's the current traffic rate on ethernet-1/1, and why don't we use Kafka to buffer this telemetry?"
```
Answer came back with both halves grounded and cited correctly: the real traffic number (`27.5`, combined in+out octet rate, via the new `octet_rate` template from entry 28) cited with its exact PromQL, and the Kafka-deferral reasoning cited to `PROGRESS_LOG.md` chunk 71 with an accurate paraphrase of the real decision (not hallucinated) — a genuinely correct, dual-grounded, cited answer. This is the first time retrieval and metrics have both worked *and* been exercised together in the same real answer.

**Component #7 stage 1 is done.** Updated `docs/architecture/component-diagram.md`: added Ollama and `diagnosis-assistant` to the diagram and component-status table (both host-installed, dashed lines, not topology nodes), and the status note now covers components #1-7. The rendered artifact still needs republishing to match (not done this session — do that before treating the diagram as fully in sync).

**What this session actually proved, end to end, worth restating:** a real per-interface labeling bug in a previously-"verified" component (#5) got found, root-caused, fixed, deployed, and re-verified with concrete evidence rather than assumption; a genuinely fragile LLM-fallback failure got debugged with real visibility (not guessed at) and fixed by promoting a common question to a proper template rather than patching the symptom; and the Chroma-persistence gap that had been purely theoretical since day one turned into a real, felt problem, exactly on schedule for a "prove the need first" project.

**Not yet done:** the rendered component-diagram artifact (republish); `BACKLOG.md` item 16 (Chroma persistence) is worth revisiting now that it's cost real time twice — not decided yet, worth a real discussion rather than reflexively building it; the LLM-fallback path (item 23) still has no repair loop, now correctly scoped to "the next genuinely off-template question that comes up" rather than the traffic-rate case (which got its own template instead); remediation proposal (component #8) hasn't been started.

**Next:** decide whether to revisit Chroma/Prometheus persistent storage now (items 3 and 16) before starting component #8, or move to component #8 design as-is and let persistence stay deferred a while longer — open question for the next session.
**Open questions:** persistent storage timing (see above) — not blocking, but worth a real decision rather than continuing to defer by default.

### 2026-09-13 (28) — LLM-fallback path exercised for real, added error visibility, promoted traffic-rate to a template

**Focus:** the first off-template question ("what's the current inbound traffic rate on ethernet-1/1?") returned a bare "I don't have any relevant metrics or docs" from `assistant.py`, with no way to tell why. User pushed back on accepting that as fine without seeing the actual cause.

**Gap found and fixed first:** `router.py`'s `generate_and_validate()` discarded the LLM's generated PromQL text on failure, returning only Prometheus's error — which gives a character offset with nothing to point it at. Fixed to include `candidate query was: {candidate!r}` in the returned error string, so a rejected query is actually debuggable instead of a dead end.

**What the fallback actually generated:** `netmind_interface_state_srl_nokia_interfaces_interface_statistics_in_octets[1m] by {interface_name="ethernet-1/1"}` — invalid PromQL. Two things worth separating: the label key is correct (`interface_name`, exactly what the fallback prompt was told to use after entry 26's fix — that correction holds even under LLM-generated queries, not just the fixed templates), but the model bolted on `by {...}` after a bare range-vector selector, which isn't legal syntax anywhere in PromQL (`by` only follows an aggregation function like `sum(...) by (...)`, with parentheses, not braces, not standalone).

**This is not a new bug — it's `BACKLOG.md` item 23 happening for real,** and the outcome was actually the *good* one: `generate_and_validate()` caught the invalid query and reported failure rather than silently returning bad data. The hybrid design's validate-before-trust step did exactly its job.

**Fixed anyway, because the underlying question is too common to leave fragile:** added `octet_rate()` to `promql_templates.py` (combined in+out byte rate, same shape as the existing error/discard/flap templates) and four new keywords (`traffic`, `octet`, `throughput`, `bandwidth`) to `KEYWORD_TEMPLATES`. "What's the traffic rate" is one of the most basic diagnostic questions there is — it shouldn't depend on an 8B model getting PromQL aggregation syntax right. The LLM-fallback path itself is left exactly as-is (still stage-1, still no repair loop) — item 23 stays open for the next *actually* off-template question that comes up, rather than fixed here.

**Not yet done:** the new `octet_rate` template hasn't been re-run against the live lab yet to confirm it now returns real data for the same question; the Chroma retrieval-index count also hasn't been confirmed yet (suspected empty after the `lab-down.sh`/`lab-up.sh` redeploy in entry 27, since `BACKLOG.md` item 16 — no persistent Chroma storage — means a full redeploy wipes it; needs `ingest.py` re-run if so).

**Next:** re-run the traffic-rate question through the real router with the new template in place; confirm Chroma's doc count and re-ingest if it's 0; then attempt the full stage-1 exit criterion (item 24) — one real question exercising retrieval, metrics, and citations together.
**Open questions:** none blocking.

### 2026-09-13 (27) — `interface_name` fix confirmed deployed and working

**Focus:** Verify entry 26's fix actually took effect on the running lab, not just in committed code — user pushed back on accepting the fix as "done" until it was proven with real, unambiguous output rather than an assumption.

**How it was verified:** rather than trust the full `assistant.py`/Ollama path (slow, and a wrong-sounding LLM answer would leave the actual data question unresolved), tested the router/template layer directly and in isolation:
```python
import router
router.resolve_metrics('any anomaly score for ethernet-1/1?', lambda p: '')
```
This exercises the real, rebuilt `detector.py`'s live Prometheus data through the real `promql_templates.py`/`router.py`, without waiting on or depending on Ollama at all (the fallback `generate_fn` is never called for a templated question) — the cleanest possible isolation of exactly the thing being verified.

**Result:** every returned series showed `interface="ethernet-1/1"` — not `interface="unknown"` — with small, sane z-scores (`in_octets = -0.267`, well under the 3.0 flag threshold, consistent with a quiet lab). `used_fallback: False` confirms it went through the fast template path. This is definitive: the bug described in entry 26 is fixed in the actually-running system, not just in source.

**A separate, unrelated hiccup along the way:** a direct `curl` with a hand-quoted PromQL query (`...{interface_name="ethernet-1/1"}`) failed with a Prometheus parse error at the shell/terminal level (likely bracket/quote auto-pairing mangling the pasted command) — not a real bug, and not the same thing as the fix being broken; confirmed by the fact that the same query, run from Python via `requests` inside `router.py`, worked cleanly against the same Prometheus instance. Noted `--data-urlencode` as the shell-safe way to run this class of query by hand in the future, in case it comes up again.

**Component #5's stage 1 closeout (log 15) is re-affirmed** now that the label fix is confirmed live — the "verified" status holds again, this time actually checked against real per-interface output rather than "something renders on Grafana."

**Next:** component #7's actual exit criterion (item 24 in `docs/roadmap/BACKLOG.md`) is still open — a full run through `assistant.py`/`run.sh` with retrieval + metrics + citations all correct, including a question that exercises the LLM-generated PromQL fallback path (item 23) at least once, since that path hasn't been touched by any test yet.
**Open questions:** none blocking.

### 2026-09-13 (26) — Bug found and fixed: wrong Prometheus label key, retroactively affects component #5

**Focus:** User feedback — the diagnosis assistant's first live run against real data returned "no data" for every metrics query, and simply patching that symptom wasn't enough; asked for a proper re-analysis rather than another quick fix.

**What was wrong:** every raw gnmic-sourced interface metric was assumed to carry the label key `name` for the interface (stated as fact in component #4's dashboard description, then reused unchecked in component #5's `detector.py`, then copied again into component #7's new `promql_templates.py`). Direct inspection — `curl http://localhost:9090/api/v1/query?query=...in_error_packets` — showed the real label key is `interface_name`, and `name` never existed on these series at all.

**Impact, worse than it first looked:** this wasn't just a component #7 bug. `detector.py`'s `series_by_interface()` and `evaluate_leaf()` were reading `.get("name", "unknown")`, which silently returned `"unknown"` for every single series since component #5 was built — meaning every `netmind_anomaly_*` Gauge this component has ever emitted has been labeled `interface="unknown"`, merging both nodes and every port into one indistinguishable bucket. This slipped through component #5's original "verified" closeout (entry 15) because data still rendered on the Grafana anomaly panel — the failure was in per-interface labeling, not in whether data flowed, so a visual check never caught it. Found now only because component #7 queries the same raw metrics directly and hit empty results immediately.

**Fixed:**
- `intelligence/anomaly-detection/detector.py` — both `.get("name", ...)` calls corrected to `.get("interface_name", ...)`, with a docstring explaining the bug, when/how it was found, and its scope.
- `intelligence/diagnosis-assistant/promql_templates.py` — `error_rate`/`discard_rate`/`flap_history` corrected from `{name="..."}` to `{interface_name="..."}`. (`anomaly_score`/`anomaly_flagged` were already correct — those query the detector's own Gauges, which use `interface`, not the raw gnmic label — left unchanged.)
- `intelligence/diagnosis-assistant/router.py` — the LLM-fallback prompt now explicitly tells the model to use `interface_name`, not `interface` or `name`, so the fallback path doesn't repeat the same mistake blind.
- `grafana/dashboards/netmind-overview.json` — top-level `description` corrected; it had stated the wrong label key as a "read directly from Prometheus" fact. The `{{name}}` legend-format strings on raw-metric panels are left as-is: they only affect legend display text (would render blank, not wrong data) since no panel actually filters on `name` — cosmetic, tracked as a follow-up, not fixed here. The anomaly panel's `{{interface}} {{stat}}` legend format was already correct syntax; it will start showing real interface names once the `detector.py` fix is deployed, no JSON change needed there.

**Not yet done:** none of these fixes have been rebuilt/redeployed yet — the anomaly-detector Docker image needs rebuilding (`docker build` inside `intelligence/anomaly-detection/`) and the lab needs a redeploy for `detector.py`'s fix to take effect; component #7 needs a live re-run to confirm `error_rate`/`flap_history`/`discard_rate` now return real data instead of "no data returned".

**Lesson to carry forward:** an assumption stated once (component #4's dashboard description, 2026-09-10) got copied forward into two more components without being re-verified against the actual system, over three days. Worth checking a raw `curl`/Explore query against the source of truth once, the first time a label name is used in code, rather than trusting a prior doc's claim — cheap now, expensive after it's been copied three times.

**Next:** rebuild the anomaly-detector image, redeploy the lab, and re-run `assistant.py` (via the new `run.sh`, see entry 25's "Next") against a real question to confirm the fix actually resolves the end-to-end symptom.
**Open questions:** none blocking.

### 2026-09-13 (25) — Correction: proper venv, not a system-Python shortcut
**Focus:** User feedback, directly and rightly critical: the pip install steps I'd given for `intelligence/diagnosis-assistant/` were a shortcut, not professional practice, and I should slow down and do it properly rather than optimizing for finishing fast.
**What was wrong:** `docs/setup/07-diagnosis-assistant.md` §6 told the user to `sudo apt install python3-pip` then `pip install -r requirements.txt` directly against the system interpreter. That hit Debian's PEP 668 "externally-managed-environment" protection (by design, not a bug) — and the reflex fix would have been `--break-system-packages`, which silences the protection instead of addressing why it exists: installing project dependencies into the system Python risks clashing with whatever apt itself depends on, with no isolation from anything else that runs Python in this distro later.
**Fixed properly:** every Python component that runs host-level (currently just this one — the others are all containerized, where this problem doesn't arise) now gets its own virtual environment: `python3 -m venv .venv`, activate, then `pip install -r requirements.txt`, documented in both `docs/setup/07-diagnosis-assistant.md` §6 and `intelligence/diagnosis-assistant/README.md`. Added `intelligence/diagnosis-assistant/.gitignore` (`.venv/`) since a venv is local and disposable, never something to commit.
**Hit and fixed — a second mistake caught before it shipped:** the first draft of this fix claimed the venv would "persist untouched" across `sync-to-lab.sh` runs without actually checking that. It wouldn't have — `sync-to-lab.sh`'s `rsync --delete` only preserves paths explicitly excluded, and `.venv/` only exists natively, never in the Windows-drive repo. Same exact bug class as the containerlab-generated-state issue that broke `srl1`/`srl2` restarts (entry 18/19's fix). Caught it before telling the user it worked, and added the same fix shape: `.venv/` excluded in `scripts/sync-to-lab.sh` alongside the existing `clab-netmind-2node/` exclude.
**Lesson to carry forward:** any future host-level Python component in this project gets a venv from the start, documented alongside its own setup, not retrofitted after hitting the same error again.
**Next:** re-run the pip install (now via venv) and the actual end-to-end test of `assistant.py` against the live lab — still the real exit criterion for component #7 stage 1.
**Open questions:** none blocking.

### 2026-09-13 (24) — Component #7: first build (retrieval + hybrid metrics + Ollama)
**Focus:** Build the actual diagnosis assistant now that every design decision is made — the PromQL template set, the hybrid router, and the prompt assembly that ties retrieval + metrics + Ollama together.
**Built:**
- `intelligence/diagnosis-assistant/promql_templates.py` — the fixed template set: `error_rate`, `discard_rate`, `flap_history`, `anomaly_score`, `anomaly_flagged`, keyed by keyword (flap/transition/carrier → flap_history, anomaly/z-score → anomaly_score, error → error_rate, discard/drop → discard_rate).
- `router.py` — `match_template()` extracts an interface name (`ethernet-\d+/\d+`) and keyword-matches to a template; `generate_and_validate()` is the LLM-fallback path — asks Ollama for one PromQL query restricted to the known metric names, then actually runs it against Prometheus to validate before trusting the result (a syntactically-invalid or hallucinated-metric query fails there, visibly, not silently).
- `prometheus_client.py` / `retrieval_client.py` — thin clients factored out of the pattern component #5's `detector.py` and component #6's `query.py` already established, reused rather than reinvented.
- `ollama_client.py` — single-shot `/api/generate` call with `keep_alive: 0` set directly in the request body — the confirmed-working fix from entry (22), not the CLI env var that didn't work.
- `assistant.py` — the actual entry point: retrieval and metrics are independent lookups (true to "parallel" in the roadmap description), assembled into one prompt, sent to Llama 3.1 8B, answered with citations.
- `intelligence/diagnosis-assistant/README.md` — design decisions + layout + known limits of this first build.
**Design decision made in the course of building:** this whole component runs **host-level, not containerized** — reaches Chroma/Prometheus via their host-published ports (`localhost:8000`/`:9090`) and Ollama via `localhost:11434`, no container network involved. Same reasoning as Ollama's own placement (entry 23): avoids re-solving the persistent-storage problem for a third component, avoids Docker overhead on the memory-tight WSL2 VM.
**Not yet done:** no end-to-end run against the live lab yet — all six files compile cleanly (checked locally) but haven't been executed against the real Ollama/Prometheus/Chroma stack. That run is the actual exit criterion, same pattern as every prior component. LLM-generated-PromQL validation is syntactic only (Prometheus accepts it, not "it's the right query") and there's no retry/repair loop on a rejected generated query — both real, named limits, not oversights.
**Next:** run `assistant.py` against the live lab with a real question, confirm retrieval + metrics + citation all show up correctly in the answer — that closes out component #7 stage 1.
**Open questions:** none blocking.

### 2026-09-13 (23) — Component #7: placement and provider scope decided
**Focus:** Close out the two remaining open design decisions for component #7 from entry (22) — Ollama's placement, and whether to build a multi-provider abstraction now.
**Decided:**
- **Ollama stays host-installed, not containerized.** Its ~4.9GB model file already lives on `~/.ollama` (native filesystem) and survives every `clab destroy`/`clab deploy` cycle for free; containerizing it without solving persistent storage first would mean re-downloading that model on every teardown — the same unsolved permission problem already deferred twice (Prometheus, item 3; Chroma, item 16). Also avoids adding Docker overhead on top of the WSL2 VM's proven-tight memory budget (entry 22).
- **Provider scope stays local-only — no Groq/Gemini abstraction built now.** 8B already proved itself correct with proper citations; there's no concrete gap for a second provider to close. Building one speculatively would break this project's established pattern (Kafka, retention, auto re-ingestion all deferred the same way — prove the need first).
**Updated:** `docs/setup/07-diagnosis-assistant.md` (all four component #7 design decisions now recorded together — model, placement, provider scope, PromQL strategy), `docs/roadmap/BACKLOG.md` (item 22 resolved).
**Next:** all design decisions for component #7 are made. Start the actual build: the fixed PromQL template set, the router (template match vs. LLM-generated-PromQL fallback), the fallback's validation step, and the prompt assembly that combines Chroma retrieval + Prometheus metrics + the question for Ollama.
**Open questions:** none blocking.

### 2026-09-11 (22) — Component #7 model decision: Llama 3.1 8B
**Focus:** Settle the 3B-vs-8B model question from entry (21) with real measurements, not a guess.
**Verified — correctness:** `benchmark.sh` run with the lab up. 3B answered fast (29.3s) but got a fact wrong — it said the anomaly "may be related to the recent decision to add a Kafka buffer," when the actual decision (BACKLOG.md item 1) was to skip Kafka. 8B answered slower (67.2s) but correctly, twice, with proper inline source citations ("Source: docs/roadmap/BACKLOG.md, item 1") — exactly the "answered with citations" behavior component #7 needs.
**Hit and fixed — memory:** Benchmark's own peak-RSS numbers were bogus (measured the lightweight `ollama run` client, not the `ollama serve` daemon actually holding the model). Real check: `free -h` inside the WSL2 VM showed available memory drop to ~1.5GB (9.6-9.7GB used of 11GiB) while 8B was loaded. Traced the host-level pressure further via Windows Task Manager (`Get-Process | Sort-Object WS`) and confirmed `vmmemWSL` was genuinely the dominant consumer (~7.8GB) — not unrelated Windows apps, an earlier false lead from a confounded `wsl --shutdown` reading. `OLLAMA_KEEP_ALIVE=0` set on the `ollama run` CLI did not free the memory (stayed pinned ~9.6GB across multiple checks) because `ollama serve` was already running as a background daemon before that variable was set — a client-side env var doesn't reach an already-running server. `ollama stop llama3.1:8b` reliably did work, confirmed: memory returned to the exact pre-load baseline (4.5GB used / 6.7GB available) immediately.
**Decided:** **Llama 3.1 8B**, called with `"keep_alive": 0` in the API request body (the correct production mechanism — Ollama's `/api/generate` endpoint honors this natively per-request, unlike the CLI env var) so the model unloads automatically after each response rather than staying resident.
**Updated:** `docs/setup/07-diagnosis-assistant.md` §5 (full decision writeup), `docs/roadmap/BACKLOG.md` (item 21 resolved, new item 22 for the still-open placement/provider-abstraction questions).
**Next:** decide Ollama's placement (host vs. topology node) and whether to build the Groq/Gemini provider abstraction now or defer it; then start building the actual template set + prompt assembly for the hybrid PromQL strategy from entry (21).
**Open questions:** none blocking.

### 2026-09-11 (21) — Component #7 kickoff: diagnosis assistant, part 1
**Focus:** First real design decisions for component #7 (retrieval-grounded LLM: parallel vector search + structured Prometheus query, assembled into a prompt, answered with citations).
**Decided:**
- **Structured metrics query: hybrid.** A small set of fixed, parameterized PromQL templates (error rate, flap/transition history, anomaly score for a given interface) tried first — safe and testable, same "prove the simple thing first" pattern every prior component used. Only when a question doesn't match a known template does it fall back to asking the model to generate PromQL directly, which gets validated before ever running against Prometheus. Chosen over templates-only (too narrow — can't answer anything unanticipated) and over LLM-generated-only (every query would depend on the model getting metric names/syntax right, with real risk of a malformed or hallucinated query).
- **Model choice: not yet decided — benchmarking 3B vs. 8B first**, deliberately, rather than picking either by default. `llama3.2:3b` already confirmed working (see entry 19); `llama3.1:8b` benchmark built but not yet run.
**Built:**
- `intelligence/diagnosis-assistant/benchmark_prompt.txt` — a representative prompt (retrieved doc chunk + metrics summary + question) matching the actual shape component #7 will send, not a generic test string.
- `intelligence/diagnosis-assistant/benchmark.sh` — pulls `llama3.1:8b`, times both it and `llama3.2:3b` against the same prompt (wall time + peak RSS), meant to be run with the lab already up so the numbers reflect real contention against the other 7 containers.
- `docs/setup/07-diagnosis-assistant.md` — updated with the benchmark run instructions and the hybrid PromQL decision write-up.
**Not yet built:** the actual template set, the router between templates/LLM-fallback, the retrieval+metrics prompt assembly, and the local-vs-Groq/Gemini provider abstraction — all pending the model-choice benchmark result.
**Next:** run `benchmark.sh`, pick a model from the real numbers, then start building the template set and prompt assembly.
**Open questions:** none blocking.

### 2026-09-11 (20) — Documentation audit: install steps weren't all captured
**Focus:** User asked whether the recent install commands (rsync, personal SSH key, zstd, Ollama) had actually made it into `docs/setup/01-network-lab-environment.md` or anywhere else — they hadn't. Went through every doc that's supposed to make this environment reproducible and closed the gaps.
**Found missing:** `docs/setup/01-network-lab-environment.md` (the file whose own stated purpose is "so it can be rebuilt... without re-deriving the decisions from scratch") had no steps for installing `rsync`, generating/registering the personal SSH key, or anything from this session (zstd, Ollama). `docs/roadmap/BACKLOG.md`'s installation index pointed two rows at itself ("this file, row 9"/"row 21") instead of an actual how-to doc — a dead-end for anyone following the index. Item 7 (install rsync) was still listed as "open/deferred" despite `sync-to-lab.sh` having run plain `rsync` successfully for multiple sessions — genuinely resolved, just never marked as such. A stray blank line had also split item 20/21 out of the "Open/deferred" table into orphaned fragments below the Resolved table.
**Fixed:**
- `docs/setup/01-network-lab-environment.md` — added §9 (install rsync) and §10 (generate/register personal SSH key), renumbered the rest, and pointed §11 (deploy) at `lab-up.sh`/`lab-down.sh` as the everyday path with the raw `clab deploy`/`destroy` kept as the underlying mechanism.
- `docs/setup/07-diagnosis-assistant.md` — new file (matches the "component gets its own 0N- doc" convention this folder already used) capturing zstd + Ollama install/verify steps, explicitly marked in-progress since the model/placement/provider decisions for component #7 aren't made yet.
- `docs/roadmap/BACKLOG.md` — item 7 (rsync) moved to Resolved; items 20/21 rebuilt into the actual Open/deferred table instead of sitting as broken fragments; installation-index rows for the SSH key, rsync, zstd, and Ollama now point at the two setup docs above instead of back at BACKLOG.md itself.
**Next:** continue component #7 design (model benchmark, provider abstraction, PromQL strategy) — this was a documentation-integrity pass, not new build work.
**Open questions:** none blocking.

### 2026-09-11 (19) — Ollama installed and confirmed working (component #7 prep)
**Focus:** Get a local model runnable ahead of component #7's design decision (which model, local-only vs. also Groq/Gemini).
**Hit and fixed:** Ollama's install script requires `zstd` for extraction, not present in the `Containerlab` distro's base image — fixed with `sudo apt install -y zstd`.
**Verified:** `ollama pull llama3.2:3b` (2.0GB) and `ollama run llama3.2:3b "test prompt"` both succeeded, coherent response returned. Note for next time: the install script starts its own background `ollama serve` automatically — a separately, manually run `ollama serve &` will fail with "address already in use" against the same port, which is expected and not a real error; the already-running service is what actually serves requests.
**Not yet done:** latency/RAM benchmarking against the other 7 lab containers running simultaneously, and no comparison against an 8B-class model yet — tracked as `docs/roadmap/BACKLOG.md` item 21. Ollama is currently host-installed inside the `Containerlab` distro, not containerized/added to the topology — that placement decision (own topology node vs. host-level) still open, see conversation.
**Next:** benchmark 3B vs 8B on this machine, decide model + host-vs-container placement, then design the fixed-templates-vs-LLM-generated-PromQL question for the structured metrics side of component #7.
**Open questions:** none blocking.

### 2026-09-11 (18) — Lab lifecycle fix: single-command up/down, survives a laptop restart
**Focus:** After a laptop restart, `docker ps -a` showed the `linux`-kind containers (gnmic, Prometheus, Grafana, anomaly-detector, Chroma) back `Up`, but `srl1`/`srl2` stuck `Exited (143)` even after re-running `clab deploy` — and a single command to bring the whole lab up/down was requested rather than the multi-step sync+deploy dance every time.
**Investigated:** confirmed against containerlab's own node-configuration docs (containerlab.dev/manual/nodes/) that the topology schema has no `restart-policy` field — there's nothing to add to `netmind-2node.clab.yml` itself to fix this, and `clab deploy` doesn't reliably restart a container that already exists but is stopped, for every kind.
**Built:**
- `scripts/lab-up.sh` — one command: syncs the repo, `docker start`s any container already `Exited`, runs `clab deploy` to reconcile anything genuinely missing, then sets Docker's own `--restart unless-stopped` policy (a container-level setting, independent of containerlab) on every container in the lab so dockerd itself brings them back up whenever it starts.
- `scripts/lab-down.sh` — one command wrapping `clab destroy --cleanup`.
- `lab/README.md` — new "Starting and stopping the lab" section documenting both scripts and the known gotcha above.
**Not fully solved:** the Docker-level restart policy only helps once the Docker daemon (inside the `Containerlab` WSL2 distro) is actually running — nothing yet starts that distro automatically on a full Windows boot, so at least one `wsl -d Containerlab` + `lab-up.sh` is still needed after a laptop restart. Tracked as `docs/roadmap/BACKLOG.md` item 20.
**Hit and fixed:** first real run of `lab-up.sh` failed restarting `srl1`/`srl2` with a Docker "not a directory" mount error. Root cause: `sync-to-lab.sh`'s `rsync --delete` was wiping `lab/topologies/clab-netmind-2node/` — containerlab's own generated per-deploy state, native-only, never in git — on every sync, moments before `docker start` tried to reuse a bind mount pointing at the file just deleted. This was likely also the true cause of the original "SR Linux won't come back" observation, since the old manual workflow ran the same sync-then-deploy sequence. Fixed by excluding that directory from the sync in `sync-to-lab.sh`.
**Next:** re-run `lab-up.sh` with the fix and confirm `srl1`/`srl2` actually come back `Up`; then continue component #7 (diagnosis assistant) design.
**Open questions:** none blocking.

### 2026-09-10 (17) — Component #6 stage 1: closed out
**Focus:** Confirm the retrieval index actually retrieves — real docs, chunked and embedded into Chroma, returning relevant results for a real question.
**Verified — stage 1 exit criterion met:** After redeploying with the version-pinned Chroma image (`chromadb/chroma:0.5.23`, see entry 16's "Hit and fixed"), `ingest.py` completed successfully: `Ingested 141 chunks from 12 documents into collection 'netmind-docs'.` A follow-up `query.py "why was Kafka skipped for the metrics store?"` returned three genuinely relevant top matches — `docs/roadmap/BACKLOG.md` item 1 (the Kafka-deferral decision itself) and `metrics/README.md` (the direct-scrape design decision), at distances 0.95–1.05. This is real retrieval against real content, not just "the container started" — component #6 stage 1 is done.
**Updated:** `docs/architecture/component-diagram.md` and the published artifact (Chroma and `ingest.py`/`query.py` rows/pill moved from "built, not yet verified" to "verified"; diagram status note updated). `docs/roadmap/BACKLOG.md` item 19 added — the ONNX embedding model (~79MB) gets re-downloaded on every `docker run` since `ingest.py`/`query.py` run via `--rm` and the container filesystem (and its `/root/.cache/chroma` cache) dies with it each time; deferred until retrieval is called often enough for the repeated ~40s download to actually matter.
**Next:** Component #7 — diagnosis assistant: retrieval-grounded LLM, parallel vector search + structured Prometheus/log query assembled into a prompt, sent to a local model (Ollama), answered with citations. First real design discussion needed: which local model to run under Ollama, and how the structured Prometheus query side gets built (fixed PromQL templates vs. something more dynamic).
**Open questions:** none blocking.

### 2026-09-10 (16) — Component #6 kickoff: retrieval index
**Focus:** Design and build the first version of the retrieval index — the first intelligence-layer component that isn't a straightforward extension of the existing telemetry pipeline.
**Decided:**
- Corpus: **this project's own docs**, not invented runbooks — every README/design doc written so far. Real content that exists today, and doubles as a natural test corpus for component #7 (diagnosis assistant) later.
- Vector store: **Chroma, containerized**, same "own node in the topology" pattern as every prior component. No persistent volume yet — same deliberate simplification as Prometheus in component #3.
- Embeddings: **Chroma's built-in default function (ONNX MiniLM-L6-v2)**, not sentence-transformers + torch — same underlying model family, much lighter container, no external API/key.
- Ingestion/query: **on-demand scripts, not topology nodes.** Only Chroma itself needs to stay running continuously; chunking/embedding/querying are cheap and idempotent, run via `docker run` against the lab's network when needed. Automatic/scheduled re-ingest deliberately deferred (see `docs/roadmap/BACKLOG.md` item 17).
**Built:**
- `intelligence/retrieval-index/ingest.py` — chunks the docs listed in `DOC_GLOBS`, embeds them, upserts into Chroma's `netmind-docs` collection. Idempotent (deterministic chunk ids).
- `intelligence/retrieval-index/query.py` — the verification tool: embeds a question, runs a similarity search, prints top matches with source + distance so relevance can be judged by eye.
- `intelligence/retrieval-index/Dockerfile`, `requirements.txt`, `README.md` — the decisions above, build/run/verify instructions.
- `lab/topologies/netmind-2node.clab.yml` — added the `chroma` node (`chromadb/chroma:latest`, port 8000 published).
- `docs/architecture/component-diagram.md` and the published artifact — added Chroma and the ingest/query tooling, the first component pair with *no* Prometheus/Grafana involvement at all — a genuinely separate axis from every prior component.
- `docs/roadmap/BACKLOG.md` — items 16–18 (Chroma persistence, automatic re-ingestion, retrieval quality beyond one ad hoc query) plus installation-index rows for Chroma and the retrieval tooling.
**Not yet built:** none of this has been deploy-tested this session (written without shell access) — first use needs two local `docker build` steps (the `chroma` image is pulled, but `netmind-retrieval-tools` is project code) before `ingest.py` can run.
**Hit and fixed:** first `ingest.py` run failed on the very first `get_or_create_collection` call — `KeyError: '_type'` inside `CollectionConfigurationInternal.from_json` (plus an unrelated telemetry warning, harmless). Root cause: the topology pulled `chromadb/chroma:latest`, which resolved to a much newer server than the `chromadb==0.5.23` client pinned in `requirements.txt` — the collection-config JSON schema changed between versions, and the older client couldn't parse the newer server's response. Fixed by pinning the server image to `chromadb/chroma:0.5.23`, matching the client exactly, in `lab/topologies/netmind-2node.clab.yml`.
**Next:** Redeploy with the pinned image, re-run `ingest.py`, then `query.py` with a real question and check the results are actually relevant — that's the exit criterion for component #6 stage 1.
**Open questions:** none blocking.

### 2026-09-10 (15) — Component #5 stage 1: closed out
**Focus:** Confirm the anomaly detector is producing real z-scores against real telemetry.
**Verified — stage 1 exit criterion met:** User confirmed anomalies are visible on the Grafana "Anomaly detection" row after the local `docker build` + redeploy. Component #5 stage 1 is done: `detector.py` computing rolling z-scores from live Prometheus data, flowing through to `netmind_anomaly_*` metrics and rendering in the dashboard, exactly as designed in entry (14).
**Updated:** `docs/architecture/component-diagram.md` and the published artifact (anomaly-detector row/pill moved from "built, unverified" to "verified"; diagram status note updated).
**Next:** Component #6 — retrieval index. Per the roadmap: runbooks/past incidents chunked, embedded, and stored in a vector DB (Chroma or pgvector), running continuously in the background. First component that needs an embedding model and a vector store, neither of which exist in the stack yet.
**Open questions:** Component #5's threshold (default z-score 3.0) is still unvalidated against a real anomaly event (see `docs/roadmap/BACKLOG.md` item 13) — worth a deliberate test later (e.g. manually flapping a link) once there's time, but not blocking component #6.

### 2026-09-10 (14) — Component #5 kickoff: anomaly detection
**Focus:** Design and build the first version of anomaly detection — the first intelligence-layer component, opening phase 5.
**Decided:**
- Scope: **interface counters only** (traffic rate, errors, discards, link/carrier transitions) — the metrics already in the pipeline, no new telemetry. Admin/oper state flap detection deliberately saved for a stage 2 (see `docs/roadmap/BACKLOG.md` item 14).
- Algorithm: **rolling-baseline z-score, no ML/LLM.** `avg_over_time`/`stddev_over_time` PromQL subqueries compute the baseline; the service's own job is orchestration and turning the result into a metric, not reimplementing statistics Prometheus already provides. A real model comes later, once this baseline's actual limits are understood from real data — not chosen speculatively now.
- Deployment: **standalone containerized service, not a Prometheus recording rule.** A recording rule could do the same math in pure config, but this component is meant to *become* the real-model version later, and a recording rule has nowhere to host a trained model — a service does.
- Output: **writes back to Prometheus** as its own metrics (`netmind_anomaly_*` on `:9805`), scraped like every other component — zero new dashboard plumbing.
- Structure: new **`intelligence/`** top-level directory (not a bare `anomaly-detection/`), since components #6–8 are also intelligence-layer per the Component map — avoids a reshuffle later.
**Built:**
- `intelligence/anomaly-detection/detector.py` — queries Prometheus for current rate + rolling mean/stddev per watched counter, computes a z-score per interface, exposes `netmind_anomaly_score`/`_detected`/`_baseline_mean`/`_baseline_stddev` gauges on `:9805`.
- `intelligence/anomaly-detection/Dockerfile`, `requirements.txt` — no public image exists for this (it's project code); must be built locally before first deploy.
- `intelligence/anomaly-detection/README.md` — the decisions above, the full metric list, build/run/verify instructions.
- `lab/topologies/netmind-2node.clab.yml` — added the `anomaly-detector` node (`netmind-anomaly-detector:latest`, built locally, port 9805 published).
- `metrics/prometheus/prometheus.yml` — added a `netmind-anomaly-detector` scrape job.
- `grafana/dashboards/netmind-overview.json` — new "Anomaly detection" row: z-scores per interface/counter (timeseries with a threshold line at the default flag boundary) and a table of currently flagged anomalies.
- `docs/architecture/component-diagram.md` and the published artifact — added the anomaly-detector node with its bidirectional relationship to Prometheus (queries it for baseline, is scraped by it for its own score) — the first component in this diagram that isn't purely one-directional pull.
- `docs/roadmap/BACKLOG.md` — items 13–15 (unvalidated z-score threshold, admin/oper state detection deferred to stage 2, local image-tag pinning) plus an installation-index row flagging the required local `docker build` step.
**Not yet built:** none of this has been deploy-tested this session (written without shell access) — first deploy needs the `docker build` step run manually before `clab deploy`, since there's no registry to pull from.
**Next:** `docker build -t netmind-anomaly-detector:latest .` from `intelligence/anomaly-detection/`, then full redeploy and verify `netmind_anomaly_*` metrics appear in Prometheus and the new Grafana row — that's the exit criterion for component #5 stage 1.
**Open questions:** none blocking.

### 2026-09-10 (13) — Component #4 stage 1: closed out
**Focus:** Confirm the NetMind Overview dashboard actually renders against real Prometheus data after the full metric set was added.
**Verified — stage 1 exit criterion met:** User confirmed the dashboard is rendering at `http://localhost:3000`. Component #4 (dashboards) stage 1 is done: Grafana provisioned as code, all 22 confirmed `netmind_*` metrics covered across the Overview dashboard's five rows (pipeline health, admin/oper state, traffic, errors & transitions, packet types, additional counters).
**Updated:** `docs/architecture/component-diagram.md` and the published artifact (Grafana row/pill moved from "built, unverified" to "verified"; diagram status note updated).
**Next:** Component #5 — anomaly detection. Per the roadmap: a scheduled job, rolling baseline first, a real model (isolation forest or similar) only once the baseline's limits are understood. No LLM involved at this stage. This closes out phase 4 (telemetry: #1–#4) and opens phase 5 (the AI layer).
**Open questions:** none blocking.

### 2026-09-10 (12) — Component #4 kickoff: dashboards
**Focus:** Design and build the first version of the dashboard layer on top of the now-verified Prometheus.
**Decided:**
- Deployment: **containerized, in the topology** — same pattern as `gnmic`/`prometheus`, its own node (`grafana`) stood up/torn down with the rest of the lab.
- Dashboards: **provisioned as code**, not built by hand in the UI — datasource and dashboard JSON both committed to `grafana/` and auto-loaded via Grafana's provisioning system, matching how `gnmic.yaml`/`prometheus.yml` are already handled.
- Access: anonymous viewer enabled for local convenience (`http://localhost:3000`, no login), admin credentials still set for editing — explicitly flagged as a lab-only posture, not a production pattern (see `docs/roadmap/BACKLOG.md` item 12).
**Built:**
- `lab/topologies/netmind-2node.clab.yml` — added the `grafana` node (`grafana/grafana:latest`, port 3000 published, provisioning + dashboards bind-mounted).
- `grafana/provisioning/datasources/prometheus.yml` — auto-registers the `prometheus` container as Grafana's datasource.
- `grafana/provisioning/dashboards/dashboards.yml` — auto-loads any dashboard JSON from `grafana/dashboards/` into a "NetMind" folder.
- `grafana/README.md` — the decisions above, layout, running/verifying instructions.
- `docs/roadmap/BACKLOG.md` — item 6 (image-tag pinning) extended to cover `grafana/grafana`; new item 12 for the lab-only auth posture.
**Hit and fixed:** first redeploy attempt failed — `Failed to verify bind path: stat .../grafana/dashboards: no such file or directory`. `grafana/dashboards/` was empty (no dashboard JSON committed yet) and git doesn't track empty directories, so the bind-mounted folder never made it into the synced repo. Same class of bug as component #2's missing `/var/log/gnmic`; same fix — added a tracked `grafana/dashboards/.gitkeep`.
**Built (continued):** user confirmed real metric names from Prometheus's metric browser — `netmind_interface_state_srl_nokia_interfaces_interface_<leaf>` (subscription name `interface-state` + metric-prefix `netmind`, confirming the expected naming pattern). `grafana/dashboards/netmind-overview.json` written against the real names: a scrape-health stat panel (`up{job="netmind-gnmic"}`), admin/oper-state raw tables, octets/sec and packets/sec per interface, error/discard rates, and link/carrier transition counts — four rows total. Datasource provisioning (`grafana/provisioning/datasources/prometheus.yml`) given a fixed `uid: netmind-prometheus` so the dashboard JSON can reference it reliably. `docs/architecture/component-diagram.md` and the published artifact both updated: Grafana promoted from a "planned" ghost node to a real `dashboard`-classed node wired to Prometheus with a query-pull arrow, matching the gnmic→Prometheus pattern; Component status table and diagram status note updated to "built, not yet verified."
**Built (continued):** user shared the full `netmind_*` metric list from Prometheus's browser (22 series total) — confirmed 12 already covered by the dashboard and surfaced 8 more (`in`/`out_unicast_packets`, `in`/`out_multicast_packets`, `in`/`out_broadcast_packets`, `in_fcs_error_packets`, `statistics_interface_transitions`, `out_mirror_octets`, `out_mirror_packets`). Added two more dashboard rows — "Packet types" (unicast/multicast/broadcast breakdown, in and out) and "Additional counters" (FCS errors, interface transitions, mirrored traffic) — so `netmind-overview.json` now covers every leaf gnmic exposes, not just the original subset. Mirror octets/packets are expected to read zero since port mirroring isn't configured on either node — documented in the panel description so it doesn't read as a broken query.
**Next:** Full redeploy (`sync-to-lab.sh` + `clab destroy --cleanup` + `clab deploy`) and verify `http://localhost:3000` shows the NetMind Overview dashboard with live panels for both `srl1` and `srl2` — that's the exit criterion for component #4 stage 1. If a panel comes up empty, check the actual label names on the raw metric via Grafana Explore before editing the query — the dashboard assumes gnmic's standard `name`/`source` labels, not yet confirmed against a rendered panel.
**Open questions:** none blocking.

### 2026-09-10 (11) — Component #3 stage 1: closed out
**Focus:** Confirm Prometheus is actually scraping gnmic after the full redeploy.
**Verified — stage 1 exit criterion met:** User confirmed the redeploy worked as expected — `netmind-gnmic` shows `UP` under Prometheus Status → Targets, and `netmind_`-prefixed series return for both `srl1` and `srl2`. Component #3 (metrics store) stage 1 is done: direct scrape, no Kafka, default retention, all as designed in entry (9).
**Updated:** `docs/architecture/component-diagram.md`, the published artifact, and `docs/roadmap/BACKLOG.md` (item 10 moved to Resolved) to reflect Prometheus as fully verified rather than built-but-unverified.
**Next:** Component #4 — dashboards (Grafana on top of Prometheus). Lower design complexity than #1–#3; the point is making the pipeline visibly real, not new protocol learning.
**Open questions:** none blocking.

### 2026-09-10 (10) — Backlog captured, diagram updated for component #3
**Focus:** Durably record every deferred decision made so far (Kafka, retention, Kubernetes timing, image pinning, and more) so "we'll fix it later" doesn't quietly get lost between sessions, plus bring the diagram (both the Mermaid source and the published artifact) up to date with component #3's build.
**Built:**
- `docs/roadmap/BACKLOG.md` — new file, two sections: an **Open/deferred** table (11 items — Kafka buffer, Prometheus retention/downsampling, Prometheus persistent storage, Kubernetes/k3s+Cilium timing, growing the lab past 2 nodes, pinning image tags, installing `rsync`, the systemd user-session warning, the Containerlab distro's shared SSH key, unverified gnmic→Prometheus metric names, and components #4–11 as a single pointer back to this file's Component map) each with why it was deferred and what "done" looks like when it's picked up; an empty **Resolved** section with instructions to move rows there instead of deleting them; and an **Installation index** table mapping everything installed so far to the doc where its actual steps live, so rebuilding the environment never means re-reading every session log.
- `docs/architecture/component-diagram.md` — Prometheus moved from a "planned" ghost node to a real `metrics`-classed node in the Mermaid diagram, with its scrape-pull edge back to gnmic; the old "planned Prometheus" node replaced by "planned Grafana — component #4"; added a status note pointing at this entry and at `BACKLOG.md`; expanded the subscription-mechanism prose with a paragraph on the Prometheus pull direction; Component status table updated to match.
- Published artifact "NetMind Signal Flow" (https://claude.ai/code/artifact/675b4713-1dec-4fee-adbd-d834242e1c26) republished to match: new metrics-red color tokens (light/dark), a Prometheus box added to the SVG (positioned to clear the existing gNMI Subscribe arrows), its scrape arrow, the Grafana "planned" box moved to originate from Prometheus instead of the output file, legend entry for the scrape arrow, updated prose, and the Component status table's gnmic/Prometheus/Grafana rows updated to reflect built-but-unverified vs. verified vs. planned.
**Design intent:** `BACKLOG.md` is meant to be the single place that answers "what did we already think about and choose to skip" — the Component map in this file still owns "what's next," this new file owns "what we already looked at." Update both together going forward whenever a design discussion produces a deliberate simplification.
**Next:** The user still needs to actually redeploy and verify component #3 (full `sync-to-lab.sh` + `clab destroy --cleanup` + `clab deploy`, then check `http://localhost:9090` Status → Targets and query `netmind_`-prefixed metrics) — that's still open from entry (9), independent of this session's documentation work.
**Open questions:** none blocking.

### 2026-09-10 (9) — Component #3 kickoff: metrics store design
**Focus:** Design and build the first version of the metrics store.
**Decided:**
- Path from collector to store: **direct scrape, no Kafka buffer.** gnmic exposes a Prometheus scrape endpoint directly; Prometheus scrapes it. Matches how #1 and #2 were built — smallest thing that proves the pipeline first. Revisit Kafka only if a second consumer of the same stream shows up later.
- Retention: **Prometheus's 15-day default, not touched.** The roadmap flags retention/downsampling as a learning goal for this component, but deliberately not addressed yet — there isn't enough real accumulated data to make the trade-offs concrete. Comes back as its own explicit topic later.
- Deployment: **containerized**, same pattern as `gnmic` — its own node in the topology, no persistent data volume yet (would hit the same container-user-vs-host-owner permission class of bug gnmic's file output did, for no benefit at this stage).
**Built:**
- `telemetry/collectors/gnmic.yaml` — added a `telemetry-prometheus` output (port 9804, `metric-prefix: netmind`) alongside the existing file output. Same subscriptions feed both.
- `metrics/prometheus/prometheus.yml` — scrapes `clab-netmind-2node-gnmic:9804` every 10s (matches gnmic's sample interval).
- `metrics/README.md` — the decisions above plus how to verify (Prometheus UI at `http://localhost:9090`, Status → Targets, a sample PromQL query).
- `lab/topologies/netmind-2node.clab.yml` — added the `prometheus` node (`prom/prometheus:latest`, port 9090 published to Windows via WSL2's automatic forwarding); moved `gnmic`'s image to node-level since the `linux` kind now hosts two nodes needing different images.
**Not yet verified:** none of this has been deploy-tested this session (written without shell access) — first redeploy may need a small correction, same caveat as component #2's first attempt.
**Next:** Full redeploy (new bind mounts/ports need it, not an incremental add), then confirm the `netmind-gnmic` scrape target shows `UP` in Prometheus and a query returns series for both `srl1` and `srl2` — that's the exit criterion for component #3 stage 1.
**Open questions:** none blocking.

### 2026-09-10 (8) — Component diagram published
**Focus:** Visual diagram of how components #1 and #2 connect, which platform each runs on, and how the gNMI subscribe/publish exchange actually works.
**Built:**
- `docs/architecture/component-diagram.md` — git-tracked source of truth: a colored Mermaid diagram (nested boxes showing the Windows host → WSL2 → Ubuntu vs. Containerlab distro → docker network → srl1/srl2/gnmic hierarchy, plus the sync and subscribe/publish flows), the subscribe-mechanism explanation, and an extensible component-status table.
- Published artifact "NetMind Signal Flow" (hand-authored SVG diagram, same content, styled for readability — nested platform boxes, color-coded arrows for data-plane link / gNMI protocol / collector file-write / repo sync / planned-future, legend, prose explanation, status table): https://claude.ai/code/artifact/675b4713-1dec-4fee-adbd-d834242e1c26
**Design intent:** both are meant to grow together as components #3–11 land — the Mermaid file is what actually gets edited each session, the artifact gets republished to match. Neither should drift from `PROGRESS_LOG.md`.
**Next:** keep extending both when component #3 (metrics store) design starts.
**Open questions:** none blocking.

### 2026-09-10 (7) — Component #2 stage 1: closed out
**Focus:** Confirm the file-output fix (bind-mounting `telemetry/output/` onto `/var/log/gnmic`) actually resolved the streaming issue.
**Verified — stage 1 exit criterion met:** Full redeploy succeeded, `tail -f ~/netmind-lab/telemetry/output/netmind-telemetry.jsonl` shows live interface-state events for both nodes arriving continuously. Data is correct: `ethernet-1/1` (the actual link between `srl1` and `srl2`) shows `admin-state: enable` / `oper-state: up` on both sides; all other interfaces (`1/2`–`1/8`) correctly show `disable`/`down`. Component #2 stage 1 — a reliable, containerized gNMI stream off the lab — is done.
**Next:** Component #3 (metrics store — Prometheus, learning PromQL/retention rather than just wiring it up) is next in build order. Needs a design discussion: Prometheus deployment (containerized in the topology, same pattern as gnmic?), and how gnmic's output gets from file to Prometheus — add a `prometheus` output type to the existing subscription config (gnmic can expose a scrape endpoint directly), or route through Kafka as the roadmap's "+ Kafka buffer" note suggests. Not yet decided.
**Open questions:** none blocking.

### 2026-09-10 (6) — Component #2: first successful deploy, fixed the file-output bug
**Focus:** Get the `gnmic` collector actually deployed and streaming, debug why it wasn't.
**Hit and fixed:**
- `scripts/sync-to-lab.sh` assumed `rsync` was present; the `Containerlab` distro doesn't ship it, which made the script abort, which in turn left `~/netmind-lab/lab/topologies` missing and caused a confusing downstream error ("Failed to fetch http(s) resource: https://netmind-2node.clab.yml" — containerlab's fallback when it can't resolve a relative topology path locally). Fixed: script now falls back to `cp` when `rsync` isn't installed.
- With that fixed, `gnmic` deployed cleanly (`clab deploy` incrementally added just the new node — didn't disturb `srl1`/`srl2`), process confirmed running with correct args, config file confirmed correctly bind-mounted. But no output file ever appeared. Root cause, found via `gnmic ... --debug`: `err="open /var/log/gnmic/netmind-telemetry.jsonl: no such file or directory"` — gnmic's file output doesn't create a missing parent directory, and `/var/log/gnmic/` doesn't exist in the image. At default log level this fails completely silently (`docker logs` showed nothing at all), which is worth remembering for the next collector-type component.
- Fix: bind-mount `telemetry/output/` (new folder, gitignored contents, `.gitkeep` tracked) onto `/var/log/gnmic` in the topology — Docker creates the mount point automatically, and it has the side benefit of making the output readable directly from the WSL shell (`tail ~/netmind-lab/telemetry/output/netmind-telemetry.jsonl`) without `docker exec`.
**Also resolved this session:** the `Containerlab` distro's baked-in SSH key (`id_ecdsa`, shared across everyone who downloads the distro image) was being used for GitHub push instead of a personal key, causing "no push permission" errors — fixed by generating a distro-local `id_ed25519` key and registering it on the `pacificpatel165` GitHub account.
**Next:** Redeploy with the fixed bind mount and confirm `output/netmind-telemetry.jsonl` actually fills with interface state/counter events every ~10s — that's the real exit criterion for component #2 stage 1 (still not yet met as of this entry).
**Open questions:** none blocking.

### 2026-09-10 (5) — Component #2 kickoff: telemetry collector design
**Focus:** Design and build the first version of the telemetry collector.
**Decided:**
- Collector engine: **`gnmic`**, config-driven — subscription YAML, not a hand-written gNMI client. Keeps the work at the architecture/design level (which paths, which targets, sampling) rather than re-implementing gRPC/protobuf handling, matching the "architecture over coding depth" positioning.
- Deployment: **containerized**, added as its own node (`gnmic`) in `lab/topologies/netmind-2node.clab.yml`, on the shared `netmind-mgmt` network — stood up/torn down with the rest of the lab, and the pattern the metrics store, dashboards, and eventually Kubernetes will all reuse.
**Built:**
- `telemetry/collectors/gnmic.yaml` — subscribes to interface oper/admin-state and statistics on both `srl1` and `srl2`, sampled every 10s, written to a file output for stage-1 validation. Prometheus output deliberately deferred to component #3.
- `telemetry/README.md` — the decisions above plus how to verify the stream.
- `lab/topologies/netmind-2node.clab.yml` — added the `gnmic` node (kind `linux`, `ghcr.io/openconfig/gnmic:latest`, bind-mounts the subscription config, mgmt IP `172.100.100.20`).
- `scripts/sync-to-lab.sh` — replaces manual single-file copying with a full repo sync (`rsync`, excludes `.git`) to `~/netmind-lab/` before every deploy, since the topology now bind-mounts a second file that has to move with it. Referenced from `lab/README.md` and `docs/setup/01-network-lab-environment.md` (both updated).
**Not yet verified:** the gnmic container image tag and exact `cmd`/bind-mount syntax haven't been deploy-tested yet (written without shell access this session) — first deploy may need a small correction. Also resolved separately this session: the `Containerlab` distro's baked-in SSH key (`id_ecdsa`, shared across everyone who downloads the distro image) was being used for GitHub push instead of a personal key, causing "no push permission" errors — fixed by generating a distro-local `id_ed25519` key and registering it on the `pacificpatel165` GitHub account.
**Next:** Run `sync-to-lab.sh`, redeploy, and verify telemetry is actually flowing (`docker logs -f clab-netmind-2node-gnmic` or tail the output file) — that's the exit criterion for component #2 stage 1.
**Open questions:** none blocking.

### 2026-09-10 (4) — Setup documentation + Kubernetes timing
**Focus:** Document the full containerlab environment install/config as a reproducible step-by-step guide, and decide when Kubernetes enters the picture.
**Built:** `docs/setup/01-network-lab-environment.md` — everything from the Docker Desktop/Ubuntu conflict through distro install, Docker CE + containerlab setup, the DrvFs deploy gotcha and fix, `gnmic` install, and lab verification. Numbered to match the component map so later components get their own `0N-<component>.md` in the same folder.
**Decided:** Kubernetes stays out of scope until after the telemetry pipeline (components 2–4) is built against the 2-node lab as-is. When it's time: k3s installed natively inside the `Containerlab` distro (not Docker Desktop's Kubernetes toggle, which would hit the same kernel-namespace isolation problem the containerlab setup itself had to work around), then Cilium as CNI, wired to the lab's reserved `e1-2` interfaces.
**Next:** Start component #2 (telemetry collector) against the existing 2-node lab.
**Open questions:** none blocking.

### 2026-09-10 (3) — Component #1 stage 1: closed out
**Focus:** Get the 2-node SR Linux topology actually deployed and confirm it's a live gNMI target.
**Hit and fixed:** First `clab deploy` failed post-deploy commit on both nodes (`Setting permissions for file '/etc/opt/srlinux/config.tmp' failed ... [Operation not permitted]`). Root cause: the lab directory was created under `/mnt/c/...` (WSL2's DrvFs view of the Windows drive), which doesn't support the POSIX permission bits SR Linux needs to chmod its own config files during commit. Fix: keep `netmind-2node.clab.yml` as the source of truth in git (on the Windows drive, so other tooling can reach it), but always copy it to a native Linux path (`~/netmind-lab/topologies/`) inside the `Containerlab` distro before running `clab deploy`. Documented in both the topology file's header comment and `lab/README.md`. Also swapped the SR Linux node type from the deprecated `ixrd2` to the current `ixr-d2` (containerlab warned the old name is removed after Jan 2026).
**Verified — stage 1 exit criterion met:** `clab deploy` from `~/netmind-lab/topologies/` succeeded cleanly, both `srl1`/`srl2` show `running`. `gnmic -a clab-netmind-2node-srl1 -u admin -p 'NokiaSrl1!' --skip-verify capabilities` returned a full model list (`srl_nokia-*`, OpenConfig, IETF NETCONF monitoring), gNMI version 0.10.0, JSON_IETF/PROTO/ASCII encodings — `srl1` is a live, queryable gNMI target.
**Next:** Component #1 stage 1 (network lab exists, reachable over gNMI) is done. Two directions from here: (a) start component #2 (telemetry collector) against this 2-node lab now, or (b) grow the lab toward the leaf-spine / K8s-underlay design before building the collector. Not yet decided — pick this at the start of the next session.
**Open questions:** none blocking.

### 2026-09-10 (2) — Component #1: environment + first topology
**Focus:** Stand up the containerlab environment for component #1 and write the first real topology file.
**Decided:**
- Containerlab runs in its own dedicated WSL2 distro (`srl-labs/wsl-containerlab`, native Docker CE + containerlab), kept fully separate from the existing Docker Desktop + Ubuntu setup used by other personal projects, to avoid the kernel-namespace conflict between Docker Desktop's WSL integration and containerlab's direct netns/veth manipulation. Docker Desktop's WSL integration is explicitly OFF for the `Containerlab` distro.
- Lab-to-K8s relationship: **integrated/nested** — the lab is designed to eventually sit underneath the phase-2 Kubernetes/Cilium cluster (Cilium using it as an underlay), not as an unrelated sibling environment. Each SR Linux node's topology reserves a second interface (`e1-2`) for that future attachment, left undeclared for now.
- Initial topology size: **2 nodes** (`srl1`, `srl2`, one link) — smallest topology that can prove the containerlab → gNMI pipeline, before growing to a leaf-spine layout.
**Built:** `lab/topologies/netmind-2node.clab.yml` (2× Nokia SR Linix `ixrd2`, one data-plane link, dedicated mgmt subnet), `lab/README.md` (environment + layout + the decisions above).
**Verified:** Containerlab WSL distro installed and isolated correctly (Docker Desktop WSL Integration panel confirms `Containerlab` OFF / `Ubuntu` ON); `docker version` → Docker CE 27.5.1 (native engine, not Desktop's proxy); `clab version` → 0.79.0.
**Open questions:** none blocking. A `wsl: Failed to start the systemd user session for 'clab'` warning appeared on first boot of the distro; didn't block `docker version`/`clab version`, treated as benign for now — revisit only if something systemd-dependent misbehaves later.

### 2026-09-10 — Component breakdown & planning
**Focus:** Decompose NetMind into top-level components before starting design/implementation session by session.
**Decided:** The 11-component map above, plus the build order. Sessions from here go component by component rather than jumping around.
**Next:** Pick a starting component — candidates discussed: #1 (network lab, first in build order) or #9 (security gate, the differentiator with the most open design decisions, doesn't strictly require #1–#8 built first to design on paper).
**Open questions:** none yet — this session was planning-only, no design decisions made on any individual component.
