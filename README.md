# PS5 Pro restock monitor (Walmart Business, New only)

Checks the Walmart Business PS5 Pro page about every 30 seconds and posts to Discord
the moment the **New** offer goes from out of stock to in stock. Open Box is ignored.

## Running on GitHub Actions (current setup)
The workflow in `.github/workflows/monitor.yml` runs for about 55 minutes at a time, checking every
20 seconds, and a new run queues every 10 minutes so the next one picks up when the last ends.
It needs the repo secret `DISCORD_WEBHOOK_URL`. Alerts ping `@everyone`; set a repo variable
`DISCORD_MENTION` (e.g. `<@YOUR_USER_ID>`) to change that.
Run it by hand from the Actions tab > PS5 Pro restock monitor > Run workflow.

## Running on your own computer
1. In Discord: Server Settings > Integrations > Webhooks > New Webhook, pick a channel, Copy Webhook URL.
2. Install Python 3.9+, then: `pip install -r requirements.txt`
3. Run it:
   - macOS/Linux: `DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..." python3 monitor.py`
   - Windows PowerShell: `$env:DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."; python monitor.py`

## Handy commands
- `python3 monitor.py --test-discord` sends a test message to your channel.
- `python3 monitor.py --once` does one check and prints what it saw (`out`, `in`, `blocked` or `unknown`).

## Options (env vars)
- `CHECK_INTERVAL` seconds between checks, default 30. Going much lower raises the chance Walmart blocks you.
- `DISCORD_MENTION` e.g. `@everyone` or `<@YOUR_USER_ID>` so the alert pings your phone.
- `PRODUCT_URL` watch a different page.

## Where to run it
It has to stay running. A home computer or Raspberry Pi that stays on works best, since
Walmart blocks cloud/datacenter IPs more often than home internet. If Walmart blocks 20
checks in a row, the monitor posts a warning to Discord so you know alerts may be missed.
