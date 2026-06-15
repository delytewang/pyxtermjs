#!/usr/bin/env bash
set -e

SESSION_NAME="pymain"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  exec tmux attach-session -t "$SESSION_NAME"
else
  exec tmux new-session -s "$SESSION_NAME"
fi
