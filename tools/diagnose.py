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


monitor.new_session()
r = monitor._session.get(monitor.PRODUCT_URL, timeout=20, headers={"Referer": monitor.HOME_URL})
m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
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
