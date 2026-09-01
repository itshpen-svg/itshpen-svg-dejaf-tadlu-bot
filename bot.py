"""
Dejaf Tadlu - Telegram Ordering Bot
Browse catalog, cart, checkout. Order summary goes to shop owner.
"""

import os
from pathlib import Path
import asyncio
import logging
import uuid
from dotenv import load_dotenv

from aiohttp import web

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from products import PRODUCTS, CATEGORIES

# Payment on delivery only — no online payment gateway
HAS_CHAPA = False

load_dotenv()
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
OWNER_CHAT_ID = (os.getenv("OWNER_CHAT_ID") or "").strip()
VAT_RATE = 0.15
SHOP_NAME = "Dejaf Tadlu"
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://dejaf-tadlu-onlineshopping.netlify.app")
PHOTO_BASE_URL = (os.getenv("PHOTO_BASE_URL") or "https://raw.githubusercontent.com/itshpen-svg/dejaf-tadlu-bot/main/").rstrip("/") + "/"
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Folder where bot.py lives (photos/ is next to it on Render)
BASE_DIR = Path(__file__).resolve().parent


def is_photo_url(path_str):
    s = (path_str or "").strip().lower()
    return s.startswith("http://") or s.startswith("https://")


def resolve_photo(path_str):
    """Return Path to a local photo file, or None. URLs are handled separately."""
    if not path_str or is_photo_url(path_str):
        return None
    candidates = []
    p = Path(path_str)
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(BASE_DIR / p)
        candidates.append(BASE_DIR / "photos" / p.name)
        candidates.append(Path.cwd() / p)
        candidates.append(Path.cwd() / "photos" / p.name)
        # Render sometimes uses /opt/render/project/src
        candidates.append(Path("/opt/render/project/src") / p)
        candidates.append(Path("/opt/render/project/src/photos") / p.name)
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


async def send_product_photo(context, chat_id, product):
    """Send one product photo (local file or public URL) with Add button."""
    raw = (product.get("photo") or "").strip()
    caption = safe_text(product.get("name"), "Product") + chr(10) + fmt_etb(unit_price(product))
    markup = product_photo_keyboard(product)

    async def _send(photo_src):
        await context.bot.send_photo(
            chat_id=chat_id, photo=photo_src, caption=caption, reply_markup=markup
        )

    try:
        if is_photo_url(raw):
            await _send(raw)
            return True

        path = resolve_photo(raw)
        if path:
            with open(path, "rb") as photo_file:
                await _send(photo_file)
            return True

        if raw:
            url = PHOTO_BASE_URL + raw.lstrip("/")
            logger.info("Trying photo URL for id=%s: %s", product.get("id"), url)
            await _send(url)
            return True

        logger.error("No photo path for id=%s", product.get("id"))
        return False
    except Exception as e:
        logger.error("send_product_photo failed id=%s raw=%s: %s", product.get("id"), raw, e)
        return False




def fmt_etb(amount):
    return "ETB {:,.2f}".format(amount)


def unit_price(product):
    return product["sale"] if product["sale"] is not None else product["price"]


def cart_lines(chat_id):
    cart = carts.get(chat_id, {})
    lines = []
    for pid, qty in cart.items():
        p = PRODUCTS_BY_ID.get(pid)
        if not p or qty <= 0:
            continue
        price = unit_price(p)
        lines.append({"product": p, "qty": qty, "unit": price, "line_total": price * qty})
    return lines


def cart_totals(chat_id):
    lines = cart_lines(chat_id)
    subtotal = sum(l["line_total"] for l in lines)
    vat = subtotal * VAT_RATE
    total = subtotal + vat
    return subtotal, vat, total


def main_menu_keyboard(chat_id=None):
    buttons = [
        [InlineKeyboardButton("🛍 Browse Categories", callback_data="menu:categories")],
        [InlineKeyboardButton("🥬 Weekly Asbeza", callback_data="menu:asbeza")],
        [InlineKeyboardButton("🛒 View Cart", callback_data="menu:cart")],
    ]
    if chat_id is not None and cart_lines(chat_id):
        buttons.append([InlineKeyboardButton("✅ Checkout", callback_data="checkout:start")])
        buttons.append([InlineKeyboardButton("🗑 Clear Cart", callback_data="cart:clear")])
    buttons.append([InlineKeyboardButton("🌐 Visit Our Website", url=WEBSITE_URL)])
    return InlineKeyboardMarkup(buttons)


