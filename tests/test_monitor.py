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
    monitor.BESTBUY_SKU = monitor.PSDIRECT_CODE = monitor.NINTENDO_SKU = ""  # Walmart only here; stores together are tested below
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


def bestbuy_answer(state, text, sku="6690019"):
    """Shaped like the live button-state answer (captured 2026-10-23: COMING_SOON)."""
    atom = {"$type": "atom", "value": {"buttonStateResponseInfos": [
        {"skuId": sku, "buttonState": state, "displayText": text}]}, "$expires": -5000}
    return json.dumps({"jsonGraph": {"shop": {"buttonstate": {"v5": {"item": {"skus": {sku: {"conditions": {
        "NONE": {"destinationZipCode": {"%20": {"storeId": {"%20": {"context": {"cyp": {"addAll": {
            "false": atom}}}}}}}}}}}}}}}}})


monitor.BESTBUY_SKU = "6690019"
bestbuy_cases = [
    ("bestbuy live today: coming soon", bestbuy_answer("COMING_SOON", "Coming Soon"), "out"),
    ("bestbuy sold out", bestbuy_answer("SOLD_OUT", "Sold Out"), "out"),
    ("bestbuy not available", bestbuy_answer("NOT_AVAILABLE", "Not Available"), "out"),
    ("bestbuy add to cart", bestbuy_answer("ADD_TO_CART", "Add to Cart"), "in"),
    ("bestbuy pre-order", bestbuy_answer("PRE_ORDER", "Pre-order"), "in"),
    ("bestbuy unfamiliar state still alerts", bestbuy_answer("SOMETHING_NEW", "Buy now"), "in"),
    ("bestbuy other sku's state ignored", bestbuy_answer("ADD_TO_CART", "Add to Cart", sku="1"), "unknown"),
    ("bestbuy not JSON", "<html>Page Not Found</html>", "unknown"),
    ("bestbuy Access Denied", "<html><title>Access Denied</title></html>", "blocked"),
]
for name, text, want in bestbuy_cases:
    got = monitor.bestbuy_parse(text)
    ok = got[0] == want
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {got}")
print("sample bestbuy alert:", monitor.bestbuy_alert_text(monitor.bestbuy_parse(
    bestbuy_answer("PRE_ORDER", "Pre-order"))[1]).splitlines()[0])



def both(ps5_seq, bb_seq, run_for=1000):
    """Run main() with both stores on a fake clock; returns (messages, checks done per store)."""
    ps5_seq, bb_seq, sent, clock = list(ps5_seq), list(bb_seq), [], [0.0]
    counts = {"ps5": 0, "bestbuy": 0}

    def take(seq, key, idle):
        counts[key] += 1
        return seq.pop(0) if seq else idle

    def sleep(s):
        clock[0] += max(s, 0)
    monitor.BESTBUY_SKU, monitor.RUN_FOR, monitor.STATE_FILE, monitor.BESTBUY_STATE_FILE = "6690019", run_for, "", ""
    monitor.PSDIRECT_CODE = monitor.NINTENDO_SKU = ""
    monitor.INTERVAL, monitor.BESTBUY_INTERVAL = 15, 30
    monitor.fetch = lambda: take(ps5_seq, "ps5", ("out", "x"))
    monitor.bestbuy_fetch = lambda: take(bb_seq, "bestbuy", ("out", "SOLD_OUT"))
    monitor.notify, monitor.log = sent.append, lambda m: None
    monitor.time.sleep, monitor.time.time = sleep, lambda: clock[0]
    monitor.main()
    return sent, counts


# Both stores together on their workflow intervals: PS5 15s, Best Buy 30s.
bb_in = ("in", 'Orderable: button says "Add to Cart" (ADD_TO_CART)')
sent, counts = both([over, under, under], [("out", "COMING_SOON")] * 3 + [bb_in] * 3)
names = sorted(m.split("**")[1] for m in sent)
ok = (len(names) == 2 and names[0].startswith("PS5 Pro") and "Special Edition" in names[1]
      and any("Best Buy" in m for m in sent) and 60 <= counts["ps5"] <= 75 and 30 <= counts["bestbuy"] <= 38)
