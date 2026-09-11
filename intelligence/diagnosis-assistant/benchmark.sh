#!/usr/bin/env bash
# NetMind AI — component #7 prep: 3B vs 8B model benchmark.
#
# Times both candidate models against the same representative prompt
# (a retrieved doc chunk + a metrics summary + a question — the actual
# shape component #7 will send), run while the rest of the lab is up
# so contention is real, not measured on an idle machine.
#
# Run from inside the Containerlab distro, with the lab already
# deployed (`lab-up.sh`):
#   bash /mnt/c/MyWorkSpace/AI-Projects/NetMind-AI/intelligence/diagnosis-assistant/benchmark.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="$SCRIPT_DIR/benchmark_prompt.txt"

echo "== Pulling llama3.1:8b (skips if already present) =="
ollama pull llama3.1:8b

# /usr/bin/time (the standalone "time" package -- distinct from bash's
# built-in `time` keyword) isn't in the base wsl-containerlab image
# either, same class of gap as rsync/zstd. Install it if missing
# rather than failing here a second time.
if [ ! -x /usr/bin/time ]; then
  echo "== Installing 'time' package (gives peak RSS, not just wall time) =="
  sudo apt update -qq && sudo apt install -y time
fi

echo
echo "== 3B: llama3.2:3b =="
if [ -x /usr/bin/time ]; then
  /usr/bin/time -f "\n3B wall time: %e s | peak RSS: %M KB" \
    ollama run llama3.2:3b < "$PROMPT_FILE" 2>&1
else
  echo "(falling back to wall-time only, no peak RSS -- 'time' package unavailable)"
  time ollama run llama3.2:3b < "$PROMPT_FILE"
fi

echo
echo "== 8B: llama3.1:8b =="
if [ -x /usr/bin/time ]; then
  /usr/bin/time -f "\n8B wall time: %e s | peak RSS: %M KB" \
    ollama run llama3.1:8b < "$PROMPT_FILE" 2>&1
else
  echo "(falling back to wall-time only, no peak RSS -- 'time' package unavailable)"
  time ollama run llama3.1:8b < "$PROMPT_FILE"
fi

echo
echo "== Also worth checking while both ran: =="
echo "  free -h            # how much headroom is left alongside the other 7 containers"
echo "  docker stats --no-stream   # did any other container get starved during the 8B run"
