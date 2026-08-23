"""
Dejaf Tadlu — Telegram Ordering Bot
====================================
Lets customers browse the catalog, build a cart, and check out inside Telegram.
On checkout, a full order summary (items, quantities, subtotal, VAT, total,
customer name + address) is sent straight to the shop owner's Telegram chat.

Setup instructions are in README.md. Short version:
    1. pip install -r requirements.txt
    2. Copy .env.example to .env and fill in BOT_TOKEN (and later OWNER_CHAT_ID)
    3. python bot.py
"""

import os
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
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from products import PRODUCTS, CATEGORIES
from payments import initialize_payment, verify_payment, payment_succeeded, ChapaError

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")  # can be blank until you run /myid once
VAT_RATE = 0.15
SHOP_NAME = "Dejaf Tadlu (ደጃፍ - ታደሉ)"
# Update this once you know your final Netlify (or custom domain) link.
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://dejaf-tadlu-onlineshopping.netlify.app")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

PRODUCTS_BY_ID = {p["id"]: p for p in PRODUCTS}

# In-memory storage. Resets if the bot restarts.
# carts:    {chat_id: {product_id: qty}}
# checkout: {chat_id: {"stage": "name"|"address", "name": str}}
carts: dict[int, dict[int, int]] = {}
checkout_state: dict[int, dict] = {}

# pending_orders: {tx_ref: {chat_id, lines, subtotal, vat, total, name, address, contact, status}}
# status is "pending" until Chapa confirms payment, then "paid".
pending_orders: dict[str, dict] = {}


def fmt_etb(amount: float) -> str:
    return f"ETB {amount:,.2f}"


def unit_price(product: dict) -> int:
    return product["sale"] if product["sale"] is not None else product["price"]


def cart_lines(chat_id: int):
    cart = carts.get(chat_id, {})
    lines = []
    for pid, qty in cart.items():
        p = PRODUCTS_BY_ID.get(pid)
        if not p or qty <= 0:
            continue
        price = unit_price(p)
        lines.append({"product": p, "qty": qty, "unit": price, "line_total": price * qty})
    return lines


def cart_totals(chat_id: int):
    lines = cart_lines(chat_id)
    subtotal = sum(l["line_total"] for l in lines)
    vat = subtotal * VAT_RATE
    total = subtotal + vat
    return subtotal, vat, total


# ---------- Menus ----------

def main_menu_keyboard(chat_id: int = None):
    buttons = [
        [InlineKeyboardButton("🛍 Browse Categories", callback_data="menu:categories")],
        [InlineKeyboardButton("🧺 View Cart", callback_data="menu:cart")],
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
        row.append(InlineKeyboardButton(cat, callback_data=f"cat:{cat}"))
        if i % 2 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅ Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def photo_products_in(cat: str):
    return [p for p in PRODUCTS if p["cat"] == cat and p.get("photo")]


def text_products_in(cat: str):
    return [p for p in PRODUCTS if p["cat"] == cat and not p.get("photo")]


def products_keyboard(cat: str):
    """Text-only items in this category (photo items get their own messages)."""
    buttons = []
    for p in text_products_in(cat):
        price = unit_price(p)
        label = f"{p['name']} — {fmt_etb(price)}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"add:{p['id']}")])
    buttons.append([InlineKeyboardButton("⬅ Back to Categories", callback_data="menu:categories")])
    return InlineKeyboardMarkup(buttons)


def product_photo_keyboard(product: dict):
    price = unit_price(product)
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"➕ Add — {fmt_etb(price)}", callback_data=f"add:{product['id']}")]]
    )


