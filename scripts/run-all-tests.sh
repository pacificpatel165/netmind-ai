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
# ncclient/lxml bug found 2026-09-16), and the diagnosis assistant's
# deterministic PromQL template routing.
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
# Each component needs its own venv with its requirements.txt installed
# first (pytest is now listed in every component's requirements.txt
# that has tests) -- this script does NOT create venvs for you, since
# that's a real, occasionally slow step (chromadb especially) better
# run deliberately once per environment, not silently on every test run.

set -uo pipefail

REPO_ROOT="$HOME/netmind-lab"
FAILED=0
RAN_ANY=0

if [ ! -d "$REPO_ROOT" ]; then
  echo "ERROR: $REPO_ROOT doesn't exist -- run scripts/sync-to-lab.sh first (see its header comment for why venvs only exist here, not on the Windows-mounted copy)."
  exit 1
fi

run_component_tests() {
  local name="$1"
  local dir="$REPO_ROOT/intelligence/$name"
  local venv="$dir/.venv"

  echo "== $name =="
  if [ ! -d "$venv" ]; then
    echo "SKIP -- no .venv at $venv (run: cd intelligence/$name && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt)"
    echo
    return
  fi
  RAN_ANY=1
  # shellcheck disable=SC1091
  source "$venv/bin/activate"
  ( cd "$dir" && python -m pytest test_*.py -v )
  local status=$?
  deactivate
  if [ $status -ne 0 ]; then
    FAILED=1
  fi
  echo
}

run_component_tests "diagnosis-assistant"
run_component_tests "remediation-proposal"
run_component_tests "security-gate"
run_component_tests "config-push-executor"

echo "=================================================="
if [ "$RAN_ANY" -eq 0 ]; then
  echo "NOTHING RAN -- every component was skipped (no .venv found). This is NOT a pass; set up at least one venv above and re-run."
  exit 1
elif [ $FAILED -eq 0 ]; then
  echo "All automated tests passed."
else
  echo "One or more component test suites FAILED -- see output above."
fi
exit $FAILED
