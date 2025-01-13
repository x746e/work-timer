#!/bin/sh

set -eu

HERE="$(dirname "$(readlink -f $0)")"
PROJECT_ROOT="$(dirname "$HERE")"
cd "$PROJECT_ROOT"

CLEAR='\033[0m'
RED='\033[0;31m'

function usage() {
  if [ -n "$1" ]; then
    echo -e "${RED}$1${CLEAR}\n";
  fi
  echo "Usage: $0 [-m|--memray] [--live-remote]"
  echo "  -m|--memray    Run with the memray memory profiler"
  echo "  --live-remote  Use 'live-remote' memray mode"
  echo ""
  exit 1
}

MEMRAY=''
LIVE_REMOTE=''

while [[ "$#" > 0 ]]; do case $1 in
  -m|--memray) MEMRAY="1"; shift;;
  --live-remote) LIVE_REMOTE="1"; shift;;
  *) usage "Unknown parameter passed: $1"; shift; shift;;
esac; done

args=(
    --plandb ~/dev-plandb
    --taskdb ~/dev-tasks
    --timelog ~/dev-timelog.json
    --work-period-duration 7s
    --break-duration 2s
    --long-break-duration 5s
    --long-break-after 20s
)

if [[ -n "$MEMRAY" ]]; then
    memray_args=()
    if [[ -n "$LIVE_REMOTE" ]]; then
        memray_args+=(
            --live-remote
            --live-port 12345
        )
    fi
    exec uv run memray run "${memray_args[@]}" src/work_timer/ui/app.py "${args[@]}"
else
    exec uv run textual run --dev src/work_timer/ui/app.py "${args[@]}"
fi
