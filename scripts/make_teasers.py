#!/usr/bin/env python3
"""Auto teaser stories: one story card 20 min after every feed post.

For each feed item (image / carousel / reel) in the next N days that has no story
pointing at it, render media/<id>-teaser/01.jpg (1080x1920, house style: lockup,
"NAYA REEL" kicker, the post's cover as a card, "Profile pe dekho") and add a story
item with `requires: <id>`. The autopilot posts it only after the feed post is live.

  python scripts/make_teasers.py            next 21 days
  python scripts/make_teasers.py --days 35
"""
import argparse, json, os
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "queue.json")
IST_OFF = "+05:30"
LIME, INK, DARK, PAPER, LIGHT = (184, 255, 90), (7, 21, 15), (13, 33, 25), (248, 248, 244), (188, 205, 196)
F = lambda w, s: ImageFont.truetype(os.path.join(ROOT, "brand", "03_Fonts", f"Manrope-{w}.ttf"), s)
ICON = Image.open(os.path.join(ROOT, "brand", "04_Logos", "CredNest_Icon_Source_Transparent_120.png")).convert("RGBA")
FEED = ("image", "carousel", "reel")


def cover_of(it):
    p = it.get("cover") if it["type"] == "reel" else (it["media"][0] if it.get("media") else None)
    p = p and os.path.join(ROOT, p)
    return p if p and os.path.exists(p) else None


def render(it, out):
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    for r in (300, 440, 580):                                   # brand ring motif
        d.ellipse([900 - r, 1650 - r, 900 + r, 1650 + r], outline=(22, 48, 37), width=4)
    ic = ICON.resize((64, 64), Image.LANCZOS)
    img.paste(ic, (90, 270), ic)
    d.text((90 + 82, 302), "CredNest", font=F("Extrabold", 44), anchor="lm", fill=PAPER)
    d.text((90, 380), "NAYA REEL" if it["type"] == "reel" else "NAYA POST", font=F("Bold", 40), fill=LIME)
    src = Image.open(cover_of(it)).convert("RGB")
    cw = 700
    ch = int(src.height * cw / src.width)
    ch = min(ch, 960)
    card = src.resize((cw, int(src.height * cw / src.width)), Image.LANCZOS).crop((0, 0, cw, ch))
    x, y = (W - cw) // 2, 460
    d.rounded_rectangle([x - 6, y - 6, x + cw + 6, y + ch + 6], 28, fill=LIME)
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw, ch], 24, fill=255)
    img.paste(card, (x, y), mask)
    ty = y + ch + 60
    d.text((W // 2, ty), "Profile pe dekho", font=F("Extrabold", 64), anchor="mt", fill=PAPER)
    d.text((W // 2, ty + 90), "@crednest.io", font=F("Bold", 44), anchor="mt", fill=LIME)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out, quality=90)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21)
    a = ap.parse_args()
    q = json.load(open(QUEUE, encoding="utf-8"))
    linked = {i.get("requires") for i in q if i["type"] == "story"}
    ids = {i["id"] for i in q}
    now = datetime.now().astimezone()
    end = now + timedelta(days=a.days)
    added = 0
    for it in list(q):
        if it["type"] not in FEED or it["status"] not in ("ready", "needs_voice", "review"):
            continue
        t = datetime.fromisoformat(it["publish_at"])
        if not now < t < end or it["id"] in linked or f"{it['id']}-teaser" in ids or not cover_of(it):
            continue
        sid = f"{it['id']}-teaser"
        render(it, os.path.join(ROOT, "media", sid, "01.jpg"))
        q.append({"id": sid, "type": "story", "publish_at": (t + timedelta(minutes=20)).isoformat(),
                  "media": [f"media/{sid}/01.jpg"], "caption": "", "status": "ready", "requires": it["id"],
                  "source": "auto teaser (scripts/make_teasers.py)"})
        added += 1
        print("teaser", sid, (t + timedelta(minutes=20)).strftime("%d %b %H:%M"))
    with open(QUEUE, "w", encoding="utf-8") as f:
        json.dump(q, f, indent=1, ensure_ascii=False); f.write("\n")
    print(f"{added} teaser stories added")


if __name__ == "__main__":
    main()
