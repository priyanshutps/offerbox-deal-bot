"""Amazon-style deal card generator (OfferBox Official).
usage: python3 card.py deal.json out.jpg
json keys: image, title, price, mrp, disc, delivery,
  optional: bought ("1K+ bought in past month"), badge ("Lowest price in 30 days"),
            replacement ("10 days Replacement"), coupon ("5%" or "₹188"),
            watermark (default "OfferBox Official")
"""
import sys, json, math, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter


FONT_NAMES = ["Inter-Regular.otf", "Inter-Medium.otf", "Inter-SemiBold.otf", "Inter-Bold.otf"]
INTER_ZIP = "https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip"


def ensure_fonts():
    """Return folder with Inter fonts; downloads them once if missing."""
    here = os.path.dirname(os.path.abspath(__file__))
    d = os.environ.get("FONT_DIR") or os.path.join(here, "fonts")
    if all(os.path.exists(os.path.join(d, n)) for n in FONT_NAMES):
        return d
    import io, zipfile, urllib.request
    os.makedirs(d, exist_ok=True)
    data = urllib.request.urlopen(INTER_ZIP, timeout=60).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in FONT_NAMES:
            open(os.path.join(d, n), "wb").write(z.read("extras/otf/" + n))
    return d


def render(d, out):
    S, W = 2, 1280
    F = ensure_fonts() + "/"
    def f(n, z): return ImageFont.truetype(F + n, z * S)
    s = lambda *v: tuple(int(x * S) for x in v)
    INK, GREY, RED, GREEN, TEAL, BLUE = (17,17,17), (110,110,110), (204,12,57), (0,118,0), (0,113,133), (30,110,200)
    x = 485

    # ---- flow layout (y = vertical centre of each row) ----
    rows, y = [], 0
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    tf = f("Inter-SemiBold.otf", 40)
    words, lines, cur = d["title"].split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if probe.textlength(t, font=tf) <= (1240 - x) * S: cur = t
        else: lines.append(cur); cur = w
    lines.append(cur)
    if len(lines) > 2:
        l2 = lines[1]
        while probe.textlength(l2 + "...", font=tf) > (1240 - x) * S: l2 = l2.rsplit(" ", 1)[0]
        lines = [lines[0], l2 + "..."]
    y = 64
    for l in lines: rows.append(("title", l, y)); y += 56
    if d.get("bought"): rows.append(("bought", d["bought"], y - 6)); y += 44
    y += 30; rows.append(("price", None, y)); y += 70
    rows.append(("mrp", None, y)); y += 50
    if d.get("badge"): y += 30; rows.append(("badge", d["badge"], y)); y += 60
    else: y += 6
    rows.append(("deliv", None, y)); y += 49
    rows.append(("stock", None, y)); y += 49
    if d.get("replacement"): rows.append(("repl", d["replacement"], y)); y += 49
    content_bottom = y - 20
    H = max(470, content_bottom + 30)
    if d.get("coupon"):
        cy0 = content_bottom + 30
        H = cy0 + 130

    img = Image.new("RGB", (W * S, H * S), (243, 244, 246))
    dr = ImageDraw.Draw(img)

    # product image
    p = Image.open(d["image"]).convert("RGB")
    p = p.crop(Image.eval(p, lambda v: 255 - v).point(lambda v: 255 if v > 10 else 0).getbbox() or (0, 0, *p.size))
    box = 400
    r = box * S / max(p.size); p = p.resize((int(p.width * r), int(p.height * r)), Image.LANCZOS)
    mask = p.convert("L").point(lambda v: 0 if v > 246 else 255).filter(ImageFilter.GaussianBlur(1.5 * S))
    img.paste(p, (int((40 + (box - p.width / S) / 2) * S), int((min(40, (H - box) / 2) + (box - p.height / S) / 2 + (0 if not d.get("coupon") else 0)) * S)), mask)

    # check box
    dr.rounded_rectangle(s(28, 28, 98, 98), radius=10 * S, fill=(25, 118, 210))
    dr.line([s(44, 64), s(58, 80), s(84, 46)], fill="white", width=7 * S, joint="curve")

    rf, bf = f("Inter-Regular.otf", 30), f("Inter-Bold.otf", 30)
    for kind, val, yy in rows:
        if kind == "title":
            dr.text(s(x, yy), val, font=tf, fill=INK, anchor="lm")
        elif kind == "bought":
            dr.text(s(x, yy), val, font=f("Inter-Regular.otf", 26), fill=INK, anchor="lm")
        elif kind == "price":
            df = f("Inter-Bold.otf", 40); dt = f"-{d['disc']}%"
            dw = dr.textlength(dt, font=df) / S
            dr.rounded_rectangle(s(x, yy - 34, x + dw + 34, yy + 33), radius=8 * S, fill=RED)
            dr.text(s(x + 17, yy), dt, font=df, fill="white", anchor="lm")
            rx = x + dw + 60
            dr.text(s(rx, yy - 22), "₹", font=f("Inter-Medium.otf", 30), fill=INK, anchor="lm")
            dr.text(s(rx + 22, yy), f"{int(d['price']):,}", font=f("Inter-Bold.otf", 70), fill=INK, anchor="lm")
            price_y = yy
        elif kind == "mrp":
            mt = f"M.R.P.: ₹{int(d['mrp']):,}"
            dr.text(s(x, yy), mt, font=f("Inter-Regular.otf", 28), fill=GREY, anchor="lm")
            dr.line([s(x, yy + 1), s(x + dr.textlength(mt, font=f("Inter-Regular.otf", 28)) / S, yy + 1)], fill=GREY, width=2 * S)
            mrp_y = yy
        elif kind == "badge":
            bt = val; bw = dr.textlength(bt, font=bf) / S
            dr.rounded_rectangle(s(x, yy - 35, x + bw + 60, yy + 35), radius=8 * S, fill=RED)
            dr.text(s(x + 30, yy), bt, font=bf, fill="white", anchor="lm")
        elif kind == "deliv":
            dr.text(s(x, yy), "FREE delivery ", font=rf, fill=INK, anchor="lm")
            dr.text(s(x + dr.textlength("FREE delivery ", font=rf) / S, yy), d["delivery"], font=bf, fill=INK, anchor="lm")
        elif kind == "stock":
            dr.text(s(x, yy), "In stock", font=rf, fill=GREEN, anchor="lm")
        elif kind == "repl":
            dr.text(s(x, yy), val, font=rf, fill=TEAL, anchor="lm")

    # coupon row
    if d.get("coupon"):
        c = str(d["coupon"]); c = c if c.startswith("₹") or c.endswith("%") else c + "%"
        t0, t1, mid = cy0 - 10, H - 26, (cy0 - 10 + H - 26) / 2
        dr.line([s(x, t0), s(1238, t0)], fill=(215, 215, 215), width=2 * S)
        dr.line([s(x, t1), s(1238, t1)], fill=(215, 215, 215), width=2 * S)
        dr.polygon([s(484, mid - 28), s(554, mid - 28), s(538, mid), s(554, mid + 28), s(484, mid + 28)], outline=(190, 190, 190), fill="white", width=2 * S)
        dr.text(s(511, mid), "₹", font=f("Inter-Bold.otf", 28), fill=(240, 140, 20), anchor="mm")
        dr.text(s(580, mid - 27), "Coupon Discount", font=f("Inter-SemiBold.otf", 32), fill=INK, anchor="lm")
        cf = f("Inter-Regular.otf", 32); ct = f"Save {c}"
        cw = dr.textlength(ct, font=cf) / S
        dr.rectangle(s(576, mid + 6, 576 + cw + 8, mid + 49), fill=(118, 214, 102))
        dr.text(s(580, mid + 27), ct, font=cf, fill=INK, anchor="lm")
        nx = 580 + cw + 18
        dr.text(s(nx, mid + 27), "now.", font=cf, fill=(80, 80, 80), anchor="lm")
        dr.text(s(nx + dr.textlength("now. ", font=cf) / S, mid + 27), "Details", font=cf, fill=BLUE, anchor="lm")
        dr.rounded_rectangle(s(1064, mid - 39, 1237, mid + 39), radius=14 * S, outline=(120, 120, 120), fill="white", width=2 * S)
        dr.text(s(1150, mid), "Apply", font=f("Inter-Medium.otf", 34), fill=INK, anchor="mm")
        ey0 = mid + 3
        pts = [((1-t)**2*78 + 2*(1-t)*t*170 + t*t*455, (1-t)**2*(ey0-30) + 2*(1-t)*t*(ey0+8) + t*t*ey0) for t in [i/60 for i in range(61)]]
        dr.line([s(*q) for q in pts], fill=(220, 30, 30), width=7 * S, joint="curve")
        ex, ey = pts[-1]; px2, py2 = pts[-6]; ang = math.atan2(ey - py2, ex - px2); L = 34
        dr.polygon([s(ex + 6*math.cos(ang), ey + 6*math.sin(ang)),
                    s(ex - L*math.cos(ang - .45), ey - L*math.sin(ang - .45)),
                    s(ex - L*math.cos(ang + .45), ey - L*math.sin(ang + .45))], fill=(220, 30, 30))

    # watermark: faint, between price and MRP (like the reference)
    wm = Image.new("RGBA", img.size, (0, 0, 0, 0))
    wd = ImageDraw.Draw(wm)
    wd.text(s(x + 230, (price_y + mrp_y) / 2 + 12), d.get("watermark", "OfferBox Official"),
            font=f("Inter-Bold.otf", 22), fill=(120, 120, 120, 95), anchor="lm")
    img = Image.alpha_composite(img.convert("RGBA"), wm).convert("RGB")

    img.resize((W, H), Image.LANCZOS).save(out, quality=95)
    return out


if __name__ == "__main__":
    render(json.load(open(sys.argv[1])), sys.argv[2])
