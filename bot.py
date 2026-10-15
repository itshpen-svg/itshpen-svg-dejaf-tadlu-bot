"""
Dejaf Tadlu ደጃፍ ታደሉ - Telegram Ordering Bot
Browse catalog, cart, checkout. Full website cart via /notify/website-order.
Order summary (with VAT) goes to shop owner. Location includes Google Maps link.
"""

from __future__ import annotations

import os
import re
import time
import secrets
import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from aiohttp import web

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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

from products import PRODUCTS, CATEGORIES, PRODUCTS_BY_ID, start_firebase_sync

load_dotenv()

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
OWNER_CHAT_ID = (os.getenv("OWNER_CHAT_ID") or "").strip()
WEBSITE_NOTIFY_SECRET = (os.getenv("WEBSITE_NOTIFY_SECRET") or "").strip()
VAT_RATE = 0.15
SHOP_NAME = "Dejaf Tadlu"
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://itshpen-svg.github.io/itshpen-svg-dejaf-tadlu-bot/")
PHOTO_BASE_URL = (
    (os.getenv("PHOTO_BASE_URL") or "https://raw.githubusercontent.com/itshpen-svg/dejaf-tadlu-bot/main/")
    .rstrip("/")
    + "/"
)
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

# user_id -> { product_id: qty }
carts: dict[int, dict[int, int]] = {}
# user_id -> checkout stage dict
checkout_state: dict[int, dict[str, Any]] = {}
# order_id -> full website order payload
PENDING_WEB_ORDERS: dict[str, dict] = {}
ORDER_TTL_SEC = 60 * 60 * 6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_etb(n: float) -> str:
    try:
        return f"ETB {float(n):,.2f}"
    except Exception:
        return f"ETB {n}"


def unit_price(p: dict) -> float:
    sale = p.get("sale")
    if sale is not None and sale != "":
        try:
            return float(sale)
        except (TypeError, ValueError):
            pass
    try:
        return float(p.get("price") or 0)
    except (TypeError, ValueError):
        return 0.0


def product_unit(p: dict) -> str:
    return (p.get("unit") or "pcs").strip() or "pcs"


def product_step(p: dict) -> float:
    try:
        s = float(p.get("step") if p.get("step") not in (None, "") else 1)
    except (TypeError, ValueError):
        s = 1.0
    return s if s > 0 else 1.0


def product_min(p: dict) -> float:
    try:
        m = float(p.get("min") if p.get("min") not in (None, "") else 1)
    except (TypeError, ValueError):
        m = 1.0
    return m if m > 0 else 1.0


def format_qty(qty, unit: str) -> str:
    try:
        q = float(qty)
    except (TypeError, ValueError):
        q = qty
    if isinstance(q, float) and q == int(q):
        q = int(q)
    return f"{q} {unit}"


def cart_lines(user_id: int) -> list[dict]:
    cart = carts.get(user_id) or {}
    lines = []
    for pid, qty in cart.items():
        p = PRODUCTS_BY_ID.get(pid) or PRODUCTS_BY_ID.get(int(pid))
        if not p or qty <= 0:
            continue
        u = unit_price(p)
        pu = product_unit(p)
        q = float(qty)
        lines.append(
            {
                "id": p["id"],
                "name": p["name"],
                "qty": q,
                "measure": pu,
                "unit": u,
                "lineTotal": u * q,
            }
        )
    return lines


def cart_totals(user_id: int) -> tuple[float, float, float]:
    lines = cart_lines(user_id)
    subtotal = sum(x["lineTotal"] for x in lines)
    vat = subtotal * VAT_RATE
    total = subtotal + vat
    return subtotal, vat, total


def format_cart_text(user_id: int, title: str = "Your cart") -> str:
    lines = cart_lines(user_id)
    if not lines:
        return "Cart is empty."
    subtotal, vat, total = cart_totals(user_id)
    parts = [title, ""]
    for i, e in enumerate(lines, 1):
        mq = format_qty(e["qty"], e.get("measure") or "pcs")
        parts.append(f"{i}. {e['name']} × {mq} — {format_etb(e['lineTotal'])}")
    parts += [
        "",
        f"Subtotal: {format_etb(subtotal)}",
        f"VAT (15%): {format_etb(vat)}",
        f"Total: {format_etb(total)}",
    ]
    return "\n".join(parts)