def categories_keyboard():
    buttons = []
    row = []
    for i, cat in enumerate(CATEGORIES, 1):
        row.append(InlineKeyboardButton(cat, callback_data="cat:" + cat))
        if i % 2 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅ Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def safe_text(value, fallback="…"):
    """Telegram rejects empty message text/captions."""
    s = (value or "").strip()
    return s if s else fallback


def photo_products_in(cat):

    return [p for p in PRODUCTS if p["cat"] == cat and p.get("photo")]


def text_products_in(cat):
    return [
        p for p in PRODUCTS
        if p["cat"] == cat and not p.get("photo") and not p.get("builder")
    ]


def products_keyboard(cat):
    buttons = []
    for p in text_products_in(cat):
        price = unit_price(p)
        label = p["name"] + " - " + fmt_etb(price)
        buttons.append([InlineKeyboardButton(label, callback_data="add:" + str(p["id"]))])
    buttons.append([InlineKeyboardButton("⬅ Categories", callback_data="menu:categories")])
    return InlineKeyboardMarkup(buttons)


def product_photo_keyboard(product):
    price = unit_price(product)
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Add - " + fmt_etb(price), callback_data="add:" + str(product["id"]))]]
    )


def cart_keyboard(chat_id):
    buttons = []
    for line in cart_lines(chat_id):
        pid = line["product"]["id"]
        name = line["product"]["name"]
        short = name if len(name) <= 22 else name[:20] + ".."
        buttons.append(
            [
                InlineKeyboardButton("-", callback_data="dec:" + str(pid)),
                InlineKeyboardButton(short + " x" + str(line["qty"]), callback_data="noop"),
                InlineKeyboardButton("+", callback_data="inc:" + str(pid)),
            ]
        )
    if cart_lines(chat_id):
        buttons.append([InlineKeyboardButton("✅ Checkout", callback_data="checkout:start")])
        buttons.append([InlineKeyboardButton("🗑 Clear Cart", callback_data="cart:clear")])
    buttons.append([InlineKeyboardButton("🌐 Visit Our Website", url=WEBSITE_URL)])
    buttons.append([InlineKeyboardButton("⬅ Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def cart_text(chat_id):
    lines = cart_lines(chat_id)
    if not lines:
        return "Your cart is empty. Browse the catalog to add something!"
    parts = ["Your Cart", ""]
    for l in lines:
        parts.append(
            str(l["qty"]) + " x " + l["product"]["name"] + " - " + fmt_etb(l["line_total"])
        )
    subtotal, vat, total = cart_totals(chat_id)
    parts.append("")
    parts.append("Subtotal: " + fmt_etb(subtotal))
    parts.append("VAT (15%): " + fmt_etb(vat))
    parts.append("Total: " + fmt_etb(total))
    return "\n".join(parts)


async def send_cart_photo_album(context, chat_id):
    lines = cart_lines(chat_id)
    photo_lines = [l for l in lines if l["product"].get("photo")]
    if not photo_lines:
        return
    media = []
    opened = []
    try:
        for l in photo_lines[:10]:
            path = resolve_photo(l["product"].get("photo"))
            if not path:
                logger.error("Missing photo for cart item: %s", l["product"].get("photo"))
                continue
            try:
                f = open(path, "rb")
            except OSError as e:
                logger.error("Missing photo: %s (%s)", path, e)
                continue
            opened.append(f)
            media.append(InputMediaPhoto(f, caption=l["product"]["name"] + " x" + str(l["qty"])))
        if len(media) == 1:
            await context.bot.send_photo(chat_id=chat_id, photo=media[0].media, caption=media[0].caption)
        elif len(media) >= 2:
            await context.bot.send_media_group(chat_id=chat_id, media=media)
    finally:
        for f in opened:
            f.close()


async def start(update, context):
    chat_id = update.effective_chat.id
    payload = context.args[0] if context.args else None
    loaded = 0
    skipped = False

    if payload:
        carts.setdefault(chat_id, {})
        for part in payload.split("-"):
            try:
                pid_str, qty_str = part.split("_")
                pid, qty = int(pid_str), int(qty_str)
            except (ValueError, IndexError):
                skipped = True
                continue
            p = PRODUCTS_BY_ID.get(pid)
            if not p or qty <= 0 or p.get("builder"):
                skipped = True
                continue
            carts[chat_id][pid] = carts[chat_id].get(pid, 0) + qty
            loaded += 1

    if loaded > 0:
        note = ""
        if skipped:
            note = "\n\nSome items could not be loaded. Please re-add anything missing."
        await update.message.reply_text(
            "Selam! Welcome to " + SHOP_NAME + "\n\n"
            "We loaded " + str(loaded) + " item(s) from your website cart." + note + "\n\n"
            "Review it below, then checkout when ready."
        )
        await update.message.reply_text(cart_text(chat_id), reply_markup=cart_keyboard(chat_id))
        return

    await update.message.reply_text(
        "Selam! Welcome to " + SHOP_NAME + "\n\n"
        "Browse our catalog and order right here in Telegram.\n\n"
        "Try Weekly Asbeza - build a vegetable basket from Grocery.\n"
        "Payment: Cash on Delivery (pay when you receive your order)",
        reply_markup=main_menu_keyboard(chat_id),
    )


async def myid(update, context):
    await update.message.reply_text(
        "Your chat ID is: " + str(update.effective_chat.id) + "\n\n"
        "If you are the shop owner, put this in .env as OWNER_CHAT_ID and restart."
    )



async def photos_debug(update, context):
    """Owner can run /photos to see if image files are on the server."""
    photos_dir = BASE_DIR / "photos"
    lines = [
        "Photo debug",
        "BASE_DIR: " + str(BASE_DIR),
        "cwd: " + str(Path.cwd()),
        "photos dir exists: " + str(photos_dir.is_dir()),
    ]
    if photos_dir.is_dir():
        files = sorted(list(photos_dir.glob("*.jpg")) + list(photos_dir.glob("*.jpeg")) + list(photos_dir.glob("*.png")))
        lines.append("image count: " + str(len(files)))
        lines.append("sample: " + ", ".join(f.name for f in files[:15]))
    else:
        top = list(BASE_DIR.iterdir())[:30]
        lines.append("top files: " + ", ".join(p.name for p in top))
    with_photo = [p for p in PRODUCTS if p.get("photo")]
    lines.append("products with photo field: " + str(len(with_photo)))
    await update.message.reply_text(chr(10).join(lines)[:3500])



async def cancel(update, context):
    chat_id = update.effective_chat.id
    if checkout_state.pop(chat_id, None) is not None:
        await update.message.reply_text("Checkout cancelled.", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(
        "What would you like to do?", reply_markup=main_menu_keyboard(chat_id)
    )


async def show_grocery_asbeza(context, chat_id, edit_query=None):
    tip = (
        "Weekly Asbeza\n\n"
        "Add vegetables and staples from the list below.\n"
        "Your cart total updates as you add.\n\n"
        "Payment: Cash on Delivery (pay when you receive your order)"
    )
    if edit_query:
        await edit_query.edit_message_text(tip, reply_markup=products_keyboard("Grocery"))
    else:
        await context.bot.send_message(
            chat_id=chat_id, text=tip, reply_markup=products_keyboard("Grocery")
        )
    for p in photo_products_in("Grocery"):
        ok = await send_product_photo(context, chat_id, p)
        if not ok:
            await context.bot.send_message(
                chat_id=chat_id,
                text=safe_text(p.get("name"), "Product") + " - " + fmt_etb(unit_price(p)),
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Add", callback_data="add:" + str(p["id"]))]]
                ),
            )


async def on_button(update, context):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data or ""

    if data == "noop":
        return

    if data == "menu:main":
        await query.edit_message_text(
            SHOP_NAME + "\n\nWhat would you like to do?",
            reply_markup=main_menu_keyboard(chat_id),
        )
        return

    if data == "menu:categories":
        await query.edit_message_text("Choose a department:", reply_markup=categories_keyboard())
        return

    if data == "menu:asbeza":
        await show_grocery_asbeza(context, chat_id, edit_query=query)
        return

    if data.startswith("cat:"):
        cat = data.split(":", 1)[1].strip()
        if not cat:
            await query.edit_message_text(
                "Choose a department:",
                reply_markup=categories_keyboard(),
            )
            return
        photo_items = photo_products_in(cat)
        text_items = text_products_in(cat)
        header = safe_text(cat, "Products")
        if text_items or not photo_items:
            await query.edit_message_text(
                header,
                reply_markup=products_keyboard(cat),
            )
        else:
            await query.edit_message_text(
                header + "\n\nPhotos of items in this department:"
            )
        for p in photo_items:
            ok = await send_product_photo(context, chat_id, p)
            if not ok:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=safe_text(p.get("name"), "Product") + " - " + fmt_etb(unit_price(p)),
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("Add", callback_data="add:" + str(p["id"]))]]
                    ),
                )
        if photo_items:
            await context.bot.send_message(
                chat_id=chat_id,
                text="That's everything in this department.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅ Categories", callback_data="menu:categories")]]
                ),
            )
        return

    if data.startswith("add:"):
        pid = int(data.split(":", 1)[1])
        p = PRODUCTS_BY_ID.get(pid)
        if p and p.get("builder"):
            await show_grocery_asbeza(context, chat_id)
            return
        carts.setdefault(chat_id, {})
        carts[chat_id][pid] = carts[chat_id].get(pid, 0) + 1
        await query.answer(text="Added to cart", show_alert=False)
        return

    if data.startswith("inc:"):
        pid = int(data.split(":", 1)[1])
        carts.setdefault(chat_id, {})
        carts[chat_id][pid] = carts[chat_id].get(pid, 0) + 1
        await query.edit_message_text(cart_text(chat_id), reply_markup=cart_keyboard(chat_id))
        return

    if data.startswith("dec:"):
        pid = int(data.split(":", 1)[1])
        if chat_id in carts and pid in carts[chat_id]:
            carts[chat_id][pid] -= 1
            if carts[chat_id][pid] <= 0:
                del carts[chat_id][pid]
        await query.edit_message_text(cart_text(chat_id), reply_markup=cart_keyboard(chat_id))
        return

    if data == "cart:clear":
        carts[chat_id] = {}
        await query.edit_message_text(
            "Cart cleared.\n\nWhat would you like to do?",
            reply_markup=main_menu_keyboard(chat_id),
        )
        return

    if data == "menu:cart":
        if not cart_lines(chat_id):
            await query.edit_message_text("Your cart is empty.", reply_markup=cart_keyboard(chat_id))
            return
        await query.edit_message_text(cart_text(chat_id), reply_markup=cart_keyboard(chat_id))
        await send_cart_photo_album(context, chat_id)
        return

    if data == "checkout:start":
        if not cart_lines(chat_id):
            await query.edit_message_text(
                "Your cart is empty.", reply_markup=main_menu_keyboard(chat_id)
            )
            return
        checkout_state[chat_id] = {"stage": "name"}
        await query.edit_message_text("Checkout\n\nPlease send your full name.")
        return


