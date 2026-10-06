# products.py — sync catalog from Firebase (same as website Admin)
import os
import json
import logging
import threading

logger = logging.getLogger(__name__)

# Fallback if Firebase is down (bot still works)
FALLBACK = [
    {"id": 49, "name": "ሳምንታዊ አስቤዛ · Weekly Asbeza", "cat": "Grocery",
     "price": 950, "sale": None, "photo": "photos/49.jpg", "builder": True},
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
        # website uses "photos/19.jpg" or "photos/19.jpeg"
        if photo and not photo.startswith("http") and not photo.startswith("photos/"):
            photo = "photos/" + photo.lstrip("/")
        sale = p.get("sale", None)
        if sale == "" or sale == "null":
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
    """Update lists in-place so bot.py keeps working."""
    with _lock:
        PRODUCTS.clear()
        PRODUCTS.extend(items if items else list(FALLBACK))
        PRODUCTS_BY_ID.clear()
        PRODUCTS_BY_ID.update({p["id"]: p for p in PRODUCTS})
        cats = sorted(set(p["cat"] for p in PRODUCTS if p.get("cat")))
        CATEGORIES.clear()
        CATEGORIES.extend(cats)
    logger.info("Catalog updated: %s products, %s categories", len(PRODUCTS), len(CATEGORIES))


def start_firebase_sync():
    """Call once from bot main(). Live-updates when website Admin saves."""
    _apply(FALLBACK)  # start with something safe

    try:
        import firebase_admin
        from firebase_admin import credentials, db
    except ImportError:
        logger.warning("firebase-admin not installed — using fallback PRODUCTS")
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
                logger.warning("No Firebase credentials — using fallback PRODUCTS")
                return
            firebase_admin.initialize_app(cred, {"databaseURL": database_url})

        def on_change(event):
            try:
                _apply(_normalize(event.data))
            except Exception as e:
                logger.exception("Firebase catalog update failed: %s", e)

        db.reference("products").listen(on_change)
        logger.info("Listening to Firebase /products …")
    except Exception as e:
        logger.exception("Firebase init failed: %s", e)
