# products.py — full catalog fallback + Firebase live sync
import os
import json
import logging
import threading

logger = logging.getLogger(__name__)

# Full catalog (same idea as website). Used if Firebase is empty/unavailable.
FALLBACK = [
    {"id": 1, "name": "Yirgacheffe Coffee Beans, 250g", "cat": "Coffee & Tea", "price": 380, "sale": None, "photo": "photos/1.jpg", "builder": False},
    {"id": 2, "name": "Black seeds For Healthy", "cat": "Beauty & Cosmetics", "price": 1200, "sale": None, "photo": "photos/2.jpg", "builder": False},
    {"id": 13, "name": "Amharic Children's Storybook Set", "cat": "Books & Paper", "price": 260, "sale": None, "photo": "photos/13.jpg", "builder": False},
    {"id": 14, "name": "Frankincense & Myrrh Set", "cat": "Home & Garden", "price": 180, "sale": None, "photo": "photos/14.jpg", "builder": False},
    {"id": 17, "name": "Woven Mesob Basket", "cat": "Home & Garden", "price": 1400, "sale": None, "photo": "photos/17.jpg", "builder": False},
    {"id": 19, "name": "Teff Flour, 5kg", "cat": "Grocery", "price": 620, "sale": None, "photo": "photos/19.jpg", "builder": False},
    {"id": 20, "name": "Fresh Avocados, 1kg Bag", "cat": "Grocery", "price": 110, "sale": None, "photo": "photos/20.jpg", "builder": False},
    {"id": 21, "name": "Shiro Powder (ሽሮ), 500g", "cat": "Grocery", "price": 170, "sale": None, "photo": "photos/21.jpg", "builder": False},
    {"id": 22, "name": "Ethiopian Kibe Butter, 250g", "cat": "Grocery", "price": 210, "sale": None, "photo": "photos/22.jpg", "builder": False},
    {"id": 23, "name": "Shea Butter Body Cream", "cat": "Beauty & Cosmetics", "price": 240, "sale": None, "photo": "photos/23.jpg", "builder": False},
    {"id": 24, "name": "Natural Henna Powder, 100g", "cat": "Beauty & Cosmetics", "price": 130, "sale": None, "photo": "photos/24.jpg", "builder": False},
    {"id": 25, "name": "Matte Lipstick Set", "cat": "Beauty & Cosmetics", "price": 390, "sale": None, "photo": "photos/25.jpg", "builder": False},
    {"id": 26, "name": "Voltage Stabilizer, 1000VA", "cat": "Electrical Equipment", "price": 1850, "sale": None, "photo": "photos/26.jpg", "builder": False},
    {"id": 27, "name": "LED Bulb Pack, 4 x 9W", "cat": "Electrical Equipment", "price": 340, "sale": None, "photo": "photos/27.jpg", "builder": False},
    {"id": 28, "name": "Rechargeable Emergency Lamp", "cat": "Electrical Equipment", "price": 590, "sale": None, "photo": "photos/28.jpg", "builder": False},
    {"id": 29, "name": "Potatoes (ድንች), 1kg", "cat": "Grocery", "price": 45, "sale": None, "photo": "photos/29.jpg", "builder": False},
    {"id": 30, "name": "Carrots (ካሮት), 1kg", "cat": "Grocery", "price": 55, "sale": None, "photo": "photos/30.jpg", "builder": False},
    {"id": 31, "name": "Cabbage (ጎመን), 1 head", "cat": "Grocery", "price": 40, "sale": None, "photo": "photos/31.jpg", "builder": False},
    {"id": 32, "name": "Onions (ሽንኩርት), 1kg", "cat": "Grocery", "price": 65, "sale": None, "photo": "photos/32.jpg", "builder": False},
    {"id": 33, "name": "Garlic (ነጭ ሽንኩርት), 250g", "cat": "Grocery", "price": 90, "sale": None, "photo": "photos/33.jpg", "builder": False},
    {"id": 34, "name": "Tomatoes (ቲማቲም), 1kg", "cat": "Grocery", "price": 70, "sale": 60, "photo": "photos/34.jpg", "builder": False},
    {"id": 35, "name": "Cooking Oil (ዘይት), 1L", "cat": "Grocery", "price": 260, "sale": None, "photo": "photos/35.jpg", "builder": False},
    {"id": 38, "name": "Kids Pajama Set, Assorted Prints", "cat": "Apparel", "price": 480, "sale": None, "photo": "photos/38.jpg", "builder": False},
    {"id": 39, "name": "Kids Pajama Pants, Assorted Prints", "cat": "Apparel", "price": 260, "sale": None, "photo": "photos/39.jpg", "builder": False},
    {"id": 40, "name": "Girls Leggings, Navy & Lilac", "cat": "Apparel", "price": 320, "sale": None, "photo": "photos/40.jpg", "builder": False},
    {"id": 41, "name": "Eau de Parfum, For Women", "cat": "Beauty & Cosmetics", "price": 950, "sale": None, "photo": "photos/41.jpg", "builder": False},
    {"id": 42, "name": "Eau de Parfum, For Men, 50ml", "cat": "Beauty & Cosmetics", "price": 850, "sale": None, "photo": "photos/42.jpg", "builder": False},
    {"id": 43, "name": "Men's Pullover Hoodie", "cat": "Apparel", "price": 900, "sale": None, "photo": "photos/43.jpg", "builder": False},
    {"id": 44, "name": "Men's Pique Polo Shirt", "cat": "Apparel", "price": 650, "sale": None, "photo": "photos/44.jpg", "builder": False},
    {"id": 45, "name": "Men's Boxer Shorts, Assorted Patterns (6-Pack)", "cat": "Apparel", "price": 780, "sale": None, "photo": "photos/45.jpg", "builder": False},
    {"id": 46, "name": "Executive Gift Box", "cat": "Gift Packages", "price": 3000, "sale": None, "photo": "photos/46.jpg", "builder": False},
    {"id": 47, "name": "Birthday Gift Box", "cat": "Gift Packages", "price": 3500, "sale": None, "photo": "photos/47.jpg", "builder": False},
    {"id": 48, "name": "Celebration Gift Box", "cat": "Gift Packages", "price": 4000, "sale": None, "photo": "photos/48.jpg", "builder": False},
    {"id": 49, "name": "ሳምንታዊ አስቤዛ · Weekly Asbeza", "cat": "Grocery", "price": 950, "sale": None, "photo": "photos/49.jpg", "builder": True},
    {"id": 50, "name": "Beso (በሶ), 1kg", "cat": "Grocery", "price": 180, "sale": None, "photo": "photos/50.jpg", "builder": False},
    {"id": 51, "name": "Aja (አጃ), 1kg", "cat": "Grocery", "price": 160, "sale": None, "photo": "photos/51.jpg", "builder": False},
    {"id": 52, "name": "Rice (ሩዝ), 1kg", "cat": "Grocery", "price": 220, "sale": None, "photo": "photos/52.jpg", "builder": False},
    {"id": 53, "name": "Qinche (ቅንጨ), 1kg", "cat": "Grocery", "price": 170, "sale": None, "photo": "photos/53.jpg", "builder": False},
    {"id": 54, "name": "Difen Misir (ድፍን ምስር), 1kg", "cat": "Grocery", "price": 200, "sale": None, "photo": "photos/54.jpg", "builder": False},
    {"id": 55, "name": "Split Misir (ምስር ክክ), 1kg", "cat": "Grocery", "price": 210, "sale": None, "photo": "photos/55.jpg", "builder": False},
    {"id": 56, "name": "Split Ater (አተር ክክ), 1kg", "cat": "Grocery", "price": 190, "sale": None, "photo": "photos/56.jpg", "builder": False},
    {"id": 60, "name": "Peanut Butter (የለውዝ ቅቤ), 500g", "cat": "Grocery", "price": 280, "sale": None, "photo": "photos/60.jpg", "builder": False},
]

