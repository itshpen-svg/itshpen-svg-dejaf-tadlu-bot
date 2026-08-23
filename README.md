# Dejaf Tadlu — Telegram Ordering Bot

A Telegram bot that lets customers browse your catalog, build a cart, and check
out — with the full order (items, quantities, subtotal, VAT, total, customer
name and address) sent straight to your Telegram as a message.

Unlike a plain "message us on Telegram" link, this bot actually fills in the
order for the customer automatically, the same way the WhatsApp button on your
website does.

---

## 1. Create the bot on Telegram

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts (choose a name and a username ending
   in `bot`, e.g. `DejafTadluBot`).
3. BotFather will reply with a **token** that looks like
   `123456789:ABCdefGhIJKlmNoPQRstuVWXyz`. Copy it.

## 2. Install and configure

Requires Python 3.10 or newer.

```bash
cd telegram-bot
python -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and paste your token:

```
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuVWXyz
OWNER_CHAT_ID=
```

Leave `OWNER_CHAT_ID` blank for now — you'll fill it in next.

## 3. Find your chat ID

1. Run the bot:
   ```bash
   python bot.py
   ```
2. Open Telegram, find your bot (search the username you gave it), and send
   `/myid`.
3. It will reply with your numeric chat ID. Copy it.
4. Stop the bot (Ctrl+C), paste that number into `.env` as `OWNER_CHAT_ID`,
   save, and run `python bot.py` again.

From now on, every completed order gets sent to that chat ID automatically.

## 4. Set up real payments (Chapa)

This lets customers pay directly through the bot via Telebirr, CBE Birr,
HelloCash, or card — money goes to your Chapa account, and the bot
automatically confirms the order to both you and the customer once payment
actually clears.

**Why Chapa and not Telebirr directly:** Telebirr's own merchant API requires
an enterprise agreement with Ethio Telecom, which isn't practically available
to an individual seller. Chapa is a payment aggregator that individuals can
sign up for online, and it accepts Telebirr (along with CBE Birr, HelloCash,
and cards) through one integration.

1. Go to **dashboard.chapa.co** and create an account.
2. Complete their verification steps (you'll need basic identity/business
   info — requirements can change, so follow whatever they currently ask for).
3. In your Chapa dashboard, find **API Keys** — copy the **Secret Key**. Use
   the **Test** key first so you can try the whole flow without real money
   moving, then switch to the **Live** key once you've confirmed everything
   works.
4. Add it to your `.env` (or Railway Variables) as `CHAPA_SECRET_KEY`.
5. **You also need a public URL** so Chapa can tell your bot when a payment
   succeeds:
   - **On Railway**: open your service → Settings → Networking → generate a
     public domain. Copy that URL (looks like
     `https://your-app-name.up.railway.app`) into `PUBLIC_URL` in your
     Variables (no trailing slash).
   - **Running locally**: Chapa can't reach `localhost`, so payments won't be
     able to confirm automatically unless you use a tool like `ngrok` to
     expose your local server, or just test this feature after you've
     deployed to Railway instead.
6. Redeploy / restart the bot so it picks up the new variables.

**How it works once set up:** after a customer gives their name and address,
instead of the order going straight to you, they get a **"💳 Pay Now"**
button. Once they pay, Chapa notifies your bot automatically, and *then* the
full order (marked ✅ PAID) gets sent to you — along with a confirmation to
the customer.

**If Chapa isn't configured, or its API is temporarily down:** the bot
doesn't lose the order. It falls back to sending you the order marked
"🕐 Awaiting payment" so you can follow up and arrange payment manually — the
same way it worked before payments were added.

## 5. Get every order in Telegram, even WhatsApp ones

By default, the website has two checkout buttons: **WhatsApp** and
**Telegram**. Telegram orders always land in your bot automatically. WhatsApp
orders only reach your WhatsApp — unless you turn on this optional mirror,
which sends a copy of every WhatsApp order to your Telegram too, so you only
have to check one place.

1. Pick any random string as a shared secret (e.g. generate one at
   randomkeygen.com, or just mash your keyboard for 20+ characters).
