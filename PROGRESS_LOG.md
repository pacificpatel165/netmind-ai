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
