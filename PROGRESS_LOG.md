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
