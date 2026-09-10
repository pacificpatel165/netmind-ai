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

To work in the lab, **always deploy from a native Linux path, not `/mnt/c/...`**: WSL2's DrvFs (the Windows-drive mount) doesn't support the POSIX permission bits SR Linux needs to chmod its own config files during commit, which breaks postdeploy with an "Operation not permitted" error. The topology file lives in git on the Windows drive (so other tooling can reach it), but gets copied to `~/netmind-lab/` before deploying:

```
wsl -d Containerlab
mkdir -p ~/netmind-lab/topologies
cp /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/lab/topologies/netmind-2node.clab.yml ~/netmind-lab/topologies/
cd ~/netmind-lab/topologies
sudo clab deploy -t netmind-2node.clab.yml
```

## Design decisions (see PROGRESS_LOG.md for the session this was decided in)

- The lab is designed to eventually sit *underneath* the phase-2
  Kubernetes/Cilium cluster (Cilium using it as an underlay), not as an
  unrelated sibling environment. Each SR Linux node reserves a second
  interface (`e1-2`) for that future attachment.
- Starting topology is 2 SR Linux nodes with one link — enough to prove
  the containerlab → gNMI → Prometheus pipeline before growing to a
  leaf-spine topology.