PRODUCTS = []
CATEGORIES = []
PRODUCTS_BY_ID = {}
_lock = threading.Lock()


def _normalize(val):
    if not val:
        return []
    if isinstance(val, list):
        raw = [x for x in val if isinstance(x, dict)]
    elif isinstance(val, dict):
        raw = [v for v in val.values() if isinstance(v, dict)]
    else:
        return []

    out = []
    for p in raw:
        try:
            pid = int(p.get("id", 0))
        except (TypeError, ValueError):
            continue
        if not pid:
            continue
        photo = (p.get("photo") or p.get("img") or "").strip()
        if photo and not photo.startswith("http") and not photo.startswith("photos/"):
            photo = "photos/" + photo.lstrip("/")
        sale = p.get("sale", None)
        if sale in ("", "null"):
            sale = None
        out.append({
            "id": pid,
            "name": p.get("name") or "Item",
            "cat": p.get("cat") or "Grocery",
            "price": p.get("price") or 0,
            "sale": sale,
            "photo": photo,
            "builder": bool(p.get("builder", False)),
        })
    out.sort(key=lambda x: x["id"])
    return out


def _apply(items):
    with _lock:
        PRODUCTS.clear()
        PRODUCTS.extend(items if items else list(FALLBACK))
        PRODUCTS_BY_ID.clear()
        PRODUCTS_BY_ID.update({p["id"]: p for p in PRODUCTS})
        cats = sorted(set(p["cat"] for p in PRODUCTS if p.get("cat")))
        CATEGORIES.clear()
        CATEGORIES.extend(cats)
    logger.info(
        "Catalog updated: %s products, categories=%s",
        len(PRODUCTS),
        ", ".join(CATEGORIES),
    )


def start_firebase_sync():
    # Always start with full local catalog so bot is never empty
    _apply(FALLBACK)

    try:
        import firebase_admin
        from firebase_admin import credentials, db
    except ImportError:
        logger.warning("firebase-admin not installed — using full local FALLBACK")
        return

    database_url = os.environ.get(
        "FIREBASE_DATABASE_URL",
        "https://dejaf-tadlu-default-rtdb.firebaseio.com",
    )

    try:
        if not firebase_admin._apps:
            sa = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
            if sa:
                cred = credentials.Certificate(json.loads(sa))
            elif os.path.exists("serviceAccount.json"):
                cred = credentials.Certificate("serviceAccount.json")
            else:
                logger.warning("No Firebase credentials — using full local FALLBACK")
                return
            firebase_admin.initialize_app(cred, {"databaseURL": database_url})

        def on_change(event):
            try:
                items = _normalize(event.data)
                # Only replace local catalog if Firebase has a real full list
                if items and len(items) >= 5:
                    _apply(items)
                else:
                    logger.warning(
                        "Firebase products empty/small (%s) — keeping local FALLBACK",
                        len(items) if items else 0,
                    )
            except Exception as e:
                logger.exception("Firebase catalog update failed: %s", e)

        db.reference("products").listen(on_change)
        logger.info("Listening to Firebase /products …")
    except Exception as e:
        logger.exception("Firebase init failed: %s", e)
