"""Fetch an Amazon.in product page and extract deal-card fields."""
import re, datetime
from curl_cffi import requests
from bs4 import BeautifulSoup

HDR = {"Accept-Language": "en-IN,en;q=0.9"}


def _num(t):
    m = re.search(r"[\d,]+(?:\.\d+)?", t or "")
    return float(m.group().replace(",", "")) if m else None


def _txt(el):
    return el.get_text(" ", strip=True) if el else ""


def short_date(s):
    """'Friday, 16 October' -> 'Fri, 16 Oct'; ranges like '11 - 31 October' -> '11 - 31 Oct'."""
    s = s.strip().rstrip(".")
    for full in ["January", "February", "March", "April", "May", "June", "July", "August",
                 "September", "October", "November", "December"]:
        s = s.replace(full, full[:3])
    for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
        s = s.replace(day, day[:3])
    return s


def _fetch(url, tries=4):
    import time
    last = None
    for i, imp in enumerate(["chrome", "chrome124", "safari", "chrome"][:tries]):
        try:
            r = requests.get(url, impersonate=imp, headers=HDR, timeout=30, allow_redirects=True)
            if r.status_code == 200 and "productTitle" in r.text:
                return r
            last = f"status {r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(2 + i * 2)
    raise RuntimeError(f"Amazon page not readable ({last}). Try again in a minute.")


def scrape(url):
    r = _fetch(url)
    soup = BeautifulSoup(r.text, "html.parser")
    body = soup.get_text("\n", strip=True)

    title = _txt(soup.select_one("#productTitle"))
    core = soup.select_one("#corePriceDisplay_desktop_feature_div") or soup.select_one("#apex_desktop") or soup

    price = _num(_txt(core.select_one(".priceToPay .a-offscreen")) or _txt(core.select_one(".a-price .a-offscreen")))
    if not price:
        price = _num(_txt(core.select_one(".a-price-whole")))
    mrp = None
    for el in core.select(".basisPrice .a-offscreen, .a-text-price .a-offscreen"):
        v = _num(_txt(el))
        if v and price and v > price:
            mrp = v
            break
    disc = _num(_txt(core.select_one(".savingsPercentage")))
    if not disc and mrp and price:
        disc = round((1 - price / mrp) * 100)
    if not mrp:
        mrp = price
        disc = 0

    img_el = soup.select_one("#landingImage")
    img = ""
    if img_el:
        img = img_el.get("data-old-hires") or ""
        if not img and img_el.get("data-a-dynamic-image"):
            img = re.findall(r'"(https://[^"]+)"', img_el["data-a-dynamic-image"])[-1]
        img = img or img_el.get("src", "")
    img = re.sub(r"\._[A-Z0-9_,]+_\.", "._SL1500_.", img)

    deliv = ""
    db = soup.select_one("#mir-layout-DELIVERY_BLOCK") or soup.select_one("#deliveryBlockMessage")
    MON = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    m = re.search(r"FREE delivery\s+((?:\w+day,\s*)?\d{1,2}(?:\s*" + MON + r")?(?:\s*-\s*\d{1,2})?\s*" + MON + r"|Tomorrow|Today)", _txt(db))
    if m:
        deliv = short_date(m.group(1))

    stock = _txt(soup.select_one("#availability"))
    bought = (re.search(r"[\d.]+K?\+ bought in past month", body) or [None])[0]
    cm = re.search(r"Apply\s+(₹\s?[\d,]+|\d+%)\s+coupon", body)
    coupon = cm.group(1).replace(" ", "") if cm else None
    badge = "Lowest price in 30 days" if "Lowest price in 30 days" in body else None
    rm = re.search(r"\b(\d+ days? (?:Replacement|Returnable))\b", body)

    return {
        "url": r.url, "title": title, "price": int(price), "mrp": int(mrp), "disc": int(disc or 0),
        "image_url": img, "delivery": deliv or "Free", "in_stock": (not stock) or "unavailable" not in stock.lower(),
        "bought": bought, "coupon": coupon, "badge": badge, "replacement": rm.group(1) if rm else None,
    }


def download(url, path):
    r = requests.get(url, impersonate="chrome", timeout=30)
    open(path, "wb").write(r.content)
    return path


if __name__ == "__main__":
    import sys, json
    print(json.dumps(scrape(sys.argv[1]), indent=1, ensure_ascii=False))