failed += not ok
print(f"{'ok  ' if ok else 'FAIL'} both alert once each, labelled, PS5 every ~15s and Best Buy every ~30s: "
      f"{names} checks={counts}")
sent, counts = both([("blocked", "HTTP 403")] * 100, [], run_for=3000)
ok = 90 <= counts["bestbuy"] <= 112 and counts["ps5"] < counts["bestbuy"]
failed += not ok
print(f"{'ok  ' if ok else 'FAIL'} PS5 blocked backoff doesn't slow Best Buy: checks={counts}")
ok = any(m.startswith("⚠️ PS5 Pro") for m in sent) and not any("Best Buy" in m for m in sent)
failed += not ok
print(f"{'ok  ' if ok else 'FAIL'} trouble warning names the product")


def psdirect_answer(stock, code="1000050805", price=899):
    """Shaped like the live productList answer (captured 2026-11-17: outOfStock)."""
    return json.dumps({"currentPage": 0, "products": [{
        "baseProduct": f"{code}Base", "code": code, "name": "PlayStation®5 Pro Console", "loginGated": True,
        "categoryHierarchy": [{"code": "SIECategory110", "name": "PS5 Consoles"}],
        "price": {"basePrice": str(price), "currencyIso": "USD", "value": price}, "purchasable": True,
        "stock": {"isProductLowStock": stock == "lowStock", "stockLevelStatus": stock}}]})


monitor.PSDIRECT_CODE = "1000050805"
psdirect_cases = [
    ("psdirect live today: out of stock", psdirect_answer("outOfStock"), "", "out"),
    ("psdirect in stock", psdirect_answer("inStock"), "", "in"),
    ("psdirect low stock", psdirect_answer("lowStock"), "", "in"),
    ("psdirect other product ignored", psdirect_answer("inStock", code="1000041051"), "", "unknown"),
    ("psdirect blank stock", psdirect_answer(""), "", "unknown"),
    ("psdirect not JSON", "<html>Oops</html>", "", "unknown"),
    ("psdirect Access Denied", "<html><title>Access Denied</title></html>", "", "blocked"),
    ("psdirect waiting room", "<html>queue</html>",
     "https://direct-queue.playstation.com/?c=sonyied&e=psdirectprodku1", "in"),
]
for name, text, url, want in psdirect_cases:
    got = monitor.psdirect_parse(text, url)
    ok = got[0] == want
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {got}")
print("sample psdirect alert:", monitor.psdirect_alert_text(monitor.psdirect_parse(
    psdirect_answer("inStock"))[1]).splitlines()[0])

# All three stores together: PlayStation Direct every ~10s, alerts once, and doesn't slow the others.
ps_seq = [("out", "stock: outOfStock")] * 5 + [("in", "stock: inStock, $899")] * 5
psd_count = [0]


def fake_psd():
    psd_count[0] += 1
    return ps_seq.pop(0) if ps_seq else ("out", "stock: outOfStock")


monitor.psdirect_fetch = fake_psd
orig_main_code = "1000050805"
sent, clock = [], [0.0]
monitor.BESTBUY_SKU, monitor.RUN_FOR, monitor.PSDIRECT_CODE, monitor.PSDIRECT_INTERVAL = "6690019", 1000, orig_main_code, 10
monitor.PSDIRECT_STATE_FILE = ""
monitor.fetch = lambda: ("out", "x")
monitor.bestbuy_fetch = lambda: ("out", "SOLD_OUT")
monitor.notify, monitor.log = sent.append, lambda m: None
monitor.time.sleep = lambda s: clock.__setitem__(0, clock[0] + max(s, 0))
monitor.time.time = lambda: clock[0]
monitor.main()
psd_alerts = [m for m in sent if "PlayStation Direct" in m]
ok = len(psd_alerts) == 1 and 90 <= psd_count[0] <= 112 and len(sent) == 1
failed += not ok
print(f"{'ok  ' if ok else 'FAIL'} PlayStation Direct checked every ~10s and alerts once: "
      f"checks={psd_count[0]} alerts={len(psd_alerts)}")


