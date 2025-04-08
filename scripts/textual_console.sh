#!/bin/bash -eu

TERMINAL_WIDTH="$(tmux display -p '#{window_width}')"

tmux split-window -h
tmux send-keys 'uv run textual console -x EVENT' Enter
tmux resize-pane -x "$(( $TERMINAL_WIDTH / 3 ))"
tmux select-pane -t '!'
