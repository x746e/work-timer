#!/bin/sh

set -eu

HERE="$(dirname "$(readlink -f $0)")"
PROJECT_ROOT="$(dirname "$HERE")"
cd "$PROJECT_ROOT"

exec uv run textual run --dev src/work_timer/ui/app.py \
    --taskdb ~/dev-tasks --timelog ~/dev-timelog.json \
    --work-period-duration 3s --break-duration 2s \
    --long-break-duration 7s --long-break-after 1m \
    --enable-notifications
