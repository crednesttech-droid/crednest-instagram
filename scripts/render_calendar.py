#!/usr/bin/env python3
"""Render the Dec 2026 - Jan 2027 calendar stills (cards, carousels, stories) in the house layout.

Content lives in plans/content_dec_jan.py. Usage:
    python scripts/render_calendar.py [--only ID ...] [--from 2026-11-28 --to 2026-12-13]
"""
import argparse, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageCms

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_hooks_layout as L
from render_hooks_layout import Canvas, header, footer, headline, document, house, M, W, INK, PAPER, LIME, ROOT

sys.path.insert(0, str(ROOT / "plans"))
import content_dec_jan as C

BAR = {"CK": C.CK, "WA": C.WA}
PROPERTY = ("property", "lap", "home", "lease")
CYCLE = ["lime", "paper", "dark"]  # 27 Nov 2026 cover was dark, so 28 Nov starts lime


def feed_themes():
    feed = sorted((i for i in C.ITEMS if i["type"] in ("image", "carousel")), key=lambda i: (i["date"], i["slot"]))
    return {it["id"]: CYCLE[n % 3] for n, it in enumerate(feed)}


def mini_icon(c, it):
    x, y = 838, 45
    if any(k in it["kicker"].lower() for k in PROPERTY):
        house(c, x + 10, y + 9, 130, 102)
    else:
        document(c, x + 12, y, 128, 114, "₹")


def cta_colors(theme):
    return (INK, PAPER) if theme in {"paper", "lime"} else (LIME, INK)


def card(it, theme):
    c = Canvas(theme)
    header(c, it["kicker"])
    mini_icon(c, it)
    end, _, _ = headline(c, it["headline"], start=96)
    sub = c.wrap(it["sub"], 33, W - 2 * M, "Medium")
    assert len(sub) <= 2, it["id"]
    sub_end = c.lines((M, end + 22), sub, 33, 42, c.sub)
    y = max(620, sub_end + 40)
    step = (968 - y) / 3
    assert step >= 54, it["id"]
    psize, nsize = (36, 42) if step >= 75 else (33, 29)
    for n, p in enumerate(it["points"], 1):
        c.line((M, y - 14, W - M, y - 14))
        c.text((M, y), f"0{n}", nsize, c.accent, "Bold")
        assert c.width(p, psize, "Semibold") <= W - M - 180, p
        c.text((180, y + 3), p, psize, c.fg, "Semibold")
        y += step
    bg, fg = cta_colors(theme)
    c.rect((M, 1010, W - M, 1072), fill=bg, radius=10)
    assert c.width(BAR[it["cta"]], 31, "Bold") < W - 2 * M - 48
    c.text((M + 24, 1027), BAR[it["cta"]], 31, fg, "Bold")
    footer(c)
    return [c.save(ROOT / "media" / it["id"] / "01.jpg")]


def carousel(it, theme):
    total = len(it["slides"]) + 1
    c = Canvas(theme)
    header(c, it["kicker"], f"01 / {total:02}")
    end, _, _ = headline(c, it["headline"], start=104)
    sub = c.wrap(it["sub"], 33, W - 2 * M, "Medium")
    assert len(sub) <= 2, it["id"]
    sub_end = c.lines((M, end + 22), sub, 33, 42, c.sub)
    ay = max(700, sub_end + 34)
    ah = 1000 - ay
    assert ah >= 120, (it["id"], ah)
    c.rect((M, ay, W - M, ay + ah), fill=c.panel, radius=18)
    teaser = [t for s in it["slides"] for t, _ in s[1]][:3 if ah >= 200 else 2]
    step = (ah - 40) / len(teaser)
    size = 34 if step >= 60 else 30
    yy = ay + 20 + (step - size) / 2
    for n, t in enumerate(teaser, 1):
        c.text((M + 34, yy), f"0{n}", size, c.accent, "Bold")
        assert c.width(t, size, "Semibold") <= W - 2 * M - 150, t
        c.text((M + 110, yy), t, size, c.fg, "Semibold")
        yy += step
    c.text((M, 1042), "Swipe →", 30, c.accent, "Bold")
    footer(c)
    paths = [c.save(ROOT / "media" / it["id"] / "01.jpg")]
    inner = "dark" if theme == "dark" else "paper"
    for n, (title, pts) in enumerate(it["slides"], 2):
        last = not pts
        th = ("dark" if theme == "lime" else "lime") if last else inner
        c = Canvas(th)
        header(c, it["kicker"], f"{n:02} / {total:02}")
        end, _, _ = headline(c, title, start=96)
        if pts:
            for ts, ds, tl, dl, gap in ((42, 31, 52, 40, 52), (38, 29, 47, 37, 40), (36, 28, 44, 35, 30)):
                y0 = max(560, end + 70)
                need = sum(len(c.wrap(t, ts, W - M - 190, "Bold")) * tl + 8 + len(c.wrap(d, ds, W - M - 190, "Medium")) * dl + gap for t, d in pts)
                if y0 + need < 1080:
                    break
            y = y0
            for k, (t, d) in enumerate(pts, 1):
                c.text((M, y), f"0{k}", ts - 2, c.accent, "Extrabold")
                y2 = c.lines((190, y), c.wrap(t, ts, W - M - 190, "Bold"), ts, tl, c.fg, "Bold")
                y2 = c.lines((190, y2 + 8), c.wrap(d, ds, W - M - 190, "Medium"), ds, dl, c.sub)
                y = y2 + gap
                if k < len(pts):
                    c.line((M, y - gap / 2, W - M, y - gap / 2))
            assert y < 1080, (it["id"], n, y)
        else:
            mini_icon(c, it)
            bg, fg = cta_colors(th)
            yy = max(700, end + 80)
            c.rect((M, yy, W - M, yy + 92), fill=bg, radius=14)
            assert c.width(BAR[it["cta"]], 36, "Bold") < W - 2 * M - 60
            c.text((M + 30, yy + 26), BAR[it["cta"]], 36, fg, "Bold")
            c.text((M, yy + 140), "Save this post · Share it with your finance team", 30, c.sub, "Semibold")
        footer(c)
        paths.append(c.save(ROOT / "media" / it["id"] / f"{n:02}.jpg"))
    return paths


