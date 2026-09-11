# lab/

Component #1 — the network lab. Containerlab topology files that stand up
the simulated network NetMind observes and configures.

## Layout

- `topologies/` — `.clab.yml` topology definitions, one file per stage.
  Start with `netmind-2node.clab.yml`; later stages (leaf-spine, K8s
  attachment) get their own files here rather than overwriting this one,
  so earlier stages stay reproducible.

## Environment

The lab runs in a dedicated WSL2 distro (`Containerlab`, from
`srl-labs/wsl-containerlab`) with a native Docker CE + containerlab
install — deliberately kept separate from the Docker Desktop + Ubuntu
setup used by the other personal projects on this machine, to avoid the
kernel-namespace conflicts between Docker Desktop's WSL integration and
containerlab's direct netns/veth manipulation. Docker Desktop's WSL
integration is left OFF for the `Containerlab` distro.

To work in the lab, **always deploy from a native Linux path, not `/mnt/c/...`**: WSL2's DrvFs (the Windows-drive mount) doesn't support the POSIX permission bits SR Linux needs to chmod its own config files during commit, which breaks postdeploy with an "Operation not permitted" error. The repo lives in git on the Windows drive (so other tooling can reach it), but gets synced to `~/netmind-lab/` before deploying — use `scripts/sync-to-lab.sh` rather than copying files by hand, since the topology now bind-mounts `telemetry/collectors/gnmic.yaml` and needs it alongside it on native fs:

```
wsl -d Containerlab
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh
cd ~/netmind-lab/lab/topologies
sudo clab deploy -t netmind-2node.clab.yml
```

For everyday use, `scripts/lab-up.sh` and `scripts/lab-down.sh` wrap
this into a single command each — see "Starting and stopping the lab"
below.

## Starting and stopping the lab

```
wsl -d Containerlab
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/lab-up.sh
```

and to tear it down:

```
bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/lab-down.sh
```

**Known gotcha — SR Linux nodes not coming back after a laptop
restart.** After a Windows/WSL2 restart, `docker ps -a` can show the
`linux`-kind containers (`gnmic`, `prometheus`, `grafana`,
`anomaly-detector`, `chroma`) back `Up`, while `srl1`/`srl2` stay
`Exited (143)` even after re-running `clab deploy` — containerlab's
topology schema has no `restart-policy` field (there is nothing to set
in the `.clab.yml` itself; checked against
[containerlab.dev/manual/nodes/](https://containerlab.dev/manual/nodes/)),
and `clab deploy` does not reliably restart a container that already
exists but is stopped, for every kind. `lab-up.sh` works around this
directly: it `docker start`s anything already `Exited` before running
`clab deploy` to reconcile whatever's still genuinely missing, then
sets Docker's own `--restart unless-stopped` policy on every container
in the lab (a container-level setting, independent of containerlab) so
the Docker daemon itself brings them back up the next time it starts.
That still depends on the `Containerlab` WSL2 distro actually being
running when Windows boots, which nothing here automates yet — see
`docs/roadmap/BACKLOG.md`.

**Second gotcha, found while fixing the first one:** the first version
of `lab-up.sh` still failed on `srl1`/`srl2` with a Docker "not a
directory" mount error. Cause: `sync-to-lab.sh`'s `rsync --delete`
was wiping `lab/topologies/clab-netmind-2node/` — containerlab's own
generated per-deploy state (each node's `topology.yml`/config),
created natively and never committed to git — on every sync, right
before `docker start` tried to reuse a bind mount pointing at a file
that had just been deleted. Fixed by excluding that directory from
the sync. This was likely also the real cause of the *original*
"SR Linux won't come back" problem, since the old manual workflow ran
the same sync-then-deploy sequence.

## Design decisions (see PROGRESS_LOG.md for the session this was decided in)

- The lab is designed to eventually sit *underneath* the phase-2
  Kubernetes/Cilium cluster (Cilium using it as an underlay), not as an
  unrelated sibling environment. Each SR Linux node reserves a second
  interface (`e1-2`) for that future attachment.
- Starting topology is 2 SR Linux nodes with one link — enough to prove
  the containerlab → gNMI → Prometheus pipeline before growing to a
  leaf-spine topology.
