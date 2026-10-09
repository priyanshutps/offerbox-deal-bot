"""OfferBox deal-card Telegram bot.
Send it one or more Amazon links -> it replies with a deal card image + ready-to-post caption.

Env vars:
  BOT_TOKEN    token from @BotFather (required)
  ALLOWED_IDS  comma-separated Telegram user IDs allowed to use the bot (recommended)
"""
import os, re, asyncio, logging, tempfile
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

from scrape import scrape, download
from card import render, ensure_fonts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("offerbox")

TOKEN = os.environ["BOT_TOKEN"]
ALLOWED = {int(x) for x in os.environ.get("ALLOWED_IDS", "").replace(" ", "").split(",") if x}
LINK_RE = re.compile(r"https?://(?:www\.)?(?:amzn\.to|amzn\.in|amazon\.in|a\.co)/\S+", re.I)


def short_title(t, max_words=7):
    t = re.split(r"\s[|–—-]\s|,|\(|\bwith\b", t)[0].strip()
    w = t.split()
    return " ".join(w[:max_words])


def caption(d, link):
    head = f"{short_title(d['title'])} @{d['price']}."
    if d.get("coupon"):
        c = d["coupon"]
        tail = f"Apply {c} Off Coupon : {link}"
    else:
        tail = link
    return f"{head}\n\n{tail}"


def make_card(link, workdir):
    d = scrape(link)
    if not d["image_url"]:
        raise RuntimeError("Couldn't find product image")
    img = download(d["image_url"], os.path.join(workdir, "p.jpg"))
    card_data = {
        "image": img, "title": d["title"], "price": d["price"], "mrp": d["mrp"], "disc": d["disc"],
        "delivery": d["delivery"], "bought": d["bought"], "badge": d["badge"],
        "replacement": d["replacement"], "coupon": d["coupon"],
    }
    out = render(card_data, os.path.join(workdir, "card.jpg"))
    return out, caption(d, link)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Send me Amazon links and I'll make OfferBox deal cards.\nYour user ID: {update.effective_user.id}")


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if ALLOWED and uid not in ALLOWED:
        return
    text = update.message.text or update.message.caption or ""
    links = LINK_RE.findall(text)
    if not links:
        await update.message.reply_text("Amazon link bhejo (amzn.to / amazon.in).")
        return
    for link in links:
        link = link.rstrip(").,")
        msg = await update.message.reply_text(f"⏳ Generating… {link}")
        try:
            with tempfile.TemporaryDirectory() as wd:
                path, cap = await asyncio.to_thread(make_card, link, wd)
                with open(path, "rb") as fh:
                    await update.message.reply_photo(fh, caption=cap)
            await msg.delete()
        except Exception as e:
            log.exception("failed for %s", link)
            await msg.edit_text(f"❌ {link}\n{e}")


def main():
    ensure_fonts()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler(["start", "id"], start))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, on_message))
    log.info("Bot running…")
    app.run_polling()


if __name__ == "__main__":
    main()
