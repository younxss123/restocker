#!/usr/bin/env bash
# Entry point for the public runner repo (see run.yml). Settings live here, in the
# private repo, so the public workflow file doesn't name any store or product.
# Run from the runner's workspace with this repo checked out at ./src.
# run.yml is the public repo's workflow (copied there as .github/workflows/run.yml,
# kept comment-free on purpose). Secrets it needs in the public repo:
#   SRC_REPO   this repo as owner/name (a secret so the name is masked in logs)
#   SRC_TOKEN  a fine-grained token with read-only Contents access to this repo
#   HOOK       the Discord webhook URL
# Optional repo variables there: PING (default @everyone), MAX (default 1000).
# Running the workflow by hand with "ping" as its input sends a Discord test message
# instead of watching; the run it starts next watches as usual.
set -euo pipefail
export QUIET=1
export DISCORD_WEBHOOK_URL="${HOOK:?HOOK secret not set}"
export DISCORD_MENTION="${PING:-@everyone}"
export MAX_PRICE="${MAX:-1000}"
export RUN_FOR="${T:-3300}"
export CHECK_INTERVAL=15 XBOX_INTERVAL=60 BESTBUY_INTERVAL=30
export STATE_FILE=a.txt XBOX_STATE_FILE=b.txt BESTBUY_STATE_FILE=c.txt
pip install -q -r src/requirements.txt > /dev/null 2>&1
if [ "${T:-}" = "ping" ]; then
  exec python src/monitor.py --test-discord > /dev/null 2>&1
fi
exec python src/monitor.py > /dev/null 2>&1
