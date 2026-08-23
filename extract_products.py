"""
Regenerates products.py (and the photos/ folder) from the website's
index.html catalog.

Usage:
    python extract_products.py path/to/index.html

Run this any time you update the product list or photos on the website and
want the Telegram bot to match it.

Handles two kinds of product images, since the site now uses both:
  - Embedded photos:  img:'data:image/jpeg;base64,...'   -> decoded and saved
    into photos/<id>.jpg automatically.
  - Plain filenames:  img:'gift-package-daniel.jpg'       -> NOT auto-copied,
    since the actual file lives outside the HTML. You need to manually place
    a matching file at photos/<that exact filename> yourself (the script will
    warn you about any that are missing).
"""

import re
import os
import base64
import sys


def extract(html_path: str, out_path: str = "products.py", photos_dir: str = "photos"):
    html = open(html_path, encoding="utf-8").read()

    m = re.search(r"const PRODUCTS = \[(.*?)\n  \];", html, re.S)
    if not m:
        raise SystemExit("Could not find the PRODUCTS array in that file.")
    block = m.group(1)

    pattern = re.compile(
        r"\{\s*id:(\d+),\s*name:(?:'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"),"
        r"\s*cat:'((?:[^'\\]|\\.)*)',\s*price:(\d+),\s*sale:(null|\d+)"
        r"(?:,\s*builder:(true|false))?"
    )

    products = []
    for pid, name1, name2, cat, price, sale, builder in pattern.findall(block):
        name = (name1 or name2).replace("\\'", "'")
        cat = cat.replace("\\'", "'")
        products.append(
            {
                "id": int(pid),
                "name": name,
                "cat": cat,
                "price": int(price),
                "sale": None if sale == "null" else int(sale),
                "builder": builder == "true",
            }
        )

    os.makedirs(photos_dir, exist_ok=True)
    photo_map = {}       # id -> photos/<file>
    missing_files = []   # plain filenames referenced but not found in photos_dir

    for id_match in re.finditer(r"\{\s*id:(\d+),", html):
        pid = int(id_match.group(1))
        window = html[id_match.start(): id_match.start() + 120000]
        end = window.find("},\n")
        entry = window[:end] if end != -1 else window

        b64_match = re.search(r"img:'data:image/jpeg;base64,([A-Za-z0-9+/=]+)'", entry)
        if b64_match:
            data = base64.b64decode(b64_match.group(1))
            fname = f"{pid}.jpg"
            with open(os.path.join(photos_dir, fname), "wb") as f:
                f.write(data)
            photo_map[pid] = f"{photos_dir}/{fname}"
            continue

        plain_match = re.search(r"img:'([^'\"]+\.(?:jpg|jpeg|png))'", entry)
        if plain_match:
            fname = plain_match.group(1)
            local_path = os.path.join(photos_dir, fname)
            if os.path.isfile(local_path):
                photo_map[pid] = f"{photos_dir}/{fname}"
            else:
                missing_files.append((pid, fname))

    lines = [
        "# Auto-generated from the Dejaf Tadlu website catalog.",
        "# Re-run extract_products.py against index.html any time the site catalog changes,",
        "# or edit this list by hand -- either way keeps the bot and the site in sync.",
        "#",
        "# 'photo' points to a file in the photos/ folder (only present for items with a real",
        "# photo; items without one fall back to text-only display in the bot).",
        "# 'builder' flags interactive website-only features (like the weekly basket builder) --",
        "# the bot sells these as a normal fixed-price item since it can't replicate that UI.",
        "",
        "PRODUCTS = [",
    ]
    for p in products:
        name = p["name"].replace("\\", "\\\\").replace('"', '\\"')
        cat = p["cat"].replace('"', '\\"')
        sale = "None" if p["sale"] is None else str(p["sale"])
        photo = photo_map.get(p["id"])
        photo_str = f'"{photo}"' if photo else "None"
        lines.append(
            f'    {{"id": {p["id"]}, "name": "{name}", "cat": "{cat}", "price": {p["price"]}, '
            f'"sale": {sale}, "photo": {photo_str}, "builder": {p["builder"]}}},'
        )
    lines.append("]")
    lines.append("")
    lines.append("CATEGORIES = sorted(set(p['cat'] for p in PRODUCTS))")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Wrote {len(products)} products ({len(photo_map)} with photos) to {out_path}")
    if missing_files:
        print("\nWARNING: these products reference an image file not found in photos/:")
        for pid, fname in missing_files:
            print(f"  - product id {pid}: {fname}")
        print("Add these files to photos/ and re-run this script to include them.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python extract_products.py path/to/index.html")
    extract(sys.argv[1])
