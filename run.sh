#!/usr/bin/env bash
set -e

.venv/bin/python -m pyxtermjs --auth-file auth.json --host 0.0.0.0