def build_order_text_from_payload(data: dict, source: str = "Website") -> str:
    items = data.get("items") or []
    subtotal = float(data.get("subtotal") or 0)
    if not subtotal and items:
        for it in items:
            lt = it.get("lineTotal")
            if lt is None:
                lt = float(it.get("unit") or it.get("price") or 0) * int(it.get("qty") or 1)
            subtotal += float(lt)
    vat = float(data["vat"]) if data.get("vat") is not None else subtotal * VAT_RATE
    total = float(data["total"]) if data.get("total") is not None else subtotal + vat
    order_id = data.get("order_id") or ""
    lines = [f"🛒 New order from {source}", f"Order #{order_id}" if order_id else "New order", ""]
    for i, it in enumerate(items, 1):
        name = it.get("name") or f"Item {it.get('id')}"
        qty = it.get("qty") or 1
        measure = (it.get("measure") or it.get("unit_label") or "").strip()
        # unit field from website is price-per-unit; measure is kg/L/pcs
        if measure in ("", "pcs", "kg", "L", "g", "ml") or not measure:
            pass
        # Prefer explicit measure; if "unit" looks like a measure label use it
        mu = it.get("measure") or ""
        if not mu and isinstance(it.get("unit"), str) and it.get("unit") in ("pcs", "kg", "L", "g", "ml"):
            mu = it.get("unit")
        if not mu:
            mu = "pcs"
        line = it.get("lineTotal")
        if line is None:
            try:
                qf = float(qty)
            except (TypeError, ValueError):
                qf = 1
            line = float(it.get("unit") if not isinstance(it.get("unit"), str) else it.get("price") or 0) * qf
        lines.append(f"{i}. {name} × {format_qty(qty, mu)} — {format_etb(line)}")
    lines += [
        "",
        f"Subtotal: {format_etb(subtotal)}",
        f"VAT (15%): {format_etb(vat)}",
        f"Total: {format_etb(total)}",
    ]
    return "\n".join(lines)


def cleanup_pending():
    now = time.time()
    for k in [k for k, v in PENDING_WEB_ORDERS.items() if now - v.get("_ts", 0) > ORDER_TTL_SEC]:
        PENDING_WEB_ORDERS.pop(k, None)


def photo_url(p: dict) -> str | None:
    path = (p.get("photo") or p.get("img") or "").strip()
    if not path:
        return None
    if path.startswith("http://") or path.startswith("https://"):
        return path
    local = BASE_DIR / path
    if local.is_file():
        return str(local)
    return PHOTO_BASE_URL + path.lstrip("/")


def main_menu_kb() -> InlineKeyboardMarkup:
    cats = CATEGORIES[:] if CATEGORIES else sorted(set(p.get("cat") or "Other" for p in PRODUCTS))
    rows = []
    row = []
    for c in cats:
        row.append(InlineKeyboardButton(c, callback_data=f"cat:{c}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton("🛒 Cart", callback_data="cart"),
            InlineKeyboardButton("Checkout", callback_data="checkout"),
        ]
    )
    rows.append([InlineKeyboardButton("🌐 Website", url=WEBSITE_URL)])
    return InlineKeyboardMarkup(rows)


def products_kb(cat: str) -> InlineKeyboardMarkup:
    items = [p for p in PRODUCTS if (p.get("cat") or "") == cat]
    rows = []
    for p in items[:40]:
        label = f"{p['name'][:24]} · {format_etb(unit_price(p))}/{product_unit(p)}"
        rows.append([InlineKeyboardButton(label, callback_data=f"p:{p['id']}")])
    rows.append([InlineKeyboardButton("« Categories", callback_data="home")])
    rows.append([InlineKeyboardButton("🛒 Cart", callback_data="cart")])
    return InlineKeyboardMarkup(rows)


def product_kb(pid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Add 1", callback_data=f"add:{pid}"),
                InlineKeyboardButton("➕ Add 3", callback_data=f"add3:{pid}"),
            ],
            [InlineKeyboardButton("🛒 Cart", callback_data="cart")],
            [InlineKeyboardButton("« Back", callback_data="home")],
        ]
    )


