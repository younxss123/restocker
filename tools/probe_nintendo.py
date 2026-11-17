"""One-off probe: what does Nintendo's store page show a GitHub runner, and where is the stock status?"""
import json, re, sys, time
from curl_cffi import requests as http

URL = "https://www.nintendo.com/us/store/products/nintendo-switch-2-the-legend-of-zelda-40th-anniversary-edition-121642/"
PAT = re.compile(r"stock|avail|salab|sales|purchas|cart|sku|nsuid|order|release|status|price|restrict|inventory|qty|limit", re.I)

def walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}"
            if PAT.search(k) and not isinstance(v, (dict, list)):
                yield p, v
            yield from walk(v, p)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")

best = None
for prof in ["chrome", "safari", "chrome_android", "safari_ios", "firefox"]:
    try:
        t = time.time()
        r = http.get(URL, impersonate=prof, timeout=20)
        m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        print(f"{prof}: HTTP {r.status_code} len={len(r.text)} {time.time()-t:.2f}s next_data={bool(m)} final={r.url}", flush=True)
        if m and not best:
            best = (r, m)
        if not m:
            print("  head:", repr(r.text[:300]))
    except Exception as e:
        print(f"{prof}: error {e}")
if not best:
    sys.exit("no __NEXT_DATA__")
r, m = best
data = json.loads(m.group(1))
seen = set()
for p, v in walk(data):
    short = re.sub(r"\[\d+\]", "[]", p)
    key = (short, str(v)[:80])
    if key in seen: continue
    seen.add(key)
    print(f"{p} = {str(v)[:160]!r}")
for word in ["Add to cart", "Out of stock", "Sold out", "Coming soon", "Notify me", "Currently unavailable", "Pre-order", "Not available"]:
    print(f"text {word!r}: {r.text.lower().count(word.lower())}")
# Look for graph API / apollo hints
for h in sorted(set(re.findall(r'https://[a-z0-9.-]*nintendo[a-z0-9.-]*/[a-zA-Z0-9_/.-]{0,60}', r.text)))[:40]:
    print("url:", h)
