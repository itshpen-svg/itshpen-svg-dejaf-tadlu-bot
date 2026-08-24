"""
Dejaf Tadlu - Telegram Ordering Bot
"""

import os
import logging
import uuid
from dotenv import load_dotenv

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

try:
    from payments import initialize_payment, ChapaError
    HAS_CHAPA = True
except Exception:
    HAS_CHAPA = False

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://dejaf-tadlu-onlineshopping.netlify.app")
TELEBIRR_NUMBER = os.getenv("TELEBIRR_NUMBER", "0919766932")
CBE_ACCOUNT = os.getenv("CBE_ACCOUNT", "")
AWASH_ACCOUNT = os.getenv("AWASH_ACCOUNT", "")
CHANNEL_URL = "https://t.me/etc12tell4"
VAT_RATE = 0.15
SHOP_NAME = "Dejaf Tadlu"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

PRODUCTS_BY_ID = {p["id"]: p for p in PRODUCTS}
carts = {}
checkout_state = {}
orders_by_chat = {}
pending_orders = {}


def fmt_etb(amount):
    return "ETB {:,.2f}".format(amount)


def unit_price(product):
    return product["sale"] if product.get("sale") is not None else product["price"]


def cart_lines(chat_id):
    cart = carts.get(chat_id, {})
    lines = []
    for pid, qty in cart.items():
        p = PRODUCTS_BY_ID.get(pid)
        if not p or qty <= 0:
            continue
        price = unit_price(p)
        lines.append({
            "product": p,
            "qty": qty,
            "unit": price,
            "line_total": price * qty,
        })
    return lines


def cart_totals(chat_id):
    lines = cart_lines(chat_id)
    subtotal = sum(l["line_total"] for l in lines)
    vat = subtotal * VAT_RATE
    total = subtotal + vat
    return subtotal, vat, total


def main_menu_keyboard(chat_id=None):
    buttons = [
        [InlineKeyboardButton("Browse Categories", callback_data="menu:categories")],
        [InlineKeyboardButton("Weekly Asbeza", callback_data="menu:asbeza")],
        [InlineKeyboardButton("View Cart", callback_data="menu:cart")],
    ]
    if chat_id is not None and cart_lines(chat_id):
        buttons.append([InlineKeyboardButton("Checkout", callback_data="checkout:start")])
        buttons.append([InlineKeyboardButton("Clear Cart", callback_data="cart:clear")])
    buttons.append([InlineKeyboardButton("Join our Channel", url=CHANNEL_URL)])
    buttons.append([InlineKeyboardButton("Visit Our Website", url=WEBSITE_URL)])
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
    buttons.append([InlineKeyboardButton("Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


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
        label = p["name"] + " - " + fmt_etb(unit_price(p))
        buttons.append([InlineKeyboardButton(label, callback_data="add:" + str(p["id"]))])
    buttons.append([InlineKeyboardButton("Back to Categories", callback_data="menu:categories")])
    return InlineKeyboardMarkup(buttons)


def product_photo_keyboard(product):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "Add - " + fmt_etb(unit_price(product)),
            callback_data="add:" + str(product["id"]),
        )
    ]])


