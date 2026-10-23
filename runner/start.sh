#!/usr/bin/env bash
# Entry point for the public runner repo (see run.yml). Settings live here, in the
# private repo, so the public workflow file doesn't name any store or product.
# Run from the runner's workspace with this repo checked out at ./src.
set -euo pipefail
export QUIET=1
export DISCORD_WEBHOOK_URL="${HOOK:?HOOK secret not set}"
export DISCORD_MENTION="${PING:-@everyone}"
export MAX_PRICE="${MAX:-1000}"
export RUN_FOR="${T:-3300}"
export CHECK_INTERVAL=15 XBOX_INTERVAL=60 BESTBUY_INTERVAL=30
export STATE_FILE=a.txt XBOX_STATE_FILE=b.txt BESTBUY_STATE_FILE=c.txt
pip install -q -r src/requirements.txt > /dev/null 2>&1
exec python src/monitor.py > /dev/null 2>&1
