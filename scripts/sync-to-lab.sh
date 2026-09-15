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
# --exclude on clab-netmind-2node/ matters as much as --delete itself:
# that directory is containerlab's own generated per-deploy state
# (each node's topology.yml/config), created natively and never
# committed to git. Without this exclude, --delete wipes it on every
# sync -- harmless right before a full `clab destroy && clab deploy`
# (which regenerates it from scratch anyway), but it breaks a plain
# `docker start` on an already-created, merely-stopped container: the
# container's bind mount still points at the now-deleted file, and
# Docker fails with a "not a directory" mount error. See lab-up.sh and
# lab/README.md's "known gotcha" section.
# --exclude on intelligence/diagnosis-assistant/.venv/,
# intelligence/remediation-proposal/.venv/, and
# intelligence/security-gate/.venv/ is the same class of fix as
# clab-netmind-2node/ above: a Python virtual environment created
# natively (see docs/setup/07-diagnosis-assistant.md §6) exists only on
# native fs, never in the Windows-drive repo -- without this exclude,
# every sync would delete it and force a full `pip install` on the
# next run.
# --exclude on intelligence/security-gate/audit_log.jsonl is the same
# issue again, but for data instead of a venv: gate.py creates it
# natively the first time someone approves/rejects a proposal, it
# isn't (yet) part of the Windows-drive repo, and a --delete sync
# would silently wipe a real audit trail rather than just cost a
# rebuild -- see that component's README.md for why whether this file
# should even be committed to git is still an open question.
rsync -a --delete --exclude='.git' --exclude='lab/topologies/clab-netmind-2node/' --exclude='intelligence/diagnosis-assistant/.venv/' --exclude='intelligence/remediation-proposal/.venv/' --exclude='intelligence/security-gate/.venv/' --exclude='intelligence/security-gate/audit_log.jsonl' "$REPO_WIN/" "$REPO_NATIVE/"

echo "Synced $REPO_WIN -> $REPO_NATIVE"
echo "Deploy from: $REPO_NATIVE/lab/topologies/"
