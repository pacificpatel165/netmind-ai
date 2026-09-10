#!/usr/bin/env bash
# Sync the repo from the Windows-mounted path into a native-Linux path
# inside the Containerlab WSL distro, so `clab deploy` (and any bind
# mounts topology files reference, like the gnmic config) run entirely
# on native filesystem. Required because WSL2's DrvFs (/mnt/c/...)
# doesn't support the POSIX permission bits SR Linux needs during
# commit — see docs/setup/01-network-lab-environment.md section 7.
#
# Run from inside the Containerlab distro:
#   bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/scripts/sync-to-lab.sh

set -euo pipefail

REPO_WIN="/mnt/c/MyWorkSpace/AI-Projects/NetMind-AI"
REPO_NATIVE="$HOME/netmind-lab"

mkdir -p "$REPO_NATIVE"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude='.git' "$REPO_WIN/" "$REPO_NATIVE/"
else
  # rsync isn't in the base wsl-containerlab image. Fall back to cp so
  # this script works with no extra install. Downside: files deleted
  # from the repo won't be removed from the native copy automatically —
  # `rm -rf ~/netmind-lab` occasionally if that drifts.
  echo "rsync not found — falling back to cp (won't prune files removed from the repo)."
  cp -r "$REPO_WIN"/. "$REPO_NATIVE"/
  rm -rf "$REPO_NATIVE/.git"
fi

echo "Synced $REPO_WIN -> $REPO_NATIVE"
echo "Deploy from: $REPO_NATIVE/lab/topologies/"