def cart_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Checkout", callback_data="checkout")],
            [InlineKeyboardButton("Clear cart", callback_data="clear")],
            [InlineKeyboardButton("« Continue shopping", callback_data="home")],
        ]
    )


# ---------------------------------------------------------------------------
# Website notify HTTP API (full cart — option D)
# ---------------------------------------------------------------------------

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Notify-Secret",
        "Access-Control-Max-Age": "86400",
    }


def create_web_app(application: Application) -> web.Application:
    app = web.Application()

    async def health(_request):
        return web.json_response({"ok": True, "products": len(PRODUCTS)}, headers=_cors_headers())

    async def options_handler(_request):
        return web.Response(status=204, headers=_cors_headers())

    async def website_order(request: web.Request):
        if request.method == "OPTIONS":
            return web.Response(status=204, headers=_cors_headers())
        hdr = request.headers.get("X-Notify-Secret") or ""
        if not WEBSITE_NOTIFY_SECRET or hdr != WEBSITE_NOTIFY_SECRET:
            return web.json_response(
                {"ok": False, "error": "unauthorized"},
                status=401,
                headers=_cors_headers(),
            )
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"ok": False, "error": "invalid json"},
                status=400,
                headers=_cors_headers(),
            )

        items = data.get("items")
        if not isinstance(items, list) or not items:
            return web.json_response(
                {"ok": False, "error": "no items"},
                status=400,
                headers=_cors_headers(),
            )

        cleanup_pending()
        order_id = (data.get("order_id") or "").strip()
        # Telegram /start payload max 64 chars — keep short token
        token = "w" + secrets.token_hex(4)
        if order_id and re.match(r"^[\w\-]{1,32}$", order_id):
            # still store short token for start= link
            pass

        subtotal = float(data.get("subtotal") or 0)
        if not subtotal:
            for it in items:
                lt = it.get("lineTotal")
                if lt is None:
                    lt = float(it.get("unit") or it.get("price") or 0) * int(it.get("qty") or 1)
                subtotal += float(lt)
        vat = float(data["vat"]) if data.get("vat") is not None else subtotal * VAT_RATE
        total = float(data["total"]) if data.get("total") is not None else subtotal + vat

        payload = {
            "order_id": order_id or token,
            "token": token,
            "items": items,
            "subtotal": subtotal,
            "vat": vat,
            "total": total,
            "_ts": time.time(),
        }
        PENDING_WEB_ORDERS[token] = payload
        if order_id:
            PENDING_WEB_ORDERS[order_id] = payload

        text = build_order_text_from_payload(payload, source="Website → Telegram")
        if OWNER_CHAT_ID:
            try:
                await application.bot.send_message(chat_id=int(OWNER_CHAT_ID), text=text)
            except Exception:
                logger.exception("Owner notify failed")

        return web.json_response(
            {"ok": True, "order_id": token},
            headers=_cors_headers(),
        )

    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_route("OPTIONS", "/notify/website-order", options_handler)
    app.router.add_post("/notify/website-order", website_order)
    return app


def apply_web_order_to_cart(user_id: int, token: str) -> dict | None:
    cleanup_pending()
    data = PENDING_WEB_ORDERS.get(token)
    if not data:
        return None
    cart: dict[int, int] = {}
    for it in data.get("items") or []:
        try:
            pid = int(it.get("id"))
            qty = int(it.get("qty") or 1)
        except (TypeError, ValueError):
            continue
        if pid and qty > 0:
            cart[pid] = cart.get(pid, 0) + qty
    # Prefer website line prices when product missing from bot catalog
    carts[user_id] = cart
    # Stash totals so checkout uses website amounts if needed
    checkout_state[user_id] = {
        "stage": None,
        "web_order": data,
    }
    return data


