"""Try several ways of fetching the product page and report which get past Walmart's bot check."""
import re
import time
from curl_cffi import requests

ITEM = "18235967161"
URLS = {
    "business": f"https://business.walmart.com/ip/Sony-PlayStation-5-Pro-Console-PS5-Pro/{ITEM}?conditionCode=1",
    "www": f"https://www.walmart.com/ip/Sony-PlayStation-5-Pro-Console-PS5-Pro/{ITEM}",
}
BROWSERS = ["chrome", "safari", "chrome_android", "safari_ios", "firefox", "edge"]


def summarize(r):
    t = r.text
    blocked = "robot or human" in t.lower() or "px-captcha" in t.lower()
    has_next = "__NEXT_DATA__" in t
    avail = sorted(set(re.findall(r'"availabilityStatus":"([A-Z_]+)"', t)))
    cond = sorted(set(re.findall(r'"condition(?:Type|Name)?":"([^"]{1,30})"', t)))[:8]
    return f"HTTP {r.status_code} len={len(t)} blocked={blocked} next_data={has_next} avail={avail} cond={cond}"


for name, url in URLS.items():
    for b in BROWSERS:
        try:
            s = requests.Session(impersonate=b)
            home = url.split("/ip/")[0] + "/"
            s.get(home, timeout=20)  # warm up cookies like a real visit
            time.sleep(2)
            r = s.get(url, timeout=20, headers={"Referer": home})
            print(f"{name:9} {b:15} {summarize(r)}", flush=True)
        except Exception as e:
            print(f"{name:9} {b:15} error {e}", flush=True)
        time.sleep(3)
