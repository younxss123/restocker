# Restock monitor: PS5 Pro (Walmart Business) + Xbox Series X25 (Microsoft Store, Best Buy)

Checks the PS5 Pro page about every 15 seconds, the Microsoft Store Xbox page about once a minute and the
Best Buy Xbox about every 30 seconds, and posts to Discord:

- **PS5 Pro** on Walmart Business: the moment the **New** offer is in stock for under $1,000.
  Open Box is ignored, and so is a New listing at $1,000 or more (for example a reseller at $1,644.99).
- **Xbox Series X25 Limited Edition** on the Microsoft Store: the moment it can be bought at any price,
  whether pre-orders open or it restocks. The alert says which one it is.
- **Xbox Series X25 Special Edition** at Best Buy (SKU 6690019): the moment its button stops saying
  Coming Soon / Sold Out / Not Available (for example Add to Cart or Pre-order), at any price.
  Best Buy blocks its product pages for cloud servers, so this reads the small button-state
  request the product page itself makes, which does answer from GitHub Actions.

Each alert names its product and store. They are tracked separately, so a block on one store doesn't slow the others.

## Running on GitHub Actions (current setup)
The workflow in `.github/workflows/monitor.yml` checks every 15 seconds for about 55 minutes,
then starts the next run itself, so it keeps going on its own. A schedule every 30 minutes
restarts it if that chain ever breaks. It needs the repo secret `DISCORD_WEBHOOK_URL`.
Alerts ping `@everyone`; set a repo variable `DISCORD_MENTION` (e.g. `<@YOUR_USER_ID>`) to change that.
To change the price limit, set a repo variable `MAX_PRICE` (default `1000`).

To stop it: Actions tab > Restock monitor (PS5 Pro + Xbox X25 + Best Buy) > "..." menu > Disable workflow.
Run it by hand from the Actions tab > Restock monitor (PS5 Pro + Xbox X25 + Best Buy) > Run workflow.

## Running on your own computer
1. In Discord: Server Settings > Integrations > Webhooks > New Webhook, pick a channel, Copy Webhook URL.
2. Install Python 3.9+, then: `pip install -r requirements.txt`
3. Run it:
   - macOS/Linux: `DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..." python3 monitor.py`
   - Windows PowerShell: `$env:DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."; python monitor.py`

## Handy commands
- `python3 monitor.py --test-discord` sends a test message to your channel.
- `python3 monitor.py --once` does one check of each page and prints what it saw (`out`, `in`, `blocked` or `unknown`).
- `python3 monitor.py --demo-alert xbox` sends a sample Xbox alert marked as a test (or `bestbuy`; leave both off for the PS5 one).

## Options (env vars)
- `CHECK_INTERVAL` seconds between checks, default 30. Going much lower raises the chance Walmart blocks you.
- `DISCORD_MENTION` e.g. `@everyone` or `<@YOUR_USER_ID>` so the alert pings your phone.
- `PRODUCT_URL` watch a different Walmart page.
- `XBOX_URL` watch a different Microsoft Store page; set it to an empty value to stop watching the Xbox.
- `XBOX_INTERVAL` seconds between Xbox checks, default 60.
- `BESTBUY_SKU` the Best Buy SKU to watch (default 6690019); set it to an empty value to stop watching Best Buy.
- `BESTBUY_URL` the Best Buy page linked in the alert.
- `BESTBUY_INTERVAL` seconds between Best Buy checks, default 30.
- `MAX_PRICE` only alert when the New price is below this, default 1000.

## Where to run it
It has to stay running. A home computer or Raspberry Pi that stays on works best, since
Walmart blocks cloud/datacenter IPs more often than home internet. If Walmart blocks 20
checks in a row, the monitor posts a warning to Discord so you know alerts may be missed.
