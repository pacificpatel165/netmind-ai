#!/usr/bin/env bash
# NetMind AI — single-command lab startup.
#
# Handles two different situations with one command:
#   1. First deploy of a session (no clab-netmind-2node-* containers
#      exist yet) -> straight `clab deploy`.
#   2. Laptop/WSL2 was rebooted and some containers exist but are
#      Exited -> `docker start` them directly first, since a plain
#      `clab deploy` does not reliably restart already-created but
#      stopped containers (observed 2026-09-11: after a laptop
#      restart, `docker ps -a` showed prometheus/gnmic/chroma/
#      anomaly-detector/grafana back "Up" but srl1/srl2 stayed
#      "Exited (143)" even after re-running `clab deploy`).
#
# Run from inside the Containerlab distro:
#   bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/lab-up.sh

set -euo pipefail

REPO_WIN="/mnt/c/MyWorkSpace/AI-Projects/NetMind-AI"
REPO_NATIVE="$HOME/netmind-lab"
TOPO="netmind-2node.clab.yml"
PREFIX="clab-netmind-2node-"

echo "== Syncing repo to native filesystem =="
bash "$REPO_WIN/scripts/sync-to-lab.sh"

cd "$REPO_NATIVE/lab/topologies"

# Step 1: restart any container that already exists but is stopped.
# `docker ps -a --filter status=exited` only lists this topology's
# containers because of the name prefix filter.
EXITED=$(docker ps -a --filter "name=${PREFIX}" --filter "status=exited" --format '{{.Names}}' || true)
if [ -n "$EXITED" ]; then
  echo "== Restarting stopped containers: $EXITED =="
  # shellcheck disable=SC2086
  docker start $EXITED
else
  echo "== No stopped containers to restart =="
fi

# Step 2: reconcile everything else (creates any container that's
# genuinely missing, e.g. after a real `clab destroy`, no-ops on
# anything already running).
echo "== Running clab deploy to reconcile the rest =="
sudo clab deploy -t "$TOPO"

# Step 3: set Docker's own restart policy on every container in this
# lab. Containerlab's topology schema has no restart-policy field
# (checked against containerlab.dev/manual/nodes/, 2026-09-11), but
# `docker update --restart` sets it directly on the container object,
# independent of containerlab. This makes dockerd itself bring every
# container back up whenever the Docker daemon starts — which still
# means the Containerlab WSL2 distro has to actually be running for
# that to happen; it does not by itself survive a full Windows reboot.
# See docs/roadmap/BACKLOG.md for that follow-on item.
ALL=$(docker ps -a --filter "name=${PREFIX}" --format '{{.Names}}')
if [ -n "$ALL" ]; then
  echo "== Setting restart policy (unless-stopped) on: $ALL =="
  # shellcheck disable=SC2086
  docker update --restart unless-stopped $ALL >/dev/null
fi

echo "== Status =="
docker ps -a --filter "name=${PREFIX}" --format 'table {{.Names}}\t{{.Status}}'

echo
echo "If srl1/srl2 still show Exited above, check why they're actually"
echo "crashing rather than just being stopped:"
echo "  docker start ${PREFIX}srl1 && docker logs -f ${PREFIX}srl1"