def cart_keyboard(chat_id: int):
    buttons = []
    for line in cart_lines(chat_id):
        pid = line["product"]["id"]
        buttons.append(
            [
                InlineKeyboardButton(f"➖", callback_data=f"dec:{pid}"),
                InlineKeyboardButton(f"{line['product']['name']} x{line['qty']}", callback_data="noop"),
                InlineKeyboardButton(f"➕", callback_data=f"inc:{pid}"),
            ]
        )
    if cart_lines(chat_id):
        buttons.append([InlineKeyboardButton("✅ Checkout", callback_data="checkout:start")])
        buttons.append([InlineKeyboardButton("🗑 Clear Cart", callback_data="cart:clear")])
    buttons.append([InlineKeyboardButton("🌐 Visit Our Website", url=WEBSITE_URL)])
    buttons.append([InlineKeyboardButton("⬅ Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def cart_text(chat_id: int) -> str:
    lines = cart_lines(chat_id)
    if not lines:
        return "Your cart is empty. Browse the catalog to add something!"
    parts = [f"🧺 *Your Cart*\n"]
    for l in lines:
        parts.append(f"{l['qty']} x {l['product']['name']} — {fmt_etb(l['line_total'])}")
    subtotal, vat, total = cart_totals(chat_id)
    parts.append("")
    parts.append(f"Subtotal: {fmt_etb(subtotal)}")
    parts.append(f"VAT (15%): {fmt_etb(vat)}")
    parts.append(f"*Total: {fmt_etb(total)}*")
    return "\n".join(parts)


# ---------- Command handlers ----------

async def send_cart_photo_album(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """
    Sends up to 10 photos of items currently in the cart as an album, so the
    customer can see what they're buying, not just read a text list.
    Silently does nothing if no cart items have photos, or if fewer than 2
    photos are available (Telegram's media groups require at least 2 items —
    a single photo is sent on its own instead).
    """
    lines = cart_lines(chat_id)
    photo_lines = [l for l in lines if l["product"].get("photo")]
    if not photo_lines:
        return

    media = []
    opened_files = []
    try:
        for l in photo_lines[:10]:
            path = l["product"]["photo"]
            try:
                f = open(path, "rb")
            except FileNotFoundError:
                logger.error("Missing cart photo file: %s", path)
                continue
            opened_files.append(f)
            caption = f"{l['product']['name']} x{l['qty']}"
            media.append(InputMediaPhoto(f, caption=caption))

        if len(media) == 1:
            await context.bot.send_photo(
                chat_id=chat_id, photo=media[0].media, caption=media[0].caption
            )
        elif len(media) >= 2:
            await context.bot.send_media_group(chat_id=chat_id, media=media)
    finally:
        for f in opened_files:
            f.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # If this /start came from the website's "Order via Telegram" button, it
    # arrives as a payload like "1_2-7_1-9_3" (product_id_qty pairs).
    payload = context.args[0] if context.args else None
    loaded_count = 0
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
            if pid not in PRODUCTS_BY_ID or qty <= 0:
                skipped = True
                continue
            carts[chat_id][pid] = carts[chat_id].get(pid, 0) + qty
            loaded_count += 1

    if loaded_count > 0:
        note = (
            "\n\n⚠️ Some items from your cart couldn't be loaded — please check and re-add "
            "anything missing."
            if skipped
            else ""
        )
        await update.message.reply_text(
            f"Selam! Welcome to *{SHOP_NAME}* 🛍\n\n"
            f"We loaded {loaded_count} item(s) from your website cart.{note}\n\n"
            "Review it below, then checkout when ready.",
            parse_mode=ParseMode.MARKDOWN,
        )
        await update.message.reply_text(
            cart_text(chat_id), reply_markup=cart_keyboard(chat_id), parse_mode=ParseMode.MARKDOWN
        )
        return

    await update.message.reply_text(
        f"Selam! Welcome to *{SHOP_NAME}* 🛍\n\n"
        "Browse our catalog and order right here in Telegram.",
        reply_markup=main_menu_keyboard(chat_id),
        parse_mode=ParseMode.MARKDOWN,
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Utility command so the shop owner can find their own chat id."""
    await update.message.reply_text(
        f"Your chat ID is: `{update.effective_chat.id}`\n\n"
        "If you're the shop owner, put this in your .env file as OWNER_CHAT_ID "
        "and restart the bot.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    had_state = checkout_state.pop(chat_id, None) is not None
    if had_state:
        # Clear any lingering phone/location share keyboard from mid-checkout.
        await update.message.reply_text("Checkout cancelled.", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text("What would you like to do?", reply_markup=main_menu_keyboard(chat_id))


# ---------- Button handler ----------

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data

    if data == "noop":
        return

    if data == "menu:main":
        await query.edit_message_text(
            f"*{SHOP_NAME}* 🛍\n\nWhat would you like to do?",
            reply_markup=main_menu_keyboard(chat_id),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "menu:categories":
        await query.edit_message_text("Choose a department:", reply_markup=categories_keyboard())
        return

    if data.startswith("cat:"):
        cat = data.split(":", 1)[1]
        photo_items = photo_products_in(cat)
        text_items = text_products_in(cat)

        if text_items or not photo_items:
            await query.edit_message_text(
                f"*{cat}*", reply_markup=products_keyboard(cat), parse_mode=ParseMode.MARKDOWN
            )
        else:
            # Every item in this category has a photo — the text message would
            # otherwise be an empty list, so just confirm the category and let
            # the photos that follow do the talking.
            await query.edit_message_text(f"*{cat}*", parse_mode=ParseMode.MARKDOWN)

        for p in photo_items:
            try:
                with open(p["photo"], "rb") as photo_file:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_file,
                        caption=f"*{p['name']}*\n{fmt_etb(unit_price(p))}",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=product_photo_keyboard(p),
                    )
            except FileNotFoundError:
                logger.error("Missing photo file for product %s: %s", p["id"], p["photo"])
                # Fall back to a text button so the item is still purchasable
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"{p['name']} — {fmt_etb(unit_price(p))}",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("➕ Add", callback_data=f"add:{p['id']}")]]
                    ),
                )

        if photo_items:
            await context.bot.send_message(
                chat_id=chat_id,
                text="That's everything in this department.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅ Back to Categories", callback_data="menu:categories")]]
                ),
            )
        return

    if data.startswith("add:"):
        pid = int(data.split(":", 1)[1])
        carts.setdefault(chat_id, {})
        carts[chat_id][pid] = carts[chat_id].get(pid, 0) + 1
        await query.answer(text="Added to cart ✅", show_alert=False)
        return

    if data == "menu:cart":
        await query.edit_message_text(
            cart_text(chat_id), reply_markup=cart_keyboard(chat_id), parse_mode=ParseMode.MARKDOWN
        )
        await send_cart_photo_album(context, chat_id)
        return

    if data.startswith("inc:"):
        pid = int(data.split(":", 1)[1])
        carts.setdefault(chat_id, {})
        carts[chat_id][pid] = carts[chat_id].get(pid, 0) + 1
        await query.edit_message_text(
            cart_text(chat_id), reply_markup=cart_keyboard(chat_id), parse_mode=ParseMode.MARKDOWN
        )
        return

    if data.startswith("dec:"):
        pid = int(data.split(":", 1)[1])
        if chat_id in carts and pid in carts[chat_id]:
            carts[chat_id][pid] -= 1
            if carts[chat_id][pid] <= 0:
                del carts[chat_id][pid]
        await query.edit_message_text(
            cart_text(chat_id), reply_markup=cart_keyboard(chat_id), parse_mode=ParseMode.MARKDOWN
        )
        return

    if data == "cart:clear":
        carts[chat_id] = {}
        await query.edit_message_text(
            cart_text(chat_id), reply_markup=cart_keyboard(chat_id), parse_mode=ParseMode.MARKDOWN
        )
        return

    if data == "checkout:start":
        if not cart_lines(chat_id):
            await query.edit_message_text(
                "Your cart is empty.", reply_markup=cart_keyboard(chat_id)
            )
            return
        checkout_state[chat_id] = {"stage": "name"}
        await query.edit_message_text(
            "Let's get your order sent over.\n\nWhat's your *full name*?\n\n"
            "(Type /cancel anytime to stop)",
            parse_mode=ParseMode.MARKDOWN,
        )
        return


# ---------- Checkout: name, phone, and location/address collection ----------

def phone_share_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📞 Share My Phone Number", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def location_share_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Share My Location", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = checkout_state.get(chat_id)
    if not state:
        # Not in a checkout flow — just point them to the menu.
        await update.message.reply_text(
            "Use the menu below to browse or check your cart.",
            reply_markup=main_menu_keyboard(chat_id),
        )
        return

    text = update.message.text.strip()

    if state["stage"] == "name":
        if not text:
            await update.message.reply_text("Please type your full name.")
            return
        state["name"] = text
        state["stage"] = "phone"
        await update.message.reply_text(
            "Thanks! Now tap below to share your phone number, or just type it "
            "if you'd rather not share it directly.",
            reply_markup=phone_share_keyboard(),
        )
        return

    if state["stage"] == "phone":
        # Typed fallback — the button (handled in on_contact) is the other path here.
        if not text:
            await update.message.reply_text("Please share or type your phone number.")
            return
        state["phone"] = text
        await ask_for_location(update, context, chat_id, state)
        return

    if state["stage"] == "address":
        # Typed fallback — the location button (handled in on_location) is the other path.
        if not text:
            await update.message.reply_text("Please share your location or type your address.")
            return
        state["address"] = text
        state["maps_link"] = None
        await update.message.reply_text("Got it!", reply_markup=ReplyKeyboardRemove())
        await finish_checkout(update, context, chat_id, state)
        checkout_state.pop(chat_id, None)
        return


async def ask_for_location(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, state: dict):
    state["stage"] = "address"
    await update.message.reply_text(
        "Almost there! Tap below to share your location on the map 📍 — this is the "
        "most accurate way for us to find you. If you'd rather not, just type your "
        "delivery address instead (subcity / area / landmark).",
        reply_markup=location_share_keyboard(),
    )


async def on_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = checkout_state.get(chat_id)
    if not state or state.get("stage") != "phone":
        return  # a contact shared outside of checkout — ignore

    contact = update.message.contact
    state["phone"] = contact.phone_number
    await ask_for_location(update, context, chat_id, state)


async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = checkout_state.get(chat_id)
    if not state or state.get("stage") != "address":
        return  # a location shared outside of checkout — ignore

    loc = update.message.location
    maps_link = f"https://maps.google.com/?q={loc.latitude},{loc.longitude}"
    state["address"] = f"Shared location: {maps_link}"
    state["maps_link"] = maps_link
    await update.message.reply_text("Got it — location received!", reply_markup=ReplyKeyboardRemove())
    await finish_checkout(update, context, chat_id, state)
    checkout_state.pop(chat_id, None)


def build_order_summary(order: dict, paid: bool) -> str:
    tag = "✅ PAID" if paid else "🕐 Awaiting payment"
    address_line = f"\n📍 Location: {order['maps_link']}" if order.get("maps_link") else f"\n📍 Address: {order['address']}"
    return (
        f"🆕 *New order — {SHOP_NAME}* [{tag}]\n\n"
        + "\n".join(order["lines"])
        + f"\n\nSubtotal: {fmt_etb(order['subtotal'])}"
        + f"\nVAT (15%): {fmt_etb(order['vat'])}"
        + f"\n*Total: {fmt_etb(order['total'])}*"
        + f"\n\n👤 Name: {order['name']}"
        + f"\n📞 Phone: {order.get('phone', 'not provided')}"
        + address_line
        + f"\n💬 Telegram: {order['contact']}"
    )


async def finish_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, state: dict):
    lines = cart_lines(chat_id)
    subtotal, vat, total = cart_totals(chat_id)
    user = update.effective_user

    order_lines = [f"{l['qty']} x {l['product']['name']} — {fmt_etb(l['line_total'])}" for l in lines]
    contact_line = f"@{user.username}" if user.username else f"user ID {user.id}"

    tx_ref = f"DJT{chat_id}{uuid.uuid4().hex[:8]}"
    order = {
        "chat_id": chat_id,
        "lines": order_lines,
        "subtotal": subtotal,
        "vat": vat,
        "total": total,
        "name": state["name"],
        "phone": state.get("phone", "not provided"),
        "address": state["address"],
        "maps_link": state.get("maps_link"),
        "contact": contact_line,
        "status": "pending",
    }
    pending_orders[tx_ref] = order

    name_parts = state["name"].strip().split(" ", 1)
    first_name = name_parts[0] or "Customer"
    last_name = name_parts[1] if len(name_parts) > 1 else "Customer"
    # Telegram doesn't give us a real email; Chapa requires one, so we use a
    # placeholder tied to the chat id. It won't receive mail, but it satisfies
    # Chapa's format validation.
    placeholder_email = f"user{chat_id}@dejaftadlu.et"

    try:
        checkout_url = await initialize_payment(
            amount=total,
            currency="ETB",
            email=placeholder_email,
            first_name=first_name,
            last_name=last_name,
            tx_ref=tx_ref,
            order_description=", ".join(order_lines),
        )
    except ChapaError as e:
        logger.error("Chapa initialize failed for %s: %s", tx_ref, e)
        # Fall back to the old flow so an order still isn't lost if payment setup fails.
        if OWNER_CHAT_ID:
            try:
                await context.bot.send_message(
                    chat_id=int(OWNER_CHAT_ID),
                    text=build_order_summary(order, paid=False)
                    + "\n\n⚠️ Online payment could not be started — follow up manually.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as send_err:
                logger.error("Failed to notify owner about fallback order: %s", send_err)
        carts[chat_id] = {}
        await update.message.reply_text(
            "Your order has been noted, but online payment isn't available right now. "
            "We'll contact you directly to arrange payment.\n\nThank you for your order!",
            reply_markup=main_menu_keyboard(chat_id),
        )
        return

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"💳 Pay {fmt_etb(total)} Now", url=checkout_url)]]
    )
    await update.message.reply_text(
        "Almost done! Tap below to pay securely via Telebirr, CBE Birr, or card.\n\n"
        "We'll confirm automatically the moment your payment goes through.",
        reply_markup=keyboard,
    )

    carts[chat_id] = {}


# ---------- Payment webhook (receives confirmations from Chapa) ----------

async def notify_payment_success(bot, order: dict):
    await bot.send_message(
        chat_id=order["chat_id"],
        text=f"✅ Payment received — {fmt_etb(order['total'])}. Thank you!\n\n"
        "We'll begin preparing your order now.",
    )
    if OWNER_CHAT_ID:
        try:
            await bot.send_message(
                chat_id=int(OWNER_CHAT_ID),
                text=build_order_summary(order, paid=True),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error("Failed to notify owner of paid order: %s", e)
    else:
        logger.warning("OWNER_CHAT_ID not set — paid order was not forwarded to the shop owner.")


async def chapa_webhook_handler(request: web.Request) -> web.Response:
    application: Application = request.app["application"]

    try:
        payload = await request.json()
    except Exception:
        logger.warning("Chapa webhook: received non-JSON body")
        return web.Response(status=400, text="bad request")

    tx_ref = payload.get("tx_ref") or payload.get("trx_ref")
    if not tx_ref:
        logger.warning("Chapa webhook: missing tx_ref in payload")
        return web.Response(status=400, text="missing tx_ref")

    order = pending_orders.get(tx_ref)
    if not order:
        logger.warning("Chapa webhook: unknown tx_ref %s", tx_ref)
        return web.Response(status=200, text="ok")  # acknowledge so Chapa stops retrying

    if order["status"] == "paid":
        return web.Response(status=200, text="already processed")

    # Never trust the webhook body for the actual payment status — verify with
    # Chapa's own servers, which is the whole point of a verify step.
    try:
        result = await verify_payment(tx_ref)
    except ChapaError as e:
        logger.error("Chapa webhook: verify failed for %s: %s", tx_ref, e)
        return web.Response(status=200, text="verify failed, will not mark paid")

    if payment_succeeded(result):
        order["status"] = "paid"
        await notify_payment_success(application.bot, order)
        logger.info("Order %s confirmed paid", tx_ref)
    else:
        logger.info("Chapa webhook: tx_ref %s not yet successful (status check)", tx_ref)

    return web.Response(status=200, text="ok")


async def chapa_thank_you_handler(request: web.Request) -> web.Response:
    return web.Response(
        text="<html><body style='font-family:sans-serif;text-align:center;padding:60px;'>"
        "<h2>Thank you!</h2><p>You can close this window and return to Telegram.</p>"
        "</body></html>",
        content_type="text/html",
    )


async def health_check_handler(request: web.Request) -> web.Response:
    return web.Response(text="Dejaf Tadlu bot is running.")


async def website_order_notify_handler(request: web.Request) -> web.Response:
    """
    Called by the website when a customer completes checkout via the WhatsApp
    button, so that order also reaches the owner on Telegram — not just
    WhatsApp. This is a convenience mirror, not a replacement: the WhatsApp
    message is still the "real" order the customer sends.

    Lightweight-secured with a shared secret header. This is NOT strong
    security (the secret lives in the public website's JS, so anyone who
    reads the page source could find it) — it's just enough to stop casual
    spam/abuse of this endpoint. Don't rely on it for anything sensitive.
    """
    expected_secret = os.getenv("WEBSITE_NOTIFY_SECRET")
    if not expected_secret:
        return web.Response(status=503, text="not configured")

    if request.headers.get("X-Notify-Secret") != expected_secret:
        return web.Response(status=403, text="forbidden")

    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")

    items = payload.get("items", [])
    subtotal = payload.get("subtotal")
    vat = payload.get("vat")
    total = payload.get("total")
    if not items or total is None:
        return web.Response(status=400, text="missing order data")

    lines = []
    for it in items[:50]:  # sanity cap
        try:
            name = str(it.get("name", "item"))[:120]
            qty = int(it.get("qty", 1))
            line_total = float(it.get("lineTotal", 0))
        except (TypeError, ValueError):
            continue
        lines.append(f"{qty} x {name} — {fmt_etb(line_total)}")

    if not lines:
        return web.Response(status=400, text="no valid items")

    try:
        subtotal_f = float(subtotal)
        vat_f = float(vat)
        total_f = float(total)
    except (TypeError, ValueError):
        return web.Response(status=400, text="invalid totals")

    summary = (
        f"🆕 *New order — via Website (WhatsApp)*\n\n"
        + "\n".join(lines)
        + f"\n\nSubtotal: {fmt_etb(subtotal_f)}"
        + f"\nVAT (15%): {fmt_etb(vat_f)}"
        + f"\n*Total: {fmt_etb(total_f)}*"
        + "\n\n💬 Sent to the customer's WhatsApp — reply there to confirm delivery."
    )

    application: Application = request.app["application"]
    if OWNER_CHAT_ID:
        try:
            await application.bot.send_message(
                chat_id=int(OWNER_CHAT_ID), text=summary, parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error("Failed to mirror website order to Telegram: %s", e)
            return web.Response(status=502, text="failed to notify")
    else:
        logger.warning("OWNER_CHAT_ID not set — website order was not mirrored to Telegram.")

    return web.Response(status=200, text="ok")


async def run():
    if not BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN is not set. Copy .env.example to .env and add your token from @BotFather."
        )

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myid", myid))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(on_button))
    application.add_handler(MessageHandler(filters.CONTACT, on_contact))
    application.add_handler(MessageHandler(filters.LOCATION, on_location))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Small web server just for Chapa's payment confirmations. Only started if
    # a payment gateway key is configured — otherwise the bot still works fine
    # for browsing/checkout, it just falls back to manual payment arrangement.
    web_app = web.Application()
    web_app["application"] = application
    web_app.router.add_post("/chapa/webhook", chapa_webhook_handler)
    web_app.router.add_get("/chapa/thank-you", chapa_thank_you_handler)
    web_app.router.add_post("/notify/website-order", website_order_notify_handler)
    web_app.router.add_get("/", health_check_handler)

    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Payment webhook server listening on port %s", port)

    async with application:
        await application.start()
        await application.updater.start_polling()
        logger.info("Bot starting...")
        try:
            # Run until interrupted (Ctrl+C locally, or container stop on Railway)
            import asyncio
            await asyncio.Event().wait()
        finally:
            await application.updater.stop()
            await application.stop()
            await runner.cleanup()


def main():
    import asyncio
    asyncio.run(run())


if __name__ == "__main__":
    main()
