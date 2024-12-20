#!/bin/sh

set -eu

HERE="$(dirname "$(readlink -f $0)")"
PROJECT_ROOT="$(dirname "$HERE")"
cd "$PROJECT_ROOT"

cd "$HERE"
exec uv run wtctl \
    --taskdb ~/dev-tasks --timelog ~/dev-timelog.json "$@"
