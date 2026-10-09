"""Fetch an Amazon.in / Flipkart / Myntra product page and extract deal-card fields."""
import re, json, time
from urllib.parse import urlparse
from curl_cffi import requests
from bs4 import BeautifulSoup

HDR = {"Accept-Language": "en-IN,en;q=0.9"}
MON = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"


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


def site_of(url):
    h = urlparse(url).netloc.lower()
    if "amazon." in h:
        return "amazon"
    if "flipkart." in h:
        return "flipkart"
    if "myntra." in h:
        return "myntra"
    return None


READY = {
    "amazon": lambda t: "productTitle" in t,
    "flipkart": lambda t: '"ppd"' in t or "og:title" in t,
    "myntra": lambda t: '"pdpData"' in t,
}


def _fetch(url, tries=4):
    last = None
    for i, imp in enumerate(["chrome", "chrome124", "safari", "chrome"][:tries]):
        try:
            r = requests.get(url, impersonate=imp, headers=HDR, timeout=30, allow_redirects=True)
            site = site_of(r.url)
            if site is None and r.status_code == 200:
                # some short links (affiliate converters) use a JS/meta redirect
                m = re.search(r'(?:url=|location\.href\s*=\s*["\']|href=["\'])(https?://[^"\'>\s]*(?:amazon|flipkart|myntra)[^"\'>\s]*)', r.text, re.I)
                if m:
                    r = requests.get(m.group(1).replace("&amp;", "&"), impersonate=imp, headers=HDR, timeout=30)
                    site = site_of(r.url)
            if site is None:
                raise RuntimeError("Only Amazon, Flipkart and Myntra links are supported.")
            if r.status_code == 200 and READY[site](r.text):
                return site, r
            last = f"status {r.status_code}"
        except RuntimeError:
            raise
        except Exception as e:
            last = str(e)
        time.sleep(2 + i * 2)
    raise RuntimeError(f"Page not readable ({last}). Try again in a minute.")


# ---------------- Amazon ----------------
def _amazon(r):
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
    m = re.search(r"FREE delivery\s+((?:\w+day,\s*)?\d{1,2}(?:\s*" + MON + r")?(?:\s*-\s*\d{1,2})?\s*" + MON + r"|Tomorrow|Today)", _txt(db))
    if m:
        deliv = short_date(m.group(1))

    bought = (re.search(r"[\d.]+K?\+ bought in past month", body) or [None])[0]
    cm = re.search(r"Apply\s+(₹\s?[\d,]+|\d+%)\s+coupon", body)
    rm = re.search(r"\b(\d+ days? (?:Replacement|Returnable))\b", body)
    return dict(title=title, price=price, mrp=mrp, disc=disc, image_url=img, delivery=deliv,
                bought=bought, coupon=cm.group(1).replace(" ", "") if cm else None,
                badge="Lowest price in 30 days" if "Lowest price in 30 days" in body else None,
                replacement=rm.group(1) if rm else None)


# ---------------- Flipkart ----------------
def _flipkart(r):
    t = r.text
    soup = BeautifulSoup(t, "html.parser")
    og = lambda p: (soup.find("meta", property=p) or {}).get("content", "")
    h1 = soup.find("h1")
    title = _txt(h1) or re.sub(r"\s+Price in India.*$", "", og("og:title"))
    img = og("og:image")
    for x in soup(["script", "style"]):
        x.decompose()
    body = soup.get_text("\n", strip=True)
    i = body.find(title) if title else -1
    after = body[i + len(title): i + len(title) + 3000] if i >= 0 else body

    price = mrp = disc = None
    m = re.search(r"(\d{1,2})%\n([\d,]+)\n₹([\d,]+)", after)
    if m:
        disc, mrp, price = int(m.group(1)), _num(m.group(2)), _num(m.group(3))
    else:  # fallback: page JSON
        pm = re.search(r'"ppd":\{[^}]*?"finalPrice":(\d+),"mrp":(\d+)', t)
        if pm:
            price, mrp = float(pm.group(1)), float(pm.group(2))
        else:
            pm = re.search(r"₹([\d,]+)", after)
            price = _num(pm.group(1)) if pm else None

    buy = re.search(r"Buy at ₹([\d,]+)", after)
    badge = None
    if buy and price and _num(buy.group(1)) < price:
        badge = f"Buy at ₹{int(_num(buy.group(1))):,} with offers"
    dm = re.search(r"Delivery by\n(.+)", after)
    rm = re.search(r"\b(\d+ Days? (?:Replacement|Return)[^\n]*)", after)
    return dict(title=title, price=price, mrp=mrp, disc=disc, image_url=img,
                delivery=short_date(dm.group(1)) if dm else "", bought=None, coupon=None,
                badge=badge, replacement=rm.group(1) if rm else None)


# ---------------- Myntra ----------------
def _myntra(r):
    m = re.search(r"window\.__myx\s*=\s*(\{.*?\})\s*</script>", r.text, re.S)
    d = json.loads(m.group(1))["pdpData"]
    brand = (d.get("brand") or {}).get("name", "")
    name = d.get("name", "")
    title = name if not brand or name.lower().startswith(brand.lower()) else f"{brand} {name}"
    pr = d.get("price") or {}
    mrp = pr.get("mrp") or d.get("mrp")
    price = pr.get("discounted") or mrp
    img = ""
    try:
        img = d["media"]["albums"][0]["images"][0]["imageURL"].replace("http://", "https://")
    except Exception:
        pass
    sizes = d.get("sizes") or []
    in_stock = any(s.get("available") for s in sizes) if sizes else True
    ret = (d.get("serviceability") or {}).get("returnPeriod")
    return dict(title=title, price=price, mrp=mrp, disc=None, image_url=img, delivery="",
                bought=None, coupon=None, badge=None,
                replacement=f"Easy {ret} days return & exchange" if ret else None, in_stock=in_stock)


def scrape(url):
    site, r = _fetch(url)
    d = {"amazon": _amazon, "flipkart": _flipkart, "myntra": _myntra}[site](r)
    price, mrp = d["price"], d["mrp"]
    if not price:
        raise RuntimeError("Couldn't read the price on this page.")
    if not mrp or mrp < price:
        mrp = price
    disc = d.get("disc") or (round((1 - price / mrp) * 100) if mrp > price else 0)
    d.update(url=r.url, site=site, price=int(price), mrp=int(mrp), disc=int(disc))
    d.setdefault("in_stock", True)
    return d


def download(url, path):
    r = requests.get(url, impersonate="chrome", timeout=30)
    open(path, "wb").write(r.content)
    return path


if __name__ == "__main__":
    import sys
    print(json.dumps(scrape(sys.argv[1]), indent=1, ensure_ascii=False))
