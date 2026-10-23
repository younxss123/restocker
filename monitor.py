#!/usr/bin/env python3
"""Restock monitor for the PS5 Pro (Walmart Business, New only), the
Xbox Series X25 Limited Edition (Microsoft Store, pre-order or in stock) and the
Xbox Series X25 Special Edition (Best Buy, pre-order or in stock).

Polls the product page, reads the "New" offer's availability and price from the
page's embedded __NEXT_DATA__ JSON, and posts to a Discord webhook when it becomes
in stock under MAX_PRICE. Open Box and other conditions are ignored, and so is a
New listing priced at MAX_PRICE or more (e.g. a reseller at $1,644.99).

The Xbox page is checked on the same schedule and alerts, at any price, when its
buy button turns on, whether that's for a pre-order or a restock.

Best Buy blocks its product pages for cloud servers, so the Best Buy SKU is read
from the small button-state API the product page itself uses for its
Add to Cart button. It alerts, at any price, when that button stops saying
"Coming Soon" / "Sold Out" / "Not Available".

Env vars:
  DISCORD_WEBHOOK_URL  required, the Discord channel webhook
  CHECK_INTERVAL       seconds from one check to the next, +/-10% (default 30)
  PRODUCT_URL          override the page to watch
  DISCORD_MENTION      optional text prepended to alerts, e.g. "@everyone" or "<@USER_ID>"
  RUN_FOR              stop after this many seconds (default 0 = run forever)
  STATE_FILE           file that remembers the last status between runs
  MAX_PRICE            only alert when the New price is below this (default 1000)
  XBOX_URL             the Microsoft Store page to watch; set it empty to stop watching it
  XBOX_STATE_FILE      like STATE_FILE, for the Xbox
  XBOX_INTERVAL        seconds from one Xbox check to the next, +/-10% (default 60)
  BESTBUY_SKU          the Best Buy SKU to watch; set it empty to stop watching Best Buy
  BESTBUY_URL          the Best Buy page linked in the alert
  BESTBUY_STATE_FILE   like STATE_FILE, for Best Buy
  BESTBUY_INTERVAL     seconds from one Best Buy check to the next, +/-10% (default 30)
  QUIET                set to 1 to print nothing while watching (for public run logs);
                       Discord alerts and warnings still go out
"""
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote

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

XBOX_NAME = "Xbox Series X25 Limited Edition"
XBOX_URL = os.environ.get(
    "XBOX_URL", "https://www.microsoft.com/en-us/d/xbox-series-x25-limited-edition/8wg5vqp0x4h3")
XBOX_STATE_FILE = os.environ.get("XBOX_STATE_FILE", "")
XBOX_INTERVAL = int(os.environ.get("XBOX_INTERVAL", "60"))
XBOX_BROWSERS = ["chrome", "safari", "chrome_android"]
# schema.org availability values that mean you can order it now.
BUYABLE = {"INSTOCK", "PREORDER", "PRESALE", "LIMITEDAVAILABILITY", "ONLINEONLY", "BACKORDER"}

BESTBUY_NAME = "Xbox Series X25 Special Edition"
BESTBUY_SKU = os.environ.get("BESTBUY_SKU", "6690019")
BESTBUY_URL = os.environ.get(
    "BESTBUY_URL",
    "https://www.bestbuy.com/product/xbox-x-x25-special-edition-gaming-1tb-console-with-wireless-controller-"
    "halo-campaign-evolved-4k-gaming-120fps/JJGXP36RRV/sku/6690019")
BESTBUY_STATE_FILE = os.environ.get("BESTBUY_STATE_FILE", "")
BESTBUY_INTERVAL = int(os.environ.get("BESTBUY_INTERVAL", "30"))
BESTBUY_BROWSERS = ["chrome", "safari", "chrome_android", "safari_ios"]
# Best Buy button states that mean you can't order it. Anything else (ADD_TO_CART,
# PRE_ORDER, CHECK_STORES, or a state we haven't seen) counts as orderable, so a
# real drop is never missed.
BESTBUY_NOT_BUYABLE = {"COMING_SOON", "SOLD_OUT", "NOT_AVAILABLE", "UNAVAILABLE_NATIONWIDE", "TEMPORARILY_UNAVAILABLE"}


QUIET = os.environ.get("QUIET", "") not in ("", "0")


def log(msg):
    if QUIET:
        return
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