2. Add it to your bot's `.env` (or Railway Variables) as `WEBSITE_NOTIFY_SECRET`.
3. Open the website's `index.html`, find these two lines near the WhatsApp
   checkout code:
   ```javascript
   const BOT_NOTIFY_URL = ''; // e.g. 'https://your-app.up.railway.app/notify/website-order'
   const BOT_NOTIFY_SECRET = ''; // must match WEBSITE_NOTIFY_SECRET set on the bot
   ```
4. Fill in `BOT_NOTIFY_URL` with your Railway public URL + `/notify/website-order`,
   and `BOT_NOTIFY_SECRET` with the exact same string from step 2.
5. Save and re-upload `index.html` to Netlify.

Leave `BOT_NOTIFY_URL` blank if you'd rather keep WhatsApp and Telegram orders
separate — the website works fine either way.

**Security note:** the secret lives in the website's public code, so it's not
strong protection — anyone who reads the page source could find it and send
fake requests. It's enough to stop casual abuse, not a determined attacker.
Don't reuse a password you actually care about for this.

## 6. Product photos and the website link

The bot now shows real photos when customers browse a category — pulled
directly from the same photos already on your website (21 items currently
have them; the rest show as a text listing until you add photos for them).

- **The `photos/` folder must be uploaded to GitHub along with the other
  files** — Railway needs these files present to send them. If you forget
  this folder, those items will quietly fall back to a text listing instead
  of crashing (the bot handles a missing photo gracefully), but customers
  won't see the images.
- **Adding more photos later**: run `python extract_products.py index.html`
  again after updating the website — it re-pulls every photo currently
  embedded in the site into the `photos/` folder and updates `products.py`
  to match automatically.
- **The website link**: shown as a button in the bot's main menu. It defaults
  to `https://vocal-gelato-0382e0.netlify.app` — if you've renamed your
  Netlify site or bought a custom domain since then, update the `WEBSITE_URL`
  line near the top of `bot.py`, or set it as a `WEBSITE_URL` variable in
  Railway (which takes priority over the default in the code).

## 7. Try it

In Telegram, send `/start` to your bot. You should see:

- **Browse Categories** — pick a department, then tap an item to add it
- **View Cart** — see what's in the cart, adjust quantities, or checkout
- **Checkout** — the bot asks for your name and delivery address, then (if
  Chapa is configured) shows a **Pay Now** button. Tap it, complete a test
  payment using Chapa's test mode, and confirm the order lands in your
  Telegram marked ✅ PAID.

## Keeping the bot online

Running `python bot.py` on your own computer only works while that computer
is on and connected. For a bot that's always reachable, deploy it somewhere
that runs 24/7. A few free or cheap options:

- **Railway.app** — connect your GitHub repo, add the same environment
  variables from `.env`, and it runs continuously on a free tier.
- **Render.com** — similar to Railway; deploy as a "Background Worker."
- **A small VPS** (e.g. a $5/month DigitalOcean droplet) — most control, but
  requires basic Linux server setup.

If you'd like, I can walk you through deploying to any of these once you're
ready.

## Keeping the catalog in sync with the website

`products.py` was generated from your website's product list at the time this
bot was built. If you add, remove, or reprice items on the website later,
either:

- Re-run `extract_products.py` against the latest `tadlu-store.html`
  (regenerates `products.py` automatically), or
- Edit `products.py` by hand — it's a plain Python list, safe to edit directly.

## Limitations to know about

- **Carts are stored in memory** — if the bot restarts, everyone's current
  cart is cleared. Fine for a small shop; ask me if you want this made
  persistent later (e.g. saved to a file or database).
- **Pending orders are also in-memory** — if the bot restarts between a
  customer starting a payment and completing it, that specific in-progress
  payment record is lost (Chapa itself still has the transaction, but the bot
  won't automatically match the confirmation back to the customer). This is
  rare in practice but worth knowing about.
- **Placeholder email**: Chapa requires an email field, but Telegram doesn't
  give the bot the customer's real email. A placeholder like
  `user12345@dejaftadlu.et` is used instead — it satisfies Chapa's format
  requirement but isn't a real inbox. If Chapa ever emails customers a
  receipt, they won't receive it. Ask me if you'd like the bot to collect a
  real email during checkout instead.
- **Single admin** — orders go to one `OWNER_CHAT_ID`. If you want a second
  person to also receive orders (e.g. a staff member), ask and I can extend
  it to notify multiple chat IDs.
