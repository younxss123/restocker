"""One-off probe: fresh page vs cached page, and Nintendo's GraphQL API for live stock."""
import json, re, time
from curl_cffi import requests as http

SKU = "121642"
URL = f"https://www.nintendo.com/us/store/products/nintendo-switch-2-the-legend-of-zelda-40th-anniversary-edition-{SKU}/"
s = http.Session(impersonate="chrome")

def page_state(u):
    t = time.time()
    r = s.get(u, timeout=20)
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    pp = json.loads(m.group(1))["props"]["pageProps"]
    p = pp["initialApolloState"].get(f'Product:{{"sku":"{SKU}"}}', {})
    keep = {k: v for k, v in p.items() if not isinstance(v, (list, dict)) and not k.startswith("description")}
    return (f"HTTP {r.status_code} {time.time()-t:.2f}s age={r.headers.get('x-cache-age')} cache={r.headers.get('x-cache')} "
            f"linked={pp['linkedData'][0]['offers']['availability']} product={json.dumps(keep)[:1500]}")

print("cached :", page_state(URL))
print("fresh  :", page_state(URL + f"?q={time.time_ns()}"))

# Pull the GraphQL documents the site ships, to copy the product query.
r = s.get(URL + f"?q={time.time_ns()}", timeout=20)
app = [c for c in re.findall(r'/_next/static/[^"]+\.js', r.text) if "_app-" in c][0]
js = s.get("https://www.nintendo.com" + app, timeout=20).text
docs = re.findall(r'(?:query|fragment) [A-Za-z]+[^`"]{0,40}', js)
print("graphql docs:", sorted(set(d.split("(")[0].split("{")[0].strip() for d in docs))[:80])
for m in re.finditer(r'"((?:query|fragment) (?:Product|StoreProduct|ProductBySku|ProductsBySku|ProductInventory|Cart)[^"]{0,3000})"', js):
    print("DOC:", m.group(1)[:3000].replace("\\n", " "))

GQL = "https://graph.nintendo.com/"
q = """query P($sku: String!, $locale: Locale!) { product(sku: $sku, locale: $locale) { sku name isSalableQty soldOutPermanent
  isPreorderable inviteRequired prePurchase releaseDate maxQtyAllowedInCart qtyAllowedPerCustomer requiresLogin
  prices(personalized: false) { finalPrice regularPrice } } }"""
for prof in ["chrome", "safari_ios"]:
    for loc in ["en_US"]:
        try:
            t = time.time()
            rr = http.post(GQL, impersonate=prof, timeout=20, json={"query": q, "variables": {"sku": SKU, "locale": loc}},
                           headers={"Origin": "https://www.nintendo.com", "Referer": URL, "apollographql-client-name": "ncom"})
            print(f"graph POST {prof}: HTTP {rr.status_code} {time.time()-t:.2f}s {rr.text[:1500]}")
            print("   headers:", {k: v for k, v in rr.headers.items() if re.search('cache|age|x-', k, re.I)})
        except Exception as e:
            print("graph error", e)