def xbox_parse(html):
    """Return (status, detail) for the Microsoft Store page, status as in parse().

    Two signals, both server-rendered fresh on every request:
      - the schema.org Product JSON-LD, whose offer "availability" is e.g. OutOfStock,
        PreOrder or InStock
      - window.__BuyBox__, whose SKU has the buy button ("action", with "disabled")
        and the text under the price ("ctaDescription", e.g. "Out of stock")
    Either one saying it can be ordered counts, so a real drop isn't missed.
    The page also has a static "Pre-order now" marketing button; that is ignored.
    """
    low = html.lower()
    if "<title>access denied" in low or "px-captcha" in low:
        return "blocked", "bot check page"
    ld, price = None, None
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        if not (isinstance(d, dict) and d.get("@type") == "Product"):
            continue
        offers = d.get("offers") or {}
        offers = (offers.get("offers") or [offers]) if isinstance(offers, dict) else offers
        for o in offers if isinstance(offers, list) else []:
            if isinstance(o, dict) and o.get("availability"):
                ld = str(o["availability"]).rstrip("/").rsplit("/", 1)[-1]
                price = price_value(o.get("price"))
                break
    sku = {}
    m = re.search(r"window\.__BuyBox__\s*=\s*", html)
    if m:
        try:
            box, _ = json.JSONDecoder().raw_decode(html, m.end())
        except ValueError:
            box = {}
        product = box.get("product") if isinstance(box, dict) else None
        skus = (product or {}).get("skuInfo") or {}
        order = ((product or {}).get("skuOrder") or {}).get("0") or list(skus)
        sku = next((skus[k] for k in order if isinstance(skus.get(k), dict)), {})
    action = sku.get("action") if isinstance(sku.get("action"), dict) else {}
    if ld is None and "disabled" not in action:
        return "unknown", "availability not found on Microsoft Store page"
    if price is None:
        price = price_value(re.sub(r"[$,]", "", str((sku.get("price") or {}).get("current") or "")) or None)

    button_on = action.get("disabled") is False
    cta = sku.get("ctaDescription")
    words = " ".join(str(x) for x in (ld, action.get("actionText"), cta) if x).lower()
    preorder = str(ld).upper() in ("PREORDER", "PRESALE") or "pre-order" in words or "preorder" in words
    # Buyable before its release date (2026-11-13 on the page today) is a pre-order too.
    release = str(sku.get("releaseMessageDateValue") or "")[:10]
    preorder = preorder or (bool(re.fullmatch(r"\d{4}-\d\d-\d\d", release))
                            and release > datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    shown = f"${price:,.2f}" if price is not None else "price not shown"
    if button_on or str(ld).upper() in BUYABLE:
        button = f"button says \"{action['actionText']}\"" if button_on and action.get("actionText") else ld
        return "in", f"{'Pre-order open' if preorder else 'In stock'}: {shown}, {button}"
    return "out", ", ".join(b for b in (cta or ld, shown, "buy button off") if b)


_xbox_session = None
_xbox_browser = 0


def xbox_fetch():
    global _xbox_session, _xbox_browser
    if _xbox_session is None:
        _xbox_session = http.Session(impersonate=XBOX_BROWSERS[_xbox_browser % len(XBOX_BROWSERS)])
    sep = "&" if "?" in XBOX_URL else "?"
    r = _xbox_session.get(f"{XBOX_URL}{sep}_={int(time.time())}", timeout=20)
    if r.status_code in (403, 429) or r.status_code >= 500:
        result = "blocked", f"HTTP {r.status_code}"
    else:
        result = xbox_parse(r.text)
    if result[0] == "blocked":  # switch browser profile next time
        _xbox_browser += 1
        _xbox_session = None
    return result


def bestbuy_api_url(sku):
    """The button-state request the Best Buy product page makes for its Add to Cart button."""
    path = ["shop", "buttonstate", "v5", "item", "skus", int(sku), "conditions", "NONE",
            "destinationZipCode", "%20", "storeId", "%20", "context", "cyp", "addAll", "false"]
    return (f"https://www.bestbuy.com/api/tcfb/model.json?paths={quote(json.dumps([path], separators=(',', ':')))}"
            f"&method=get")


def bestbuy_parse(text, sku=None):
    """Return (status, detail) from the button-state answer, status as in parse().

    The answer looks like (captured 2026-10-23):
      {"jsonGraph": {...: {"value": {"buttonStateResponseInfos":
          [{"skuId": "6690019", "buttonState": "COMING_SOON", "displayText": "Coming Soon"}]}}}}
    """
    sku = str(sku or BESTBUY_SKU)
    low = text.lower()
    if "<title>access denied" in low or "px-captcha" in low:
        return "blocked", "bot check page"
    try:
        data = json.loads(text)
    except ValueError:
        return "unknown", "Best Buy answer wasn't JSON"
    infos = [d for d in walk(data) if "buttonState" in d and str(d.get("skuId", sku)) == sku]
    if not infos:
        return "unknown", "buttonState not found in Best Buy answer"
    state = str(infos[0]["buttonState"]).upper()
    shown = f"button says \"{infos[0].get('displayText') or state}\" ({state})"
    if state in BESTBUY_NOT_BUYABLE:
        return "out", shown
    return "in", f"{'Pre-order open' if 'PRE' in state else 'Orderable'}: {shown}"


_bestbuy_session = None
_bestbuy_browser = 0


def bestbuy_fetch():
    global _bestbuy_session, _bestbuy_browser
    if _bestbuy_session is None:
        _bestbuy_session = http.Session(impersonate=BESTBUY_BROWSERS[_bestbuy_browser % len(BESTBUY_BROWSERS)])
    r = _bestbuy_session.get(f"{bestbuy_api_url(BESTBUY_SKU)}&_={int(time.time())}", timeout=20,
                             headers={"Referer": BESTBUY_URL})
    if r.status_code in (403, 429) or r.status_code >= 500:
        result = "blocked", f"HTTP {r.status_code}"
    else:
        result = bestbuy_parse(r.text)
    if result[0] == "blocked":  # switch browser profile next time
        _bestbuy_browser += 1
        _bestbuy_session = None
    return result


def bestbuy_alert_text(detail):
    what = "PRE-ORDERS ARE OPEN" if detail.startswith("Pre-order") else "IN STOCK"
    return f"🚨 **{BESTBUY_NAME}: {what}** at Best Buy! ({detail})\n{BESTBUY_URL}"


def xbox_alert_text(detail):
    what = "PRE-ORDERS ARE OPEN" if detail.startswith("Pre-order") else "IN STOCK"
    return f"🚨 **{XBOX_NAME}: {what}** on Microsoft Store! ({detail})\n{XBOX_URL}"


def alert_text(detail):
    return (f"🚨 **PS5 Pro (New) is IN STOCK under {money(MAX_PRICE)}** on Walmart Business! "
            f"({detail})\n{PRODUCT_URL}")


def main():
    if "--test-discord" in sys.argv:
        notify("Restock monitor test message: Discord alerts are working.")
        return
    if "--demo-alert" in sys.argv:
        if "bestbuy" in sys.argv:
            sample = bestbuy_alert_text('Orderable: button says "Add to Cart" (ADD_TO_CART)')
        elif "xbox" in sys.argv:
            sample = xbox_alert_text('Pre-order open: $899.99, button says "Pre-order"')
        else:
            sample = alert_text("New: IN_STOCK at $899.00")
        notify("🧪 **TEST, not a real restock.** This is what a restock alert looks like:\n" + sample)
        return
    if "--once" in sys.argv:
        print("PS5 Pro:", fetch())
        if XBOX_URL:
            print(f"{XBOX_NAME}:", xbox_fetch())
        if BESTBUY_SKU:
            print(f"{BESTBUY_NAME} (Best Buy):", bestbuy_fetch())
        return
    # Each product is checked on its own schedule with its own saved status,
    # so trouble with one store never delays or resets the others.
    watches = [Watch("PS5 Pro", lambda: fetch(), alert_text, STATE_FILE, PRODUCT_URL, INTERVAL)]
    if XBOX_URL:
        watches.append(Watch(XBOX_NAME, lambda: xbox_fetch(), xbox_alert_text, XBOX_STATE_FILE, XBOX_URL,
                             XBOX_INTERVAL))
    if BESTBUY_SKU:
        watches.append(Watch(f"{BESTBUY_NAME} (Best Buy)", lambda: bestbuy_fetch(), bestbuy_alert_text,
                             BESTBUY_STATE_FILE, BESTBUY_URL, BESTBUY_INTERVAL))
    for w in watches:
        log(f"Watching {w.url} every ~{w.interval}s")
    deadline = time.time() + RUN_FOR if RUN_FOR else None
    while deadline is None or time.time() < deadline:
        w = min(watches, key=lambda w: w.due)
        time.sleep(max(0, w.due - time.time()))
        if deadline is not None and time.time() >= deadline:
            break
        w.check_once()


class Watch:
    def __init__(self, name, check, alert, state_file, url, interval):
        self.name, self.check, self.alert, self.state_file, self.url = name, check, alert, state_file, url
        self.interval = interval
        self.last = None
        if state_file and os.path.exists(state_file):
            self.last = open(state_file).read().strip() or None
        self.blocked_streak = 0
        self.trouble_streak = 0  # checks in a row that couldn't read the stock status
        self.due = 0.0

    def check_once(self):
        started = time.time()
        try:
            status, detail = self.check()
        except Exception as e:
            status, detail = "unknown", f"error: {e}"
        log(f"{self.name}: {status}: {detail}")
        if status == "in" and self.last != "in":
            notify(self.alert(detail))
        if status in ("in", "out"):
            self.last = status
            if self.state_file:
                with open(self.state_file, "w") as f:
                    f.write(status)
            if self.trouble_streak >= 20:
                notify(f"✅ {self.name} restock monitor: reading the page normally again.")
            self.blocked_streak = self.trouble_streak = 0
        else:
            self.trouble_streak += 1
            if status == "blocked":
                self.blocked_streak += 1
            if self.trouble_streak == 20:
                notify(f"⚠️ {self.name} restock monitor: the last 20 checks couldn't read the stock status "
                       f"({detail}). Alerts may be missed until this clears.")
        # interval is the time from one check's start to the next, give or take 10% so
        # requests don't look robotic; back off when blocked.
        wait = self.interval * (min(self.blocked_streak, 6) + 1) if status == "blocked" else self.interval
        self.due = started + wait * random.uniform(0.9, 1.1)

if __name__ == "__main__":
    main()
