"""Show where the stock status lives in the product page's data, and what the monitor reads from it."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import monitor


def paths(node, path=""):
    if isinstance(node, dict):
        if "availabilityStatus" in node:
            keys = [k for k in node if re.search(r"condition|offer|seller|price|availab|usItemId|name", k, re.I)]
            brief = {k: node[k] for k in keys if not isinstance(node[k], (dict, list))}
            print(f"{path}: {json.dumps(brief)[:400]}")
        for k, v in node.items():
            paths(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            paths(v, f"{path}[{i}]")


import time

m = None
for attempt in range(6):
    monitor._browser = attempt
    monitor.new_session()
    r = monitor._session.get(monitor.PRODUCT_URL, timeout=20, headers={"Referer": monitor.HOME_URL})
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    print(f"attempt {attempt} {monitor.BROWSERS[attempt % 2]}: HTTP {r.status_code} len={len(r.text)} "
          f"blocked={'robot or human' in r.text.lower()} next_data={bool(m)}", flush=True)
    if m:
        break
    time.sleep(10)
if not m:
    t = r.text
    for i in [x.start() for x in re.finditer("__NEXT_DATA__", t)][:3]:
        print("NEXT_DATA context:", repr(t[max(0, i - 200):i + 200]))
    for i in [x.start() for x in re.finditer("availabilityStatus", t)][:15]:
        print("avail context:", repr(t[max(0, i - 300):i + 80]))
    sys.exit("never parsed the product page")
data = json.loads(m.group(1))
paths(data)
for k in ("conditionGroupCode", "conditionCode", "variantCriteria", "allOffers", "conditionGroups"):
    for d in monitor.walk(data):
        if k in d:
            print(k, "=>", json.dumps(d[k])[:600])
            break
print("monitor.parse:", monitor.parse(r.text))
for _ in range(3):
    print("monitor.fetch:", monitor.fetch(), flush=True)
