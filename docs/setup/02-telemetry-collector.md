# Component #2 setup: telemetry collector (`gnmic`)

Step-by-step "how" for standing this component up, per this folder's
convention (`01-network-lab-environment.md`). For the *why* behind the
choices below — `gnmic` over a hand-written client, direct file output,
the deliberate no-Kafka scope — see `telemetry/README.md` and
`PROGRESS_LOG.md` entries dated 2026-09-10.

Prerequisite: component #1's lab is installed and `gnmic` itself is
already installed inside the `Containerlab` distro (see
`01-network-lab-environment.md` §8) — this file assumes both.

---

## 1. Nothing extra to install

`gnmic` runs as a container declared in
`lab/topologies/netmind-2node.clab.yml`, not a separate host install —
the CLI installed in §1's prerequisite is only used for the ad hoc
`capabilities` check, not for running this component.

## 2. Deploy

```bash
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/lab/topologies
sudo clab deploy -t netmind-2node.clab.yml
```

(Or the `lab-up.sh` wrapper — see `01-network-lab-environment.md` §11.)

## 3. Known gotcha: missing output directory

`gnmic`'s file output does not create a missing parent directory —
without `telemetry/output/` existing and bind-mounted onto
`/var/log/gnmic` inside the container, every write silently fails (only
visible with `gnmic ... --debug`; the default log level shows nothing).
The bind mount is already in the topology file; this is here so a
silent-no-output symptom is recognized immediately rather than
re-debugged from scratch.

## 4. Verify it's actually streaming

```bash
tail -f ~/netmind-lab/telemetry/output/netmind-telemetry.jsonl
```

Interface state/counter events for both `srl1` and `srl2` should arrive
roughly every 10 seconds. That's the exit criterion — a reliable,
containerized stream of real telemetry off the lab, not just "the
container started."

Full design detail, the Prometheus-scrape side of the same pipeline,
and the subscription config location: `telemetry/README.md`.
