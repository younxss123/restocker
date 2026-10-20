#!/usr/bin/env python3
"""Walmart Business restock monitor for the PS5 Pro (New condition only).

Polls the product page, reads the "New" offer's availability and price from the
page's embedded __NEXT_DATA__ JSON, and posts to a Discord webhook when it becomes
in stock under MAX_PRICE. Open Box and other conditions are ignored, and so is a
New listing priced at MAX_PRICE or more (e.g. a reseller at $1,644.99).

Env vars:
  DISCORD_WEBHOOK_URL  required, the Discord channel webhook
  CHECK_INTERVAL       seconds between checks (default 30)
  PRODUCT_URL          override the page to watch
  DISCORD_MENTION      optional text prepended to alerts, e.g. "@everyone" or "<@USER_ID>"
  RUN_FOR              stop after this many seconds (default 0 = run forever)
  STATE_FILE           file that remembers the last status between runs
  MAX_PRICE            only alert when the New price is below this (default 1000)
"""
import json
import os
import random
import re
import sys
import time
from datetime import datetime

# curl_cffi mimics a real browser's TLS fingerprint. Walmart's bot check lets the
# mobile browser profiles through from cloud servers but blocks desktop ones.
from curl_cffi import requests as http

BROWSERS = ["chrome_android", "safari_ios"]

PRODUCT_URL = os.environ.get(
    "PRODUCT_URL",
    "https://business.walmart.com/ip/Sony-PlayStation-5-Pro-Console-PS5-Pro/18235967161"
    "?classType=REGULAR&conditionCode=1&conditionGroupCode=1",
)
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
INTERVAL = int(os.environ.get("CHECK_INTERVAL", "30"))
MENTION = os.environ.get("DISCORD_MENTION", "")
RUN_FOR = int(os.environ.get("RUN_FOR", "0"))  # stop after N seconds (0 = forever), for scheduled runs
STATE_FILE = os.environ.get("STATE_FILE", "")  # remembers last status between scheduled runs
HOME_URL = PRODUCT_URL.split("/ip/")[0] + "/"
# Accept "1000", "$1,000" or "999.99"; anything else falls back to 1000 rather than crashing.
try:
    MAX_PRICE = float(re.sub(r"[$,\s]", "", os.environ.get("MAX_PRICE", "")) or 1000)
except ValueError:
    MAX_PRICE = 1000.0
IN_STOCK = {"IN_STOCK", "AVAILABLE", "LIMITED_STOCK"}


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def status_value(v):
    """availabilityStatus is either "IN_STOCK" or {"display": "In stock", "value": "IN_STOCK"}."""
    if isinstance(v, dict):
        v = v.get("value")
    return str(v).upper() if v else None


def price_value(v):
    """Prices look like {"price": 1644.99, "priceString": "$1,644.99"}."""
    if isinstance(v, dict):
        v = v.get("price")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def money(x):
    return f"${x:,.0f}" if x == int(x) else f"${x:,.2f}"


def judge(st, price):
    """Turn a New offer's stock status and price into (status, detail).

    'in' means in stock AND under MAX_PRICE, which is the only thing worth an alert.
    A missing price still counts as 'in' so a real restock is never skipped.
    """
    if st not in IN_STOCK:
        return "out", f"New: {st}"
    if price is None:
        return "in", "New: IN_STOCK, price not shown"
    if price < MAX_PRICE:
        return "in", f"New: IN_STOCK at ${price:,.2f}"
    return "out", f"New: IN_STOCK at ${price:,.2f}, not under {money(MAX_PRICE)}"


