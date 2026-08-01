#!/bin/sh

set -eu

HERE="$(dirname "$(readlink -f $0)")"
PROJECT_ROOT="$(dirname "$HERE")"
cd "$PROJECT_ROOT"
XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
WT_DATA_DIR="$XDG_DATA_HOME/work_timer"

CLEAR='\033[0m'
RED='\033[0;31m'

function usage() {
  if [ -n "$1" ]; then
    echo -e "${RED}$1${CLEAR}\n";
  fi
  echo "Usage: $0 [-b]"
  echo "  -b, --bug   Enable notifications about timer not ticking"
  echo ""
  exit 1
}

BUGGING_ENABLED=''

while [[ "$#" > 0 ]]; do case $1 in
  -b|--bug) BUGGING_ENABLED="1"; shift;;
  *) usage "Unknown parameter passed: $1"; shift; shift;;
esac; done


args=(
    --plandb "$WT_DATA_DIR/plandb"
    --taskdb "$WT_DATA_DIR/tasks"
    --timelog "$WT_DATA_DIR/timelog.json"
    --enable-notifications
)
if [[ -n "$BUGGING_ENABLED" ]]; then
    args+=(--bug-after 5m)
fi

exec uv run textual run --dev src/work_timer/ui/app.py "${args[@]}"
