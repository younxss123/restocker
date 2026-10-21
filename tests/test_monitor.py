"""Offline checks for the page parsing and alert logic. Run: python tests/test_monitor.py"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("MAX_PRICE", None)
import monitor  # noqa: E402

RESELLER, WALMART, OPEN_BOX = "7D41131D710C33F1AA0E29FE223F3B12", "7C3AA4268C833F3FB2D9217803A3C465", "ADF3E"


def offer(offer_id, new, status, price):
    """Shaped like the live page's conditionOffers entries (captured 2026-10-20)."""
    return {"offerId": offer_id, "isConditionNew": new,
            "availabilityStatus": {"display": status.title(), "value": status},
            "condition": {"code": 1 if new else 9, "text": "New" if new else "Open Box"},
            "price": {"price": price, "priceString": None if price is None else f"${price:,.2f}"}}


def page(offers, selected, top_status, top_price):
    product = {"selectedOfferId": selected, "isConditionNew": True, "availabilityStatus": top_status,
               "priceInfo": {"currentPrice": {"price": top_price}},
               "secondaryOfferPrice": {"currentPrice": {"price": 899}},
               "conditionOffers": offers,
               "fulfillmentOptions": [{"type": "SHIPPING", "availabilityStatus": top_status}]}
    data = {"props": {"pageProps": {"initialData": {"data": {"product": product}}}}}
    return f'<div></div><script id=__NEXT_DATA__ type="application/json" nonce=x>{json.dumps(data)}</script>'


cases = [
    # Live page 2026-10-20: New in stock from a reseller at $1,644.99, Open Box in stock -> no alert.
    ("reseller over limit",
     page([offer(RESELLER, True, "IN_STOCK", 1644.99), offer(OPEN_BOX, False, "IN_STOCK", None)],
          RESELLER, "IN_STOCK", 1644.99), "out"),
    # Live page 2026-10-19: New out of stock at $899, Open Box in stock -> no alert.
    ("walmart out of stock",
     page([offer(WALMART, True, "OUT_OF_STOCK", 899), offer(OPEN_BOX, False, "IN_STOCK", None)],
          WALMART, "OUT_OF_STOCK", 899), "out"),
    ("walmart restock at $899",
     page([offer(WALMART, True, "IN_STOCK", 899), offer(OPEN_BOX, False, "IN_STOCK", None)],
          WALMART, "IN_STOCK", 899), "in"),
    ("exactly $1,000 is not under", page([offer(WALMART, True, "IN_STOCK", 1000)], WALMART, "IN_STOCK", 1000), "out"),
    ("$999.99 is under", page([offer(WALMART, True, "IN_STOCK", 999.99)], WALMART, "IN_STOCK", 999.99), "in"),
    ("offer price missing, page price used",
     page([offer(WALMART, True, "IN_STOCK", None)], WALMART, "IN_STOCK", 899), "in"),
    ("offer price missing, page price over limit",
     page([offer(RESELLER, True, "IN_STOCK", None)], RESELLER, "IN_STOCK", 1644.99), "out"),
    ("no price anywhere still alerts", page([offer(WALMART, True, "IN_STOCK", None)], WALMART, "IN_STOCK", None), "in"),
    ("cheap Open Box ignored",
     page([offer(RESELLER, True, "OUT_OF_STOCK", 1644.99), offer(OPEN_BOX, False, "IN_STOCK", 500)],
          RESELLER, "OUT_OF_STOCK", 1644.99), "out"),
    ("no conditionOffers, top-level fallback under limit", page([], None, "IN_STOCK", 899), "in"),
    ("no conditionOffers, top-level fallback over limit", page([], None, "IN_STOCK", 1644.99), "out"),
    ("bot check page", "<title>Robot or human?</title>", "blocked"),
    ("selected Open Box with no New entry is not treated as New",
     page([offer(OPEN_BOX, False, "IN_STOCK", 649)], OPEN_BOX, "IN_STOCK", 649), "unknown"),
]
failed = 0
for name, html, want in cases:
    got = monitor.parse(html)
    ok = got[0] == want
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {got}")


def alerts(seq, last=None):
    """Feed fake check results through main() and return the Discord messages it would send."""
    seq = list(seq)

    def fake_fetch():
        if not seq:
            raise KeyboardInterrupt
        return seq.pop(0)

    sent = []
    monitor.XBOX_URL = ""  # PS5 only here; both products together are tested below
    monitor.fetch, monitor.notify, monitor.log = fake_fetch, sent.append, lambda m: None
    monitor.time.sleep = lambda s: None
    try:
        monitor.main()
    except KeyboardInterrupt:
        pass
    return sent


over = ("out", "New: IN_STOCK at $1,644.99, not under $1,000")
under = ("in", "New: IN_STOCK at $899.00")
transitions = [
    ("reseller then Walmart restock alerts once", [over, over, under, under], 1),
    ("reseller only never alerts", [over] * 5, 0),
    ("restock, sells out, restocks again alerts twice", [under, ("out", "New: OUT_OF_STOCK"), under], 2),
    ("unknown check in between does not re-alert", [under, ("unknown", "x"), under], 1),
]
for name, seq, want in transitions:
    got = [m for m in alerts(seq) if m.startswith("🚨")]
    ok = len(got) == want
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {len(got)} alert(s)")
import subprocess  # noqa: E402
for raw, want in [("$1,000", 1000.0), ("999.99", 999.99), ("", 1000.0), ("abc", 1000.0)]:
    out = subprocess.run([sys.executable, "-c", "import monitor; print(monitor.MAX_PRICE)"],
                         cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         env={**os.environ, "MAX_PRICE": raw}, capture_output=True, text=True).stdout.strip()
    ok = out == str(want)
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} MAX_PRICE={raw!r} -> {out}")
msgs = alerts([over, under])
print("sample alert:", msgs[-1].splitlines()[0])


