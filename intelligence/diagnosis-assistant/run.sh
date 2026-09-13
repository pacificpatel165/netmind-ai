#!/usr/bin/env bash
# NetMind AI — component #7, single-command entry point.
#
# Collapses "cd to the right directory, activate the right venv, run
# the right script" into one command, run from anywhere:
#   bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/intelligence/diagnosis-assistant/run.sh "<question>"
#
# Added after a real mix-up (2026-09-13): running assistant.py from
# the wrong directory (retrieval-index/ instead of
# diagnosis-assistant/) after an unrelated ingest step, because the
# dual-path setup (edit on the Windows repo, run from a synced
# native-fs copy) makes it easy to lose track of which directory a
# shell is actually in. Same fix shape as lab-up.sh/lab-down.sh for
# the same underlying complexity.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d .venv ]; then
  echo "== No .venv found -- creating one (first run) =="
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -r requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [ "$#" -eq 0 ]; then
  echo 'usage: bash run.sh "<question>"'
  exit 1
fi

python assistant.py "$@"