class Story(Canvas):
    H = 1920

    def __init__(self, theme):
        self.bg, self.fg, self.accent, self.sub, self.rule, self.panel = L.THEMES[theme]
        self.im = Image.new("RGB", (W * L.S, self.H * L.S), self.bg)
        self.d = ImageDraw.Draw(self.im)

    def save(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        self.im.resize((W, self.H), Image.Resampling.LANCZOS).save(path, "JPEG", quality=95, optimize=True, subsampling=0, icc_profile=srgb)
        return path.relative_to(ROOT).as_posix()


def story(it, theme):
    """Teaser for the day's post; all ink between y=290 and y=1650."""
    c = Story(theme)
    logo = Image.open(ROOT / "brand/04_Logos/CredNest_Icon_Source_Transparent_120.png").convert("RGBA")
    logo = logo.resize((72 * L.S, 72 * L.S), Image.Resampling.LANCZOS)
    c.im.paste(logo, (M * L.S, 300 * L.S), logo)
    c.text((182, 317), "CredNest", 42, weight="Bold")
    c.line((M, 404, W - M, 404))
    c.text((M, 440), ("TODAY · " + it["kicker"]).upper(), 27, c.accent, "Bold")
    end, _, _ = headline(c, it["headline"], y=500, start=104)
    sub = c.wrap(it["sub"], 38, W - 2 * M, "Medium")
    end = c.lines((M, end + 30), sub, 38, 50, c.sub)
    pts = it.get("points") or [t for s in it.get("slides", []) for t, _ in s[1]][:3]
    y = max(end + 70, 1000)
    for n, p in enumerate(pts, 1):
        c.line((M, y - 22, W - M, y - 22))
        c.text((M, y), f"0{n}", 40, c.accent, "Bold")
        assert c.width(p, 38, "Semibold") <= W - M - 190, p
        c.text((190, y + 2), p, 38, c.fg, "Semibold")
        y += 92
    assert y <= 1440, (it["id"], y)
    bg, fg = cta_colors(theme)
    c.rect((M, 1460, W - M, 1550), fill=bg, radius=14)
    c.text((M + 30, 1484), "New post on our feed today  →", 38, fg, "Bold")
    c.text((M, 1582), "crednest.io · WhatsApp +91 98199 99057", 28, c.fg, "Bold")
    c.text((M, 1622), "Not a lender or NBFC. Loan approval is at the lender's sole discretion.", 21, c.sub, "Medium")
    return [c.save(ROOT / "media" / (it["id"] + "-story") / "01.jpg")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--from", dest="start", default="0000")
    ap.add_argument("--to", dest="end", default="9999")
    a = ap.parse_args()
    themes = feed_themes()
    for it in C.ITEMS:
        if a.only and it["id"] not in a.only:
            continue
        if not (a.start <= it["date"] <= a.end):
            continue
        if it["type"] == "image":
            print(it["id"], card(it, themes[it["id"]]))
        elif it["type"] == "carousel":
            print(it["id"], carousel(it, themes[it["id"]]))
        if it.get("story"):
            print(it["id"] + "-story", story(it, "forest" if themes.get(it["id"]) == "dark" else "dark"))


if __name__ == "__main__":
    main()
