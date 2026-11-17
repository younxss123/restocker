"""Probe PlayStation Direct from a GitHub runner: what the PS5 Pro page and stock API return."""
import json
import re
import time

from curl_cffi import requests as http

PAGE = "https://direct.playstation.com/en-us/buy-consoles/playstation5-pro-console"
API = ("https://api.direct.playstation.com/commercewebservices/ps-direct-us/users/anonymous/products/"
       "productList?fields=BASIC&productCodes={}")


def show(label, r):
    t = r.text
    title = re.search(r"<title[^>]*>(.*?)</title>", t, re.S | re.I)
    print(f"== {label}: HTTP {r.status_code} len={len(t)} url={r.url} title={title.group(1).strip()[:100] if title else None}")
    for w in ["queue-it", "queueit", "akamai", "access denied", "px-captcha", "captcha", "outOfStock", "inStock",
              "out of stock", "add to cart", "stockLevelStatus", "sold out", "productCode", "data-product-code",
              "sku"]:
        n = t.lower().count(w.lower())
        if n:
            i = t.lower().find(w.lower())
            print(f"   {w!r} x{n}: {t[max(0, i - 150):i + 150]!r}")


codes = set()
for imp in ["chrome", "safari", "chrome_android", "safari_ios", "firefox"]:
    try:
        s = http.Session(impersonate=imp)
        r = s.get(PAGE, timeout=25)
        show(f"page {imp}", r)
        if r.status_code == 200 and len(r.text) > 5000:
            for pat in [r'data-product-code="(\w+)"', r'"productCode"\s*:\s*"(\w+)"', r'productCodes?=(\w+)',
                        r'"code"\s*:\s*"(\d{5,})"', r'data-sku="(\w+)"', r'"sku"\s*:\s*"(\w+)"']:
                found = set(re.findall(pat, r.text))
                if found:
                    print("   codes via", pat, found)
                    codes |= found
            open(f"page_{imp}.html", "w").write(r.text)
    except Exception as e:
        print(f"== page {imp}: error {e}")
    time.sleep(3)

print("codes:", codes)
for code in list(codes)[:6] + ["3006646", "1000044425", "1000044424"]:
    for imp in ["chrome", "safari_ios"]:
        try:
            r = http.get(API.format(code), impersonate=imp, timeout=20,
                         headers={"Origin": "https://direct.playstation.com", "Referer": PAGE})
            print(f"== api {code} {imp}: HTTP {r.status_code} {r.text[:600]!r}")
        except Exception as e:
            print(f"== api {code} {imp}: error {e}")
        time.sleep(1)

# 10-second cadence: does it keep answering?
s = http.Session(impersonate="chrome")
for i in range(12):
    try:
        r = s.get(PAGE + f"?_={int(time.time())}", timeout=20)
        print(f"burst {i}: HTTP {r.status_code} len={len(r.text)}", flush=True)
    except Exception as e:
        print(f"burst {i}: {e}")
    time.sleep(10)
