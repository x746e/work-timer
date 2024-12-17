#!/bin/sh

set -eu

HERE="$(dirname $0)"

cd "$HERE"
exec uv run python wtctl.py \
    --taskdb ~/dev-tasks --timelog ~/dev-timelog.json "$@"
