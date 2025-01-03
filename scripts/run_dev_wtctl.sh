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
  echo "Usage: $0 [--prod]"
  echo "  --prod   Use prod datasets"
  echo ""
  exit 1
}

PROD=''

while [[ "$#" > 0 ]]; do case $1 in
  --prod) PROD="1"; shift;;
  -*) usage "Unknown parameter passed: $1"; shift; shift;;
  *) break;
esac; done

if [[ -n "$PROD" ]]; then
    args=(
        --taskdb ~/tasks
        --timelog ~/timelog.json
    )
else
    args=(
        --taskdb ~/dev-tasks
        --timelog ~/dev-timelog.json
    )
fi

exec uv run wtctl "${args[@]}" "$@"
