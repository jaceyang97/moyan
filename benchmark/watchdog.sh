#!/usr/bin/env bash
# Watchdog for autoskill: restarts the loop if it dies for any reason.
# Stops only when autoskill exits 0 (graceful: max iters, plateau, KeyboardInterrupt)
# or when /tmp/autoskill.stop exists.
#
# Usage:
#   ANTHROPIC_API_KEY=sk-... ./watchdog.sh <tag> <max_iters>
# Example:
#   nohup setsid ./watchdog.sh v1 25 > /tmp/watchdog.log 2>&1 < /dev/null & disown

set -u
TAG="${1:-v1}"
MAX_ITERS="${2:-25}"
BASELINE="${3:-v0}"
PUSH_BRANCH="${4:-autoskill/v1}"
STOP_FILE="/tmp/autoskill.stop"
MAX_RESTARTS=20
LOG="/tmp/autoskill_${TAG}.log"

cd "$(dirname "$0")"

restart_count=0
while [ $restart_count -lt $MAX_RESTARTS ]; do
  if [ -f "$STOP_FILE" ]; then
    echo "[watchdog $(date +%T)] stop file present, exiting"
    break
  fi
  echo "[watchdog $(date +%T)] launching autoskill (restart=$restart_count, tag=$TAG)" | tee -a "$LOG"
  python3 -u autoskill.py \
    --tag "$TAG" \
    --baseline-run-id "$BASELINE" \
    --max-iters "$MAX_ITERS" \
    --judge-every 3 \
    --push-branch "$PUSH_BRANCH" \
    >> "$LOG" 2>&1
  rc=$?
  echo "[watchdog $(date +%T)] autoskill exited rc=$rc" | tee -a "$LOG"
  if [ $rc -eq 0 ]; then
    echo "[watchdog $(date +%T)] graceful exit, stopping watchdog" | tee -a "$LOG"
    break
  fi
  restart_count=$((restart_count + 1))
  echo "[watchdog $(date +%T)] sleeping 30s before restart" | tee -a "$LOG"
  sleep 30
done

echo "[watchdog $(date +%T)] watchdog terminated after $restart_count restarts" | tee -a "$LOG"
