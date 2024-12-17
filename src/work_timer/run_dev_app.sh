#!/bin/sh

set -eux

HERE="$(dirname $0)"

cd "$HERE"
exec uv run textual run --dev ui/app.py \
    --taskdb ~/dev-tasks --timelog ~/dev-timelog.json \
    --work-period-duration 10s --break-duration 5s \
    --long-break-duration 7s --long-break-after 1m \
    --enable-notifications