def cart_keyboard(chat_id):
    buttons = []
    for line in cart_lines(chat_id):
        pid = line["product"]["id"]
        name = line["product"]["name"]
        short = name if len(name) <= 22 else name[:20] + ".."
        buttons.append([
            InlineKeyboardButton("-", callback_data="dec:" + str(pid)),
            InlineKeyboardButton(short + " x" + str(line["qty"]), callback_data="noop"),
            InlineKeyboardButton("+", callback_data="inc:" + str(pid)),
        ])
    if cart_lines(chat_id):
        buttons.append([InlineKeyboardButton("Checkout", callback_data="checkout:start")])
        buttons.append([InlineKeyboardButton("Clear Cart", callback_data="cart:clear")])
    buttons.append([InlineKeyboardButton("Visit Our Website", url=WEBSITE_URL)])
    buttons.append([InlineKeyboardButton("Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def cart_text(chat_id):
    lines = cart_lines(chat_id)
    if not lines:
        return "Your cart is empty. Browse the catalog to add something!"
    parts = ["Your Cart\n"]
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
            path = l["product"]["photo"]
            try:
                f = open(path, "rb")
            except FileNotFoundError:
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            if pid not in PRODUCTS_BY_ID or qty <= 0 or PRODUCTS_BY_ID[pid].get("builder"):
                skipped = True
                continue
            carts[chat_id][pid] = carts[chat_id].get(pid, 0) + qty
            loaded += 1

    if loaded > 0:
        note = "\n\nSome items could not be loaded." if skipped else ""
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
        "Payments: Telebirr, CBE Birr, Awash Bank, Cash on Delivery\n"
        "Channel: " + CHANNEL_URL,
        reply_markup=main_menu_keyboard(chat_id),
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Your chat ID is: " + str(update.effective_chat.id) + "\n\n"
        "Put this in Render as OWNER_CHAT_ID if you are the shop owner."
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if checkout_state.pop(chat_id, None):
        await update.message.reply_text("Checkout cancelled.", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(
        "What would you like to do?",
        reply_markup=main_menu_keyboard(chat_id),
    )


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data

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
        tip = (
            "Weekly Asbeza\n\n"
            "Add vegetables and staples from the list below.\n"
            "Cart total updates as you add.\n\n"
            "Payments: Telebirr, CBE Birr, Awash Bank, Cash on Delivery"
        )
        await query.edit_message_text(tip, reply_markup=products_keyboard("Grocery"))
        for p in photo_products_in("Grocery"):
            try:
                with open(p["photo"], "rb") as photo_file:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_file,
                        caption=p["name"] + "\n" + fmt_etb(unit_price(p)),
                        reply_markup=product_photo_keyboard(p),
                    )
            except FileNotFoundError:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=p["name"] + " - " + fmt_etb(unit_price(p)),
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("Add", callback_data="add:" + str(p["id"]))]]
                    ),
                )
        return

    if data.startswith("cat:"):
        cat = data.split(":", 1)[1]
        photo_items = photo_products_in(cat)
        text_items = text_products_in(cat)
        if text_items or not photo_items:
            await query.edit_message_text(cat, reply_markup=products_keyboard(cat))
        else:
            await query.edit_message_text(cat)
        for p in photo_items:
            try:
                with open(p["photo"], "rb") as photo_file:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_file,
                        caption=p["name"] + "\n" + fmt_etb(unit_price(p)),
                        reply_markup=product_photo_keyboard(p),
                    )
            except FileNotFoundError:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=p["name"] + " - " + fmt_etb(unit_price(p)),
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("Add", callback_data="add:" + str(p["id"]))]]
                    ),
                )
        if photo_items:
            await context.bot.send_message(
                chat_id=chat_id,
                text="That's everything in this department.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Back to Categories", callback_data="menu:categories")]]
                ),
            )
        return

    if data.startswith("add:"):
        pid = int(data.split(":", 1)[1])
        p = PRODUCTS_BY_ID.get(pid)
        if p and p.get("builder"):
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Weekly Asbeza\n\n"
                    "Pick items from Grocery (vegetables + staples).\n"
                    "Add each with + ."
                ),
                reply_markup=products_keyboard("Grocery"),
            )
            return
        carts.setdefault(chat_id, {})
        carts[chat_id][pid] = carts[chat_id].get(pid, 0) + 1
        await query.answer(text="Added to cart")
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
                "Your cart is empty.",
                reply_markup=main_menu_keyboard(chat_id),
            )
            return
        checkout_state[chat_id] = {"stage": "name"}
        await query.edit_message_text("Checkout\n\nPlease send your full name.")
        return

    # Payment method after address
    if data.startswith("pay:"):
        method = data.split(":", 1)[1]
        state = checkout_state.get(chat_id)
        if not state or state.get("stage") != "payment":
            return
        state["payment"] = method
        state["stage"] = "contact"
        await query.edit_message_text("Payment method: " + method)

        if method == "Telebirr":
            tip = (
                "Pay with Telebirr\n\n"
                "Send the TOTAL to: " + TELEBIRR_NUMBER + "\n"
                "Use your name as the reason.\n\n"
                "Then share your phone number below."
            )
        elif method == "CBE Birr":
            tip = (
                "Pay with CBE Birr\n\n"
                + (("Account: " + CBE_ACCOUNT + "\n\n") if CBE_ACCOUNT else "")
                + "Share your phone number below."
            )
        elif method == "Awash Bank":
            tip = (
                "Pay with Awash Bank\n\n"
                + (("Account: " + AWASH_ACCOUNT + "\n\n") if AWASH_ACCOUNT else "")
                + "Share your phone number below."
            )
        else:
            tip = (
                "Cash on Delivery\n\n"
                "Pay when the order arrives.\n"
                "Share your phone number to finish."
            )

        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("Share my phone number", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await context.bot.send_message(chat_id=chat_id, text=tip, reply_markup=kb)
        return


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()
    state = checkout_state.get(chat_id)

    if not state:
        # Maybe transaction ID for an open order
        order = orders_by_chat.get(chat_id)
        if order and order.get("payment") != "Cash on Delivery" and len(text) >= 6:
            if OWNER_CHAT_ID:
                try:
                    await context.bot.send_message(
                        chat_id=int(OWNER_CHAT_ID),
                        text=(
                            "TX / REFERENCE\n"
                            "Order: " + order["order_id"] + "\n"
                            "Payment: " + str(order.get("payment")) + "\n"
                            "Reference: " + text + "\n"
                            "Customer chat: " + str(chat_id)
                        ),
                    )
                except Exception as e:
                    logger.error("Notify owner tx failed: %s", e)
            await update.message.reply_text(
                "Reference received for order " + order["order_id"] + ".\n"
                "We will verify shortly."
            )
            return
        await update.message.reply_text(
            "Use the menu buttons to browse and order.",
            reply_markup=main_menu_keyboard(chat_id),
        )
        return

    if state.get("stage") == "name":
        state["name"] = text
        state["stage"] = "address"
        await update.message.reply_text(
            "Thanks, " + text + ".\n\nPlease send your delivery address in Addis Ababa."
        )
        return

    if state.get("stage") == "address":
        state["address"] = text
        state["stage"] = "payment"
        pay_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Telebirr", callback_data="pay:Telebirr")],
            [InlineKeyboardButton("CBE Birr", callback_data="pay:CBE Birr")],
            [InlineKeyboardButton("Awash Bank", callback_data="pay:Awash Bank")],
            [InlineKeyboardButton("Cash on Delivery", callback_data="pay:Cash on Delivery")],
        ])
        await update.message.reply_text("Choose your payment method:", reply_markup=pay_kb)
        return

    if state.get("stage") == "contact":
        state["contact"] = text
        await finish_checkout(update, context, chat_id)
        return


