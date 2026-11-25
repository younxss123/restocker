"""Temporary: probe GameStop from a GitHub runner (page + SFCC Product-Variation JSON)."""
import json
import re
import time

from curl_cffi import requests as http

PAGE = ("https://www.gamestop.com/consoles-hardware/playstation-5/consoles/products/"
        "sony-playstation-5-pro-console/20015604.html")
BASE = "https://www.gamestop.com/on/demandware.store/Sites-gamestop-us-Site/default/"
APIS = [
    BASE + "Product-Variation?pid=20015604&quantity=1",
    BASE + "Product-Variation?dwvar_20015604_condition=New&pid=20015604&quantity=1",
    BASE + "Product-AvailabilityJson?pids=20015604",
]


def show(tag, r):
    t = r.text
    print(f"== {tag}: HTTP {r.status_code} len={len(t)} url={r.url}", flush=True)
    low = t.lower()
    for k in ("access denied", "captcha", "px-captcha", "_incapsula_", "cf-chl", "just a moment", "akamai",
              "bm-verify", "sec-if-cpt"):
        if k in low:
            print("   marker:", k)
    return t


for b in ["chrome", "chrome_android", "safari", "safari_ios", "firefox"]:
    try:
        s = http.Session(impersonate=b)
        r = s.get(PAGE, timeout=25)
        t = show(f"{b} page", r)
        if r.status_code == 200:
            for pat in [r'"availability"\s*:\s*"[^"]*"', r'data-gtmdata="[^"]{0,50}', r'"available"\s*:\s*\w+',
                        r'"readyToOrder"\s*:\s*\w+', r'add-to-cart[^>]{0,300}', r'(?i)not available[^<]{0,80}',
                        r'(?i)out of stock[^<]{0,80}', r'"productAvailability"[^}]{0,300}', r'"price"[^,]{0,60}',
                        r'(?i)"(?:sellable|isSellable|instock|inStock)"\s*:\s*\w+', r'schema.org/\w+',
                        r'data-ready-to-order="\w+"', r'data-available="\w+"']:
                for m in re.findall(pat, t)[:4]:
                    print("   ", pat[:30], "=>", m[:300])
            open(f"/tmp/gs_{b}.html", "w").write(t)
        else:
            print("   head:", re.sub(r"\s+", " ", t[:600]))
        time.sleep(3)
        for api in APIS:
            r = s.get(api, timeout=25, headers={"Referer": PAGE, "X-Requested-With": "XMLHttpRequest",
                                                 "Accept": "application/json, text/javascript, */*; q=0.01"})
            t = show(f"{b} api {api.split('/default/')[1][:60]}", r)
            try:
                d = json.loads(t)
                p = d.get("product") or {}
                print("   keys:", list(d)[:20])
                print("   product.availability:", json.dumps(p.get("availability"))[:800])
                for k in ("available", "readyToOrder", "orderable", "price", "productType", "id"):
                    print(f"   product.{k}:", json.dumps(p.get(k))[:400])
                for pat in [r'"[^"]*(?:[Aa]vail|[Ss]tock|[Oo]rderable|[Ss]ellable)[^"]*"\s*:\s*[^,]{0,80}']:
                    for m in sorted(set(re.findall(pat, t)))[:40]:
                        print("    field", m)
            except ValueError:
                print("   head:", re.sub(r"\s+", " ", t[:400]))
            time.sleep(2)
    except Exception as e:
        print(b, "error", e)
# Speed test: 12 page + api requests 5s apart on one session.
s = http.Session(impersonate="chrome")
for i in range(12):
    try:
        r1 = s.get(APIS[0] + f"&_={time.time_ns()}", timeout=20, headers={"Referer": PAGE})
        print(f"5s-loop {i}: api HTTP {r1.status_code} len={len(r1.text)}", flush=True)
    except Exception as e:
        print("5s-loop", i, e)
    time.sleep(5)