def parse_start_payload(arg: str, user_id: int) -> str | None:
    """Load cart from website token or id_qty-id_qty payload. Returns status note."""
    arg = (arg or "").strip()
    if not arg:
        return None

    # Website full-cart token (w + hex)
    if arg.startswith("w") and arg in PENDING_WEB_ORDERS:
        data = apply_web_order_to_cart(user_id, arg)
        if data:
            n = len(data.get("items") or [])
            return f"Loaded website order ({n} lines). Total {format_etb(data.get('total') or 0)} including VAT."
        return None

    # Also try order_id key
    if arg in PENDING_WEB_ORDERS:
        data = apply_web_order_to_cart(user_id, arg)
        if data:
            n = len(data.get("items") or [])
            return f"Loaded website order ({n} lines). Total {format_etb(data.get('total') or 0)} including VAT."

    # Legacy: 21_2-29_1
    if re.match(r"^[\d_]+(?:-[\d_]+)*$", arg):
        cart: dict[int, int] = {}
        for part in arg.split("-"):
            if "_" not in part:
                continue
            a, b = part.split("_", 1)
            try:
                pid, qty = int(a), int(b)
            except ValueError:
                continue
            if pid and qty > 0:
                cart[pid] = cart.get(pid, 0) + qty
        if cart:
            carts[user_id] = cart
            return f"Loaded {sum(cart.values())} item(s) from website link."
    return None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    note = None
    if context.args:
        note = parse_start_payload(context.args[0], uid)

    text = (
        f"Welcome to {SHOP_NAME} (ደጃፍ ታደሉ)!\n"
        "Browse categories, add to cart, checkout.\n"
        "Payment: cash on delivery · Addis Ababa.\n"
    )
    if note:
        text += "\n" + note + "\n\n" + format_cart_text(uid)

    await update.message.reply_text(text, reply_markup=main_menu_kb())


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your chat id: `{update.effective_chat.id}`", parse_mode="Markdown")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    checkout_state.pop(uid, None)
    await update.message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text("Main menu:", reply_markup=main_menu_kb())


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data or ""

    if data == "home":
        await q.edit_message_text("Choose a category:", reply_markup=main_menu_kb())
        return

    if data.startswith("cat:"):
        cat = data[4:]
        await q.edit_message_text(f"Category: {cat}", reply_markup=products_kb(cat))
        return

    if data.startswith("p:"):
        pid = int(data[2:])
        p = PRODUCTS_BY_ID.get(pid)
        if not p:
            await q.edit_message_text("Product not found.", reply_markup=main_menu_kb())
            return
        text = f"{p['name']}\n{format_etb(unit_price(p))}\nCategory: {p.get('cat')}"
        url = photo_url(p)
        try:
            if url and url.startswith("http"):
                await q.message.reply_photo(url, caption=text, reply_markup=product_kb(pid))
                return
            if url and Path(url).is_file():
                with open(url, "rb") as f:
                    await q.message.reply_photo(f, caption=text, reply_markup=product_kb(pid))
                return
        except Exception:
            logger.exception("photo send failed")
        await q.message.reply_text(text, reply_markup=product_kb(pid))
        return

    if data.startswith("add:") or data.startswith("add3:"):
        pid = int(data.split(":")[1])
        n = 3 if data.startswith("add3:") else 1
        carts.setdefault(uid, {})
        carts[uid][pid] = carts[uid].get(pid, 0) + n
        p = PRODUCTS_BY_ID.get(pid)
        name = p["name"] if p else str(pid)
        await q.message.reply_text(f"Added {n} × {name}\n\n{format_cart_text(uid)}", reply_markup=cart_kb())
        return

    if data == "cart":
        await q.message.reply_text(format_cart_text(uid), reply_markup=cart_kb())
        return

    if data == "clear":
        carts[uid] = {}
        checkout_state.pop(uid, None)
        await q.message.reply_text("Cart cleared.", reply_markup=main_menu_kb())
        return

    if data == "checkout":
        lines = cart_lines(uid)
        if not lines:
            # website order may have items not in PRODUCTS_BY_ID
            web = (checkout_state.get(uid) or {}).get("web_order")
            if not web or not web.get("items"):
                await q.message.reply_text("Cart is empty.", reply_markup=main_menu_kb())
                return
        checkout_state[uid] = {**(checkout_state.get(uid) or {}), "stage": "name"}
        await q.message.reply_text(
            format_cart_text(uid) + "\n\nPlease send your *full name*.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = (update.message.text or "").strip()
    st = checkout_state.get(uid) or {}
    stage = st.get("stage")

    if stage == "name":
        st["name"] = text
        st["stage"] = "phone"
        checkout_state[uid] = st
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("Share phone", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await update.message.reply_text("Send your phone number, or tap the button.", reply_markup=kb)
        return

    if stage == "phone":
        st["phone"] = text
        st["stage"] = "location"
        checkout_state[uid] = st
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("Share location", request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await update.message.reply_text(
            "Send delivery location (tap Share location), or type your address.",
            reply_markup=kb,
        )
        return

    if stage == "location":
        st["address"] = text
        st["location"] = None
        checkout_state[uid] = st
        await finish_order(update, context)
        return

    await update.message.reply_text("Use the menu buttons, or /start.", reply_markup=main_menu_kb())


async def on_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = checkout_state.get(uid) or {}
    if st.get("stage") != "phone":
        return
    contact = update.message.contact
    st["phone"] = contact.phone_number if contact else ""
    st["stage"] = "location"
    checkout_state[uid] = st
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("Share location", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(
        "Thanks. Now share your delivery location, or type your address.",
        reply_markup=kb,
    )


async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = checkout_state.get(uid) or {}
    # Accept location during checkout even if stage slightly off
    if st.get("stage") not in ("location", "phone", "name") and "name" not in st:
        # still allow if they were checking out
        if not st:
            return
    loc = update.message.location
    if not loc:
        return
    st["location"] = {"lat": loc.latitude, "lng": loc.longitude}
    st["address"] = st.get("address") or f"{loc.latitude:.6f}, {loc.longitude:.6f}"
    st["stage"] = "location"
    checkout_state[uid] = st
    await finish_order(update, context)


async def finish_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user
    st = checkout_state.get(uid) or {}
    web = st.get("web_order")

    if web and web.get("items"):
        body = build_order_text_from_payload(web, source="Telegram checkout")
        subtotal = float(web.get("subtotal") or 0)
        vat = float(web.get("vat") if web.get("vat") is not None else subtotal * VAT_RATE)
        total = float(web.get("total") if web.get("total") is not None else subtotal + vat)
    else:
        lines = cart_lines(uid)
        if not lines:
            await update.message.reply_text("Cart empty.", reply_markup=main_menu_kb())
            return
        body = format_cart_text(uid, title="🛒 Order")
        subtotal, vat, total = cart_totals(uid)

    order_ref = "TG-" + uuid.uuid4().hex[:8].upper()
    name = st.get("name") or (user.full_name if user else "")
    phone = st.get("phone") or ""
    address = st.get("address") or ""
    loc = st.get("location")

    maps = ""
    if loc and loc.get("lat") is not None:
        maps = f"https://maps.google.com/?q={loc['lat']},{loc['lng']}"

    customer = [
        "",
        f"Order ref: {order_ref}",
        f"Customer: {name}",
        f"Phone: {phone}",
        f"Address: {address}",
    ]
    if maps:
        customer.append(f"Map: {maps}")
    customer.append(f"Telegram: @{user.username}" if user and user.username else f"Telegram id: {uid}")

    owner_text = body + "\n" + "\n".join(customer)

    if OWNER_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(OWNER_CHAT_ID), text=owner_text)
        except Exception:
            logger.exception("Failed to notify owner")

    await update.message.reply_text(
        "Betam ameseginalehu! Your order was sent to Dejaf Tadlu.\n"
        f"Ref: {order_ref}\n"
        f"Total: {format_etb(total)} (incl. VAT)\n"
        "We will confirm delivery details soon.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.message.reply_text("Shop again anytime:", reply_markup=main_menu_kb())

    carts[uid] = {}
    checkout_state.pop(uid, None)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def post_init(application: Application):
    try:
        start_firebase_sync()
    except Exception:
        logger.exception("Firebase sync failed to start")

    web_app = create_web_app(application)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("HTTP notify server listening on 0.0.0.0:%s", PORT)


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN missing")

    # Python 3.12+ event loop for some hosts
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
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(on_button))
    application.add_handler(MessageHandler(filters.CONTACT, on_contact))
    application.add_handler(MessageHandler(filters.LOCATION, on_location))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    photos_dir = BASE_DIR / "photos"
    n_photos = len(list(photos_dir.glob("*.jpg"))) if photos_dir.is_dir() else 0
    logger.info("Photo folder: %s (%s jpg)", photos_dir, n_photos)
    logger.info("Starting bot (polling)...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        close_loop=False,
    )


if __name__ == "__main__":
    main()
