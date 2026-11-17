"""One-off probe: is Nintendo's store page cached, and what does the Zelda bundle's product record hold?"""
import json, re, time
from curl_cffi import requests as http

URL = "https://www.nintendo.com/us/store/products/nintendo-switch-2-the-legend-of-zelda-40th-anniversary-edition-121642/"
s = http.Session(impersonate="chrome")
for i, u in enumerate([URL, URL, URL + f"?_={int(time.time())}", URL + f"?_={int(time.time())+1}"]):
    r = s.get(u, timeout=20)
    hdr = {k: v for k, v in r.headers.items() if re.search(r"cache|age|date|etag|akamai|x-|cf-|server|vary|expires", k, re.I)}
    print(i, u[-20:], r.status_code, len(r.text), json.dumps(hdr))
    time.sleep(2)
m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
data = json.loads(m.group(1))
pp = data["props"]["pageProps"]
print("pageProps keys:", list(pp))
print("buildId:", data.get("buildId"), "isFallback:", data.get("isFallback"), "gssp:", data.get("gssp"), "isr?", data.get("autoExport"))
prod = pp["initialApolloState"].get('Product:{"sku":"121642"}')
print("PRODUCT 121642:", json.dumps(prod)[:4000])
print("linkedData:", json.dumps(pp.get("linkedData"))[:1500])
print("analytics:", json.dumps(pp.get("analytics"))[:800])
# graph endpoints / query names in page
for h in sorted(set(re.findall(r'https://[a-z0-9.-]*graph[a-z0-9.-]*[^"\s]{0,80}', r.text)))[:20]:
    print("graph url:", h)
for h in sorted(set(re.findall(r'/_next/static/chunks/[^"]+\.js', r.text)))[:80]:
    pass
# scan JS chunks for graph endpoint and stock query names
chunks = sorted(set(re.findall(r'/_next/static/[^"]+\.js', r.text)))
print("chunks:", len(chunks))
hits = set()
for c in chunks:
    try:
        js = s.get("https://www.nintendo.com" + c, timeout=20).text
    except Exception as e:
        continue
    for pat in [r'https://graph[a-z0-9.-]*nintendo[a-z0-9./-]*', r'isSalableQty[^;]{0,120}', r'sha256Hash["\']?\s*:\s*["\'][0-9a-f]{64}["\'][^;]{0,0}',
                r'operationName["\']?\s*:\s*["\'][A-Za-z]+', r'[A-Za-z]*(Inventory|Stock|Salable)[A-Za-z]*Query']:
        for x in re.findall(pat, js):
            x = x if isinstance(x, str) else x
            key = (c.split('/')[-1][:30], str(x)[:160])
            if str(x)[:160] not in {h[1] for h in hits}:
                hits.add(key)
for h in sorted(hits)[:120]:
    print("js:", h)