async def on_text(update, context):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()
    state = checkout_state.get(chat_id)
    if not state:
        await update.message.reply_text(
            "Use the menu buttons to browse and order.",
            reply_markup=main_menu_keyboard(chat_id),
        )
        return

    if state.get("stage") == "name":
        state["name"] = text
        state["stage"] = "address"
        loc_kb = ReplyKeyboardMarkup(
            [
                [KeyboardButton("📍 Share my location", request_location=True)],
                [KeyboardButton("Skip — type address instead")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await update.message.reply_text(
            "Thanks, " + text + ".\n\n"
            "Send your delivery address in Addis Ababa,\n"
            "or tap 📍 Share my location.",
            reply_markup=loc_kb,
        )
        return

    if state.get("stage") == "address":
        if text.startswith("Skip"):
            await update.message.reply_text(
                "Please type your delivery address in Addis Ababa.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        state["address"] = text
        state["stage"] = "contact"
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Share my phone number", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await update.message.reply_text(
            "Please share your phone number (or type it).",
            reply_markup=kb,
        )
        return

    if state.get("stage") == "contact":
        state["contact"] = text
        await finish_checkout(update, context, chat_id)
        return



async def on_location(update, context):
    chat_id = update.effective_chat.id
    state = checkout_state.get(chat_id)
    if not state or state.get("stage") != "address":
        return
    loc = update.message.location
    if not loc:
        await update.message.reply_text("Could not read location. Please type your address.")
        return
    state["address"] = (
        "Location: "
        + str(round(loc.latitude, 6))
        + ", "
        + str(round(loc.longitude, 6))
        + " (map pin from customer)"
    )
    state["stage"] = "contact"
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("Share my phone number", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(
        "Location saved. Please share your phone number (or type it).",
        reply_markup=kb,
    )


async def on_contact(update, context):
    chat_id = update.effective_chat.id
    state = checkout_state.get(chat_id)
    if not state or state.get("stage") != "contact":
        return
    contact = update.message.contact
    state["contact"] = contact.phone_number if contact else "unknown"
    await finish_checkout(update, context, chat_id)


async def finish_checkout(update, context, chat_id):
    state = checkout_state.pop(chat_id, {})
    lines = cart_lines(chat_id)
    if not lines:
        await update.message.reply_text("Your cart is empty.", reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text(
            "What would you like to do?", reply_markup=main_menu_keyboard(chat_id)
        )
        return

    subtotal, vat, total = cart_totals(chat_id)
    name = state.get("name", "-")
    address = state.get("address", "-")
    contact = state.get("contact", "-")
    order_id = "DJT-" + uuid.uuid4().hex[:8].upper()

    summary_lines = [
        str(l["qty"]) + " x " + l["product"]["name"] + " - " + fmt_etb(l["line_total"])
        for l in lines
    ]
    summary = (
        "Order " + order_id + "\n"
        "Customer: " + name + "\n"
        "Phone: " + str(contact) + "\n"
        "Address: " + address + "\n\n"
        + "\n".join(summary_lines)
        + "\n\nSubtotal: " + fmt_etb(subtotal)
        + "\nVAT (15%): " + fmt_etb(vat)
        + "\nTotal: " + fmt_etb(total)
        + "\n\nPayment: Cash on Delivery (pay when you receive)"
    )

    # Notify shop owner (must be set on Render as OWNER_CHAT_ID)
    if not OWNER_CHAT_ID:
        logger.error(
            "OWNER_CHAT_ID is not set — order %s will NOT be sent to the owner. "
            "Open the bot, send /myid, and put that number in Render Environment.",
            order_id,
        )
    else:
        try:
            owner_id = int(OWNER_CHAT_ID)
            await context.bot.send_message(
                chat_id=owner_id,
                text="NEW ORDER\n\n" + summary,
            )
            logger.info("Owner notified for order %s -> chat %s", order_id, owner_id)
        except Exception as e:
            logger.error(
                "Failed to notify owner (OWNER_CHAT_ID=%s) for order %s: %s",
                OWNER_CHAT_ID,
                order_id,
                e,
            )

    carts[chat_id] = {}
    await update.message.reply_text("Order received. Thank you!", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(
        "We got your order (" + order_id + ").\n"
        "Payment: Cash on Delivery — pay when your order arrives.\nWe will call/message you to confirm delivery.\n\n" + summary,
        reply_markup=main_menu_keyboard(chat_id),
    )


async def health(request):
    return web.Response(text="Dejaf Tadlu bot is running.")


async def post_init(application):
    """HTTP health endpoint so Render sees an open port."""
    aio = web.Application()
    aio.router.add_get("/", health)
    aio.router.add_get("/health", health)
    runner = web.AppRunner(aio)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    try:
        await site.start()
        logger.info("Health server on port %s", PORT)
    except OSError as e:
        logger.warning("Health server not started: %s", e)


def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN is not set. Add BOT_TOKEN in Render Environment.")
        raise SystemExit(1)

    if OWNER_CHAT_ID:
        logger.info("Owner notifications enabled -> OWNER_CHAT_ID=%s", OWNER_CHAT_ID)
    else:
        logger.warning(
            "OWNER_CHAT_ID is empty — you will NOT receive NEW ORDER messages. "
            "Set it on Render from /myid."
        )

    # Python 3.12+ / 3.14 on Render: create a main-thread event loop first
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myid", myid))
    application.add_handler(CommandHandler("photos", photos_debug))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(on_button))
    application.add_handler(MessageHandler(filters.CONTACT, on_contact))
    application.add_handler(MessageHandler(filters.LOCATION, on_location))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    photos_dir = BASE_DIR / "photos"
    n_photos = len(list(photos_dir.glob("*.jpg"))) if photos_dir.is_dir() else 0
    logger.info("Photo folder: %s (%s jpg files)", photos_dir, n_photos)
    if n_photos == 0:
        logger.warning("No photos/*.jpg found — Telegram will not show product images")
    logger.info("Starting bot (polling)...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        close_loop=False,
    )


if __name__ == "__main__":
    main()
