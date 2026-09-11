#!/usr/bin/env bash
# NetMind AI — single-command lab teardown.
# Thin wrapper so "up" and "down" are symmetric single commands; the
# actual work is still containerlab's own destroy, not a replacement
# for it.
#
# Run from inside the Containerlab distro:
#   bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/lab-down.sh

set -euo pipefail

REPO_NATIVE="$HOME/netmind-lab"
TOPO="netmind-2node.clab.yml"

cd "$REPO_NATIVE/lab/topologies"
sudo clab destroy -t "$TOPO" --cleanup

echo "== Lab destroyed =="