async def on_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = checkout_state.get(chat_id)
    if not state or state.get("stage") != "contact":
        return
    contact = update.message.contact
    state["contact"] = contact.phone_number if contact else "unknown"
    await finish_checkout(update, context, chat_id)


async def finish_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    state = checkout_state.pop(chat_id, {})
    lines = cart_lines(chat_id)
    if not lines:
        await update.message.reply_text("Your cart is empty.", reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text(
            "What would you like to do?",
            reply_markup=main_menu_keyboard(chat_id),
        )
        return

    subtotal, vat, total = cart_totals(chat_id)
    name = state.get("name", "-")
    address = state.get("address", "-")
    contact = state.get("contact", "-")
    payment = state.get("payment", "Not specified")
    order_id = "DJT-" + uuid.uuid4().hex[:8].upper()

    summary_lines = [
        str(l["qty"]) + " x " + l["product"]["name"] + " - " + fmt_etb(l["line_total"])
        for l in lines
    ]
    summary = (
        "Order " + order_id + "\n"
        "Customer: " + name + "\n"
        "Phone: " + str(contact) + "\n"
        "Address: " + address + "\n"
        "Payment: " + payment + "\n\n"
        + "\n".join(summary_lines)
        + "\n\nSubtotal: " + fmt_etb(subtotal)
        + "\nVAT (15%): " + fmt_etb(vat)
        + "\nTotal: " + fmt_etb(total)
    )

    if OWNER_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=int(OWNER_CHAT_ID),
                text="NEW ORDER\n\n" + summary,
            )
        except Exception as e:
            logger.error("Failed to notify owner: %s", e)

    orders_by_chat[chat_id] = {
        "order_id": order_id,
        "summary": summary,
        "payment": payment,
        "total": total,
        "name": name,
    }
    carts[chat_id] = {}

    await update.message.reply_text("Order received. Thank you!", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(
        "We got your order (" + order_id + ").\n\n" + summary,
        reply_markup=main_menu_keyboard(chat_id),
    )

    if payment != "Cash on Delivery":
        await update.message.reply_text(
            "After you pay, send a photo of the receipt here,\n"
            "or type the transaction ID.\n\n"
            "We will confirm your order."
        )

    await update.message.reply_text("Offers & news: " + CHANNEL_URL)


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    order = orders_by_chat.get(chat_id)
    caption = (update.message.caption or "").strip()

    if not order:
        await update.message.reply_text("No open order found. Use Checkout or /start first.")
        return

    if OWNER_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=int(OWNER_CHAT_ID),
                text=(
                    "RECEIPT RECEIVED\n"
                    "Order: " + order["order_id"] + "\n"
                    "Payment: " + str(order.get("payment")) + "\n"
                    "Customer chat: " + str(chat_id) + "\n"
                    + (("Note: " + caption + "\n") if caption else "")
                ),
            )
            await context.bot.forward_message(
                chat_id=int(OWNER_CHAT_ID),
                from_chat_id=chat_id,
                message_id=update.message.message_id,
            )
        except Exception as e:
            logger.error("Forward receipt failed: %s", e)

    await update.message.reply_text(
        "Receipt received for order " + order["order_id"] + ".\n"
        "We will verify and confirm soon."
    )


def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN is not set. Add it in Render Environment variables.")
        raise SystemExit(1)

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myid", myid))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(on_button))
    application.add_handler(MessageHandler(filters.CONTACT, on_contact))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