def xbox_page(ld_availability, button_disabled, cta, action_text="Build your device", price=899.99,
              release="2026-11-13T05:00:00.0000000Z"):
    """Shaped like the live Microsoft Store page (captured 2026-10-21: OutOfStock, button off)."""
    ld = {"@context": "https://schema.org", "@type": "Product", "name": "XBOX Series X25 Limited Edition",
          "offers": {"@type": "AggregateOffer", "priceCurrency": "USD", "lowPrice": price,
                     "offers": [{"availability": f"https://schema.org/{ld_availability}", "price": price}]}}
    box = {"product": {"productId": "8wg5vqp0x4h3", "skuOrder": {"0": ["JXZJ"]}, "skuInfo": {"JXZJ": {
        "skuId": "JXZJ", "price": {"current": f"${price:,.2f}"}, "ctaDescription": cta,
        "releaseMessageDateValue": release,
        "action": {"action": "ConfigureDevice", "actionText": action_text, "disabled": button_disabled}}}}}
    # The live page also has a static marketing "Pre-order now" button, which must not count.
    return (f'<script type="application/ld+json">{json.dumps(ld)}</script>'
            '<a data-bi-cn="Pre-order now" aria-label="Pre-order now">Pre-order now</a>'
            f'<script>window.__BuyBox__={json.dumps(box)};</script>')


xbox_cases = [
    ("xbox live page today: out of stock", xbox_page("OutOfStock", True, "Out of stock"), "out", "Out of stock"),
    ("xbox pre-order opens", xbox_page("PreOrder", False, None, "Pre-order"), "in", "Pre-order open"),
    ("xbox restock after release", xbox_page("InStock", False, None, "Add to cart", release="2000-01-01"),
     "in", "In stock"),
    ("xbox buyable before release is a pre-order", xbox_page("InStock", False, None), "in", "Pre-order open"),
    ("xbox button on, schema still says out", xbox_page("OutOfStock", False, None, "Pre-order"), "in", "Pre-order"),
    ("xbox schema says pre-order, button data missing",
     xbox_page("PreOrder", True, None).split("<script>window")[0], "in", "Pre-order open"),
    ("xbox nothing readable", "<html>hi</html>", "unknown", ""),
    ("xbox Access Denied", "<html><title>Access Denied</title></html>", "blocked", ""),
]
for name, html, want, prefix in xbox_cases:
    got = monitor.xbox_parse(html)
    ok = got[0] == want and got[1].startswith(prefix)
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {got}")


def both(ps5_seq, xbox_seq, run_for=1000):
    """Run main() with both products on a fake clock; returns (messages, checks done per product)."""
    ps5_seq, xbox_seq, sent, clock = list(ps5_seq), list(xbox_seq), [], [0.0]
    counts = {"ps5": 0, "xbox": 0}

    def take(seq, key):
        counts[key] += 1
        return seq.pop(0) if seq else ("out", "x")

    def sleep(s):
        clock[0] += max(s, 0)
    monitor.XBOX_URL, monitor.RUN_FOR, monitor.STATE_FILE, monitor.XBOX_STATE_FILE = "https://x", run_for, "", ""
    monitor.INTERVAL = 15
    monitor.fetch, monitor.xbox_fetch = lambda: take(ps5_seq, "ps5"), lambda: take(xbox_seq, "xbox")
    monitor.notify, monitor.log = sent.append, lambda m: None
    monitor.time.sleep, monitor.time.time = sleep, lambda: clock[0]
    monitor.main()
    return sent, counts


pre = ("in", 'Pre-order open: $899.99, button says "Pre-order"')
sent, counts = both([over, under, under], [("out", "Out of stock"), pre, pre])
names = sorted(m.split("**")[1] for m in sent)
ok = (len(names) == 2 and names[0].startswith("PS5 Pro") and "Xbox Series X25" in names[1]
      and "PRE-ORDERS ARE OPEN" in names[1] and abs(counts["ps5"] - counts["xbox"]) <= 6 and counts["ps5"] > 50)
failed += not ok
print(f"{'ok  ' if ok else 'FAIL'} both products alert once each, labelled: {names} checks={counts}")
blocked = ("blocked", "HTTP 403")
sent, counts = both([blocked] * 100, [], run_for=3000)
ok = counts["xbox"] > 50 and counts["ps5"] < counts["xbox"] / 2
failed += not ok
print(f"{'ok  ' if ok else 'FAIL'} PS5 blocked backoff doesn't slow the Xbox: checks={counts}")
ok = any(m.startswith("⚠️ PS5 Pro") for m in sent) and not any("Xbox" in m for m in sent)
failed += not ok
print(f"{'ok  ' if ok else 'FAIL'} trouble warning names the product")
print("sample xbox alert:", monitor.xbox_alert_text(pre[1]).splitlines()[0])
sys.exit(1 if failed else 0)