def nintendo_page(salable, sku="121642", linked="OutOfStock", price=519.99, sold_out_permanent=None):
    """Shaped like the live Nintendo Store page (captured 2026-11-17: isSalableQty false, then true)."""
    product = {"__typename": "Product", "sku": sku, "isSalableQty": salable, "maxQtyAllowedInCart": 2,
               "soldOutPermanent": sold_out_permanent,
               'prices({"personalized":false})': {"finalPrice": price, "regularPrice": price}}
    if salable == "missing":
        del product["isSalableQty"]
    apollo = {f'Product:{{"sku":"{sku}"}}': product,
              'Product:{"sku":"127073"}': {"sku": "127073", "isSalableQty": True}}
    data = {"props": {"pageProps": {"initialApolloState": apollo, "linkedData": [
        {"@type": ["Product"], "sku": sku, "offers": {"@type": "Offer", "price": str(price),
                                                      "availability": f"https://schema.org/{linked}"}}]}}}
    return (f'<html><head></head><body><div>Not available</div>'
            f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>')


monitor.NINTENDO_SKU = "121642"
nintendo_cases = [
    ("nintendo live today: not salable", nintendo_page(False), "", "out"),
    ("nintendo live today: salable", nintendo_page(True, linked="InStock"), "", "in"),
    ("nintendo flag wins over stale linkedData", nintendo_page(True, linked="OutOfStock"), "", "in"),
    ("nintendo other product salable ignored", nintendo_page(False, sku="999999"), "", "unknown"),
    ("nintendo flag missing, linkedData InStock", nintendo_page("missing", linked="InStock"), "", "in"),
    ("nintendo flag missing, linkedData OutOfStock", nintendo_page("missing"), "", "out"),
    ("nintendo sold out permanently", nintendo_page(True, sold_out_permanent=True), "", "out"),
    ("nintendo no page data", "<html>Oops</html>", "", "unknown"),
    ("nintendo Access Denied", "<html><title>Access Denied</title></html>", "", "blocked"),
    ("nintendo waiting room", "<html>queue</html>", "https://queue.nintendo.com/?c=nintendo&e=drop", "in"),
    ("nintendo page that mentions queue-it is still read normally", nintendo_page(False).replace(
        "<head>", "<head><script src='https://static.queue-it.net/x.js'></script>"), "", "out"),
]
for name, text, url, want in nintendo_cases:
    got = monitor.nintendo_parse(text, url)
    ok = got[0] == want
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {got}")
print("sample nintendo alert:", monitor.nintendo_alert_text(monitor.nintendo_parse(nintendo_page(True))[1]).splitlines()[0])

# All four together: Nintendo every ~10s, alerts once, and doesn't slow or wake the others.
nin_seq = [("out", "isSalableQty: False")] * 5 + [("in", "isSalableQty: True, $519.99")] * 5
nin_count = [0]


def fake_nintendo():
    nin_count[0] += 1
    return nin_seq.pop(0) if nin_seq else ("out", "isSalableQty: False")


ps_seq[:] = []
psd_count[0] = 0
monitor.nintendo_fetch = fake_nintendo
sent, clock = [], [0.0]
monitor.NINTENDO_SKU, monitor.NINTENDO_INTERVAL, monitor.NINTENDO_STATE_FILE = "121642", 10, ""
monitor.notify = sent.append
monitor.main()
nin_alerts = [m for m in sent if "Nintendo Store" in m]
ok = len(nin_alerts) == 1 and 90 <= nin_count[0] <= 112 and 90 <= psd_count[0] <= 112 and len(sent) == 1
failed += not ok
print(f"{'ok  ' if ok else 'FAIL'} Nintendo checked every ~10s next to PlayStation Direct and alerts once: "
      f"checks={nin_count[0]} psdirect={psd_count[0]} alerts={len(nin_alerts)}")
sys.exit(1 if failed else 0)
