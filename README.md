# PS5 Pro restock monitor (Walmart Business, New only)

Checks the Walmart Business PS5 Pro page about every 15 seconds and posts to Discord
the moment the **New** offer is in stock for under $1,000. Open Box is ignored, and so is a New
listing at $1,000 or more (for example a reseller at $1,644.99).

## Running on GitHub Actions (current setup)
The workflow in `.github/workflows/monitor.yml` checks every 15 seconds for about 55 minutes,
then starts the next run itself, so it keeps going on its own. A schedule every 30 minutes
restarts it if that chain ever breaks. It needs the repo secret `DISCORD_WEBHOOK_URL`.
Alerts ping `@everyone`; set a repo variable `DISCORD_MENTION` (e.g. `<@YOUR_USER_ID>`) to change that.
To change the price limit, set a repo variable `MAX_PRICE` (default `1000`).

To stop it: Actions tab > PS5 Pro restock monitor > "..." menu > Disable workflow.
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
- `MAX_PRICE` only alert when the New price is below this, default 1000.

## Where to run it
It has to stay running. A home computer or Raspberry Pi that stays on works best, since
Walmart blocks cloud/datacenter IPs more often than home internet. If Walmart blocks 20
checks in a row, the monitor posts a warning to Discord so you know alerts may be missed.
