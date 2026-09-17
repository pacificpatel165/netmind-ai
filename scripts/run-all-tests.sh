#!/usr/bin/env bash
# NetMind AI — run every component's automated test suite in one shot
# (BACKLOG.md item 30, added 2026-09-17).
#
# These are NOT a replacement for docs/testing/TESTING.md's live-device
# verification steps -- they deliberately don't need the lab up at all.
# They cover the parts of each component that are pure/mockable logic:
# payload shapes pinned against what was proven live by hand, the
# security gate's hashing/audit/default-deny logic, the config-push
# executor's RPC-body parsing (a direct regression test for the real
# ncclient/lxml bug found 2026-09-16), the diagnosis assistant's
# deterministic PromQL template routing, the anomaly detector's z-score
# math and interface_name label handling, and the retrieval index's
# chunking logic and ingest/query flow against a mocked Chroma client
# (components #5/#6, added 2026-09-17 closing BACKLOG.md item 30b --
# despite being containerized in deployment, both components' testable
# logic runs fine in a plain host venv, same as #7-#10, so no different
# pattern was actually needed).
#
# Always runs against the NATIVE lab path (~/netmind-lab), never
# wherever this script happens to be invoked from -- fixed 2026-09-17
# after a real run showed why: every component's .venv only exists
# natively (same reason sync-to-lab.sh exists at all, see that
# script's own header comment), so invoking this from the
# Windows-mounted path found zero venvs and skipped every single
# component -- while still printing "All automated tests passed",
# which was a false positive covered up by treating "skipped" and
# "passed" as the same outcome. Both bugs fixed below: the path is now
# hardcoded to the native lab location like sync-to-lab.sh's
# REPO_NATIVE, and an all-skipped run now exits non-zero with an
# explicit warning instead of silently reporting success.
#
# Run from anywhere -- always resolves to ~/netmind-lab regardless of
# the caller's cwd or which copy of the repo invoked it:
#   bash scripts/run-all-tests.sh
#
# Since 2026-09-17 (item 32), every component shares ONE venv --
# intelligence/.venv -- instead of six separate per-component ones.
# That consolidation is why this script no longer skips components: a
# single missing venv is a hard error now, not a per-component skip,
# because "missing" can no longer mean "just hasn't been set up for
# THIS component yet" (item 33's original failure mode) -- there's only
# one venv to have or not have. Create it once:
#   cd intelligence && python3 -m venv .venv && source .venv/bin/activate \
#     && pip install -r requirements.txt && deactivate
#
# Auto-syncs from the Windows-mounted repo before running, same pattern
# lab-up.sh already used for deploys (2026-09-17, item 34's evaluation).
# Item 34 considered making ~/netmind-lab the actual git working copy
# instead of a sync target, to remove the "forgot to sync, ran stale
# code" bug class at the root (entry 43 hit it once for `clab deploy`;
# this script had the identical exposure for test runs, just never bit
# anyone yet). Declined: it would sever this session's own Claude<->repo
# collaboration path (SendUserFile/device_commit_files only reach
# C:\... paths -- a live check confirmed \\wsl$\Containerlab\... UNC
# paths are refused outright), which is a real, larger cost than the
# sync-discipline bug it would fix. Auto-syncing here instead closes
# the actual gap without that trade -- same fix shape as lab-up.sh,
# applied to the other ad hoc native-execution entry point.

set -uo pipefail

REPO_WIN="/mnt/c/MyWorkSpace/AI-Projects/NetMind-AI"
REPO_ROOT="$HOME/netmind-lab"
SHARED_VENV="$REPO_ROOT/intelligence/.venv"
FAILED=0

if [ -d "$REPO_WIN" ]; then
  echo "== Syncing repo to native filesystem =="
  bash "$REPO_WIN/scripts/sync-to-lab.sh"
  echo
fi

if [ ! -d "$REPO_ROOT" ]; then
  echo "ERROR: $REPO_ROOT doesn't exist -- run scripts/sync-to-lab.sh first (see its header comment for why venvs only exist here, not on the Windows-mounted copy)."
  exit 1
fi

if [ ! -d "$SHARED_VENV" ]; then
  echo "ERROR: shared venv missing at $SHARED_VENV -- run:"
  echo "  cd intelligence && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && deactivate"
  exit 1
fi

# shellcheck disable=SC1091
source "$SHARED_VENV/bin/activate"

run_component_tests() {
  local name="$1"
  local dir="$REPO_ROOT/intelligence/$name"

  echo "== $name =="
  ( cd "$dir" && python -m pytest test_*.py -v )
  local status=$?
  if [ $status -ne 0 ]; then
    FAILED=1
  fi
  echo
}

run_component_tests "diagnosis-assistant"
run_component_tests "remediation-proposal"
run_component_tests "security-gate"
run_component_tests "config-push-executor"
run_component_tests "anomaly-detection"
run_component_tests "retrieval-index"

deactivate

echo "=================================================="
if [ $FAILED -eq 0 ]; then
  echo "All automated tests passed."
else
  echo "One or more component test suites FAILED -- see output above."
fi
exit $FAILED
