#!/bin/sh
set -eux

HERE="$(dirname "$(readlink -f $0)")"
PROJECT_ROOT="$(dirname "$HERE")"
cd "$PROJECT_ROOT"

uv build --wheel
uv tool install --force dist/work_timer-*-py3-none-any.whl
uv tool upgrade work-timer
