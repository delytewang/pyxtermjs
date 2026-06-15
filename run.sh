#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

.venv/bin/python -m pyxtermjs \
  --auth-file auth.json \
  --host 0.0.0.0 \
  --command ./terminal-entry.sh