def parse(html):
    """Return (status, detail). status is 'in', 'out', 'blocked' or 'unknown'."""
    low = html.lower()
    if "robot or human" in low or "px-captcha" in low or "/blocked?" in low:
        return "blocked", "bot check page"
    m = re.search(r'<script[^>]*id=["\']?__NEXT_DATA__["\']?[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return "unknown", "no __NEXT_DATA__ on page"
    data = json.loads(m.group(1))
    product = (data.get("props", {}).get("pageProps", {})
               .get("initialData", {}).get("data", {}).get("product"))
    product = product if isinstance(product, dict) else {}
    page_price = price_value((product.get("priceInfo") or {}).get("currentPrice"))

    # The product's offers by condition look like
    #   "conditionOffers": [{"isConditionNew": true, "availabilityStatus": {"value": "IN_STOCK"},
    #                        "price": {"price": 1644.99}, ...},
    #                       {"isConditionNew": false, ...Open Box...}]
    # Only the New ones count.
    new_offers = [d for d in walk(data)
                  if d.get("isConditionNew") is True and "availabilityStatus" in d and "offerId" in d]
    results = []
    for d in new_offers:
        st = status_value(d.get("availabilityStatus"))
        if not st:
            continue
        price = price_value(d.get("price"))
        if price is None and d.get("offerId") == product.get("selectedOfferId"):
            price = page_price  # the page's headline price belongs to the selected offer
        results.append(judge(st, price))
    if results:
        # Any qualifying New offer wins; otherwise report the first one.
        return next((r for r in results if r[0] == "in"), results[0])

    # Fallback: the page's main product. The URL pins conditionCode=1 (New),
    # so the selected offer should be the New one; skip it if it's a known non-New offer.
    not_new_ids = {d.get("offerId") for d in walk(data) if d.get("isConditionNew") is False}
    if product.get("isConditionNew") is not False and product.get("selectedOfferId") not in not_new_ids - {None}:
        st = status_value(product.get("availabilityStatus"))
        if st:
            return judge(st, page_price)
    return "unknown", "availabilityStatus not found"


_session = None
_browser = 0


def new_session():
    """Start a fresh browser-like session, visiting the home page first for cookies."""
    global _session
    _session = http.Session(impersonate=BROWSERS[_browser % len(BROWSERS)])
    _session.get(HOME_URL, timeout=20)
    time.sleep(2)


def fetch():
    global _browser
    if _session is None:
        new_session()
    sep = "&" if "?" in PRODUCT_URL else "?"
    url = f"{PRODUCT_URL}{sep}_={int(time.time())}"  # cache buster
    r = _session.get(url, timeout=20, headers={"Referer": HOME_URL})
    if r.status_code in (403, 429) or r.status_code >= 500:
        result = "blocked", f"HTTP {r.status_code}"
    else:
        result = parse(r.text)
    if result[0] == "blocked":  # switch browser profile and start over next time
        _browser += 1
        new_session()
    return result


def notify(text):
    if not WEBHOOK:
        log("DISCORD_WEBHOOK_URL not set, would have sent: " + text)
        return
    payload = {
        "content": f"{MENTION} {text}".strip(),
        "allowed_mentions": {"parse": ["everyone", "users", "roles"]},
    }
    for attempt in range(3):
        try:
            r = http.post(WEBHOOK, json=payload, timeout=15)
            if r.status_code < 300:
                return
            log(f"Discord returned {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log(f"Discord error: {e}")
        time.sleep(2 ** attempt)


def alert_text(detail):
    return (f"🚨 **PS5 Pro (New) is IN STOCK under {money(MAX_PRICE)}** on Walmart Business! "
            f"({detail})\n{PRODUCT_URL}")


def main():
    if "--test-discord" in sys.argv:
        notify("Restock monitor test message: Discord alerts are working.")
        return
    if "--demo-alert" in sys.argv:
        notify("🧪 **TEST, not a real restock.** This is what a restock alert looks like:\n"
               + alert_text("New: IN_STOCK at $899.00"))
        return
    if "--once" in sys.argv:
        print(fetch())
        return
    log(f"Watching {PRODUCT_URL} every ~{INTERVAL}s")
    last = None
    if STATE_FILE and os.path.exists(STATE_FILE):
        last = open(STATE_FILE).read().strip() or None
    blocked_streak = 0
    trouble_streak = 0  # checks in a row that couldn't read the stock status
    deadline = time.time() + RUN_FOR if RUN_FOR else None
    while deadline is None or time.time() < deadline:
        try:
            status, detail = fetch()
        except Exception as e:
            status, detail = "unknown", f"error: {e}"
        log(f"{status}: {detail}")
        if status == "in" and last != "in":
            notify(alert_text(detail))
        if status in ("in", "out"):
            last = status
            if STATE_FILE:
                with open(STATE_FILE, "w") as f:
                    f.write(status)
            if trouble_streak >= 20:
                notify("✅ Restock monitor: reading the page normally again.")
            blocked_streak = trouble_streak = 0
        else:
            trouble_streak += 1
            if status == "blocked":
                blocked_streak += 1
            if trouble_streak == 20:
                notify(f"⚠️ Restock monitor: the last 20 checks couldn't read the stock status "
                       f"({detail}). Alerts may be missed until this clears.")
        # back off when blocked, jitter so requests don't look robotic
        wait = INTERVAL * (min(blocked_streak, 6) + 1) if status == "blocked" else INTERVAL
        time.sleep(wait + random.uniform(0, INTERVAL * 0.3))


if __name__ == "__main__":
    main()
