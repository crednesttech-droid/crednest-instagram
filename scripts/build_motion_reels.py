#!/usr/bin/env python3
"""Faceless motion-graphics reels in the CredNest house style (content v3).

No stock footage needed: brand colours, Manrope, kinetic type. Frame 1 is the hook.
Specs live in reels_v3/specs.json; timing comes from each item's voice_scenes in queue.json.

  python scripts/build_motion_reels.py                 build every spec
  python scripts/build_motion_reels.py --only N07      one reel
  python scripts/build_motion_reels.py --frames N07    write preview PNGs only

Output: media/<id>/reel.mp4 (silent, 1080x1920, 30 fps, H.264) + media/<id>/cover.jpg.
Voice + music are added afterwards by the "Re-voice reels (Sarvam)" workflow.
"""
import argparse, json, math, os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H, FPS = 1080, 1920, 30
C = dict(lime=(184, 255, 90), ink=(7, 21, 15), dark=(13, 33, 25), forest=(49, 87, 70),
         paper=(248, 248, 244), mint=(157, 243, 197), light=(188, 205, 196), white=(255, 255, 255))
FONT = os.path.join(ROOT, "brand", "03_Fonts", "Manrope-{}.ttf")
DISCLAIMER = "CredNest is a debt-capital facilitator, not a lender or NBFC. Loan approval and terms are at the lender's sole discretion."
X0, TOP, BOTTOM = 90, 270, 1500          # safe zone: 250 px top, 420 px bottom
ICON = Image.open(os.path.join(ROOT, "brand", "04_Logos", "CredNest_Icon_Source_Transparent_120.png")).convert("RGBA")
_fc = {}


def font(w, s):
    k = (w, s)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(FONT.format(w), s)
    return _fc[k]


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def wrap(text, f, width):
    """Word-wrap; an explicit newline in the text forces a break."""
    lines = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split():
            t = (cur + " " + w).strip()
            if f.getlength(t) <= width or not cur:
                cur = t
            else:
                lines.append(cur); cur = w
        if cur:
            lines.append(cur)
    return lines


def draw_lines(d, lines, f, x, y, fill, hi=(), hi_fill=None, lh=1.12, alpha_img=None):
    """Draw wrapped lines; words in `hi` (case-insensitive, punctuation stripped) get hi_fill."""
    hiset = {h.lower() for h in hi}
    step = int(f.size * lh)
    for ln in lines:
        cx = x
        for w in ln.split(" "):
            key = w.strip(".,?!:;'\"").lower()
            d.text((cx, y), w, font=f, fill=hi_fill if (hi_fill and key in hiset) else fill)
            cx += f.getlength(w + " ")
        y += step
    return y


def background(img, t, mode):
    d = ImageDraw.Draw(img)
    if mode == "paper":
        d.rectangle([0, 0, W, H], fill=C["paper"])
        ring = C["line"] if "line" in C else (217, 224, 217)
        col = (225, 232, 225)
    else:
        d.rectangle([0, 0, W, H], fill=C["dark"] if mode == "dark" else C["ink"])
        col = (22, 48, 37)
    # slow-drifting rings for constant subtle motion
    cx, cy = 860 + 60 * math.sin(t * 0.6), 1500 + 40 * math.cos(t * 0.5)
    for r in (260, 380, 500, 620):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=3)
    # diagonal hairlines drifting up
    off = int(t * 40) % 120
    for k in range(-20, 30):
        y = k * 120 - off
        d.line([(0, y), (W, y - 300)], fill=col, width=1)


def lockup(img, x, y, size=72, ink=False):
    """Brand-kit lockup: original icon (never recoloured, <=120 px) + Manrope ExtraBold wordmark."""
    icon = ICON.resize((size, size), Image.LANCZOS) if size != 120 else ICON
    img.paste(icon, (x, y), icon)
    d = ImageDraw.Draw(img)
    f = font("Extrabold", int(size * 50 / 72))
    d.text((x + int(size * 92 / 72), y + size // 2), "CredNest", font=f, anchor="lm",
           fill=C["ink"] if ink else C["paper"])


def header(img, d, spec, t, total, ink=False):
    tag_col = C["forest"] if ink else C["lime"]
    lockup(img, X0, TOP, 64, ink)
    d.text((X0, TOP + 96), spec["series"], font=font("Bold", 34), fill=tag_col)
    if t >= 2.0:
        lab = "Illustrative example"
        f = font("Medium", 28)
        d.text((W - X0 - f.getlength(lab), TOP + 100), lab, font=f, fill=C["forest"] if ink else C["light"])
    # progress bar
    y = TOP + 152
    d.rectangle([X0, y, W - X0, y + 6], fill=(217, 224, 217) if ink else (31, 60, 47))
    d.rectangle([X0, y, X0 + int((W - 2 * X0) * min(1, t / total)), y + 6], fill=C["forest"] if ink else C["lime"])


def caption(d, text, local, dur, ink=False):
    """Spoken line, word by word, current word in lime."""
    words = text.split()
    n = max(1, len(words))
    shown = min(n, int(ease(local / max(0.3, dur * 0.8)) * n) + 1)
    f = font("Semibold", 46)
    lines = wrap(" ".join(words[:shown]), f, W - 2 * X0)
    y = 1230 - (len(lines) - 1) * 56
    for i, ln in enumerate(lines):
        cx = X0
        ws = ln.split(" ")
        for j, w in enumerate(ws):
            last = (i == len(lines) - 1 and j == len(ws) - 1)
            col = (C["forest"] if ink else C["lime"]) if last else (C["ink"] if ink else C["white"])
            d.text((cx, y), w, font=f, fill=col)
            cx += f.getlength(w + " ")
        y += 56


def footer(d, ink=False):
    d.text((X0, 1430), "crednest.io", font=font("Semibold", 36), fill=C["ink"] if ink else C["white"])


def phone(img, d, sc, local):
    """POV phone: hook line above, phone with notification + chat bubbles that pop in on cue."""
    f = font("Extrabold", 70)
    y = draw_lines(d, wrap(sc.get("big", ""), f, W - 2 * X0), f, X0, 430, C["white"], hi=sc.get("hi", ()), hi_fill=C["lime"], lh=1.08)
    px, py, pw, ph = 160, max(y + 30, 600), 760, 1500 - max(y + 30, 600) + 260
    d.rounded_rectangle([px, py, px + pw, py + ph], 70, fill=(2, 8, 6), outline=(49, 87, 70), width=6)
    d.rounded_rectangle([px + 300, py + 22, px + 460, py + 52], 15, fill=(20, 30, 26))      # notch
    d.rounded_rectangle([px + 24, py + 70, px + pw - 24, py + ph - 24], 48, fill=(16, 26, 22))
    by = py + 100
    for b in sc.get("bubbles", []):
        if local < b.get("at", 0):
            break
        a = ease((local - b.get("at", 0)) / 0.25)
        side, text = b.get("side", "in"), b["text"]
        fb = font("Bold" if side == "notif" else "Semibold", 40 if side != "notif" else 36)
        lines = wrap(text, fb, pw - 170)
        bh = 36 + len(lines) * 50 + (40 if side == "notif" else 0)
        bw = min(pw - 90, max(fb.getlength(l) for l in lines) + 70)
        if side == "notif":
            bx, col, tc = px + 45, (238, 241, 238), C["ink"]
            bw = pw - 90
        elif side == "out":
            bx, col, tc = px + pw - 45 - bw, C["lime"], C["ink"]
        else:
            bx, col, tc = px + 45, (40, 62, 52), C["white"]
        oy = int((1 - a) * -40)
        d.rounded_rectangle([bx, by + oy, bx + bw, by + bh + oy], 30, fill=col)
        ty = by + 18 + oy
        if side == "notif":
            d.text((bx + 30, ty), b.get("title", "Lender update"), font=font("Extrabold", 30), fill=C["forest"])
            ty += 42
        for l in lines:
            d.text((bx + 34, ty), l, font=fb, fill=tc)
            ty += 50
        by += bh + 26


def scene_frame(spec, sc, local, t, total):
    kind = sc["kind"]
    if kind == "list":   # fast colour flips for pattern interrupt
        mode = sc.get("bg", "ink")
        img = Image.new("RGB", (W, H), {"ink": C["ink"], "forest": C["forest"], "lime": C["lime"], "paper": C["paper"]}[mode])
        d = ImageDraw.Draw(img)
        ink = mode in ("lime", "paper")
        header(img, d, spec, t, total, ink)
        sc_ = 0.85 + 0.15 * ease(local / 0.18)
        size = int(sc.get("size", 120) * sc_)
        f = font("Extrabold", size)
        lines = wrap(sc["big"], f, W - 2 * X0)
        y = 900 - len(lines) * size * 0.55
        if sc.get("num"):
            d.text((X0, y - 250), sc["num"], font=font("Extrabold", 220), fill=C["ink"] if ink else C["lime"])
        draw_lines(d, lines, f, X0, int(y), C["ink"] if ink else C["white"], hi=sc.get("hi", ()),
                   hi_fill=C["forest"] if ink else C["lime"], lh=1.06)
        if sc.get("sub"):
            d.text((X0, 1250), sc["sub"], font=font("Bold", 50), fill=C["ink"] if ink else C["mint"])
        footer(d, ink)
        return img
    mode = "paper" if kind == "takeaway" else ("dark" if kind == "end" else "ink")
    ink = mode == "paper"
    img = Image.new("RGB", (W, H))
    background(img, t, mode)
    d = ImageDraw.Draw(img)
    header(img, d, spec, t, total, ink)
    a = ease(local / 0.35)                     # entrance progress
    dy = int((1 - a) * 60)

    if kind == "phone":
        phone(img, d, sc, local)
        return img
    if kind == "hook":
        size = 118   # shrink until no explicit line has to wrap
        while size > 80 and any(font("Extrabold", size).getlength(l) > W - 2 * X0
                                for part in (sc["big"], sc.get("big2", "")) for l in part.split("\n")):
            size -= 4
        f = font("Extrabold", size)
        y = 520
        for part, col in ((sc["big"], C["white"]), (sc.get("big2", ""), C["lime"])):
            if not part:
                continue
            lines = wrap(part, f, W - 2 * X0)
            y = draw_lines(d, lines, f, X0, y, col, lh=1.08) + 20
        bar = int((W - 2 * X0) * ease((local - 0.3) / 0.6))
        if bar > 4:   # frame 1 (the cover) stays clean
            d.rectangle([X0, y + 10, X0 + bar, y + 22], fill=C["lime"])
        footer(d)
    elif kind == "beat":
        if sc.get("num"):
            fn = font("Extrabold", 300)
            d.text((X0 - int((1 - a) * 200), 470), sc["num"], font=fn, fill=C["lime"])
        f = font("Extrabold", 100)
        lines = wrap(sc["big"], f, W - 2 * X0)
        y = draw_lines(d, lines, f, X0, 830 + dy, C["white"], hi=sc.get("hi", ()), hi_fill=C["lime"], lh=1.1)
        if sc.get("sub"):
            d.text((X0, y + 18 + dy), sc["sub"], font=font("Semibold", 52), fill=C["mint"])
        if local > 1.6:   # second change inside the beat
            u = ease((local - 1.6) / 0.4)
            d.rectangle([X0, 800, X0 + int(260 * u), 812], fill=C["lime"])
        caption(d, sc["text"], local, sc["end"] - sc["start"])
        footer(d)
    elif kind == "timeline":
        f = font("Extrabold", 92)
        draw_lines(d, wrap(sc["big"], f, W - 2 * X0), f, X0, 500 + dy, C["white"], hi=sc.get("hi", ()), hi_fill=C["lime"])
        y0, x1, x2 = 760, X0, W - X0
        span = x2 - x1
        u = ease(local / 1.2)
        d.text((x1, y0 - 70), "Supplier ko payment", font=font("Semibold", 38), fill=C["light"])
        d.rectangle([x1, y0, x1 + int(span / 2 * u), y0 + 40], fill=C["forest"])
        d.text((x1, y0 + 120), "Customer se paisa", font=font("Semibold", 38), fill=C["light"])
        d.rectangle([x1, y0 + 190, x1 + int(span * u), y0 + 230], fill=C["forest"])
        if local > 1.0:
            g = ease((local - 1.0) / 0.6)
            d.rectangle([x1 + span // 2, y0 + 190, x1 + span // 2 + int(span / 2 * g), y0 + 230], fill=C["lime"])
            d.text((x1 + span // 2, y0 + 290), "30 din ka gap", font=font("Extrabold", 54), fill=C["lime"])
        for lab, xx in (("0", x1), ("30", x1 + span // 2), ("60 din", x2 - 120)):
            d.text((xx, y0 + 245), lab, font=font("Medium", 32), fill=C["light"])
        caption(d, sc["text"], local, sc["end"] - sc["start"])
        footer(d)
    elif kind == "takeaway":
        f = font("Extrabold", 100)
        lines = wrap(sc["big"], f, W - 2 * X0)
        draw_lines(d, lines, f, X0, 560 + dy, C["ink"], hi=sc.get("hi", ()), hi_fill=C["forest"], lh=1.1)
        caption(d, sc["text"], local, sc["end"] - sc["start"], ink=True)
        footer(d, ink=True)
    elif kind == "end":
        f = font("Extrabold", 96)
        y = draw_lines(d, wrap(sc["big"], f, W - 2 * X0), f, X0, 560 + dy, C["lime"], lh=1.08)
        if sc.get("sub"):
            y = draw_lines(d, wrap(sc["sub"], font("Bold", 56), W - 2 * X0), font("Bold", 56), X0, y + 30, C["white"])
        d.text((X0, y + 50), "Independent advice. Lender-led decisions.", font=font("Medium", 34), fill=C["light"])
        footer(d)
        fd = font("Regular", 28)
        draw_lines(d, wrap(DISCLAIMER, fd, W - 2 * X0), fd, X0, 1340, C["light"], lh=1.3)
    return img


def render(item, spec, out_dir, preview=False):
    scenes = spec["scenes"]
    for sc, vs in zip(scenes, item["voice_scenes"]):
        sc["start"], sc["end"], sc["text"] = vs["start"], vs["end"], vs["text"]
    total = scenes[-1]["end"]
    os.makedirs(out_dir, exist_ok=True)
    if preview:
        for i, sc in enumerate(scenes):
            for k, lt in enumerate((0.0, (sc["end"] - sc["start"]) * 0.75)):
                scene_frame(spec, sc, lt, sc["start"] + lt, total).save(f"/tmp/preview_{item['id']}_{i}{k}.jpg", quality=85)
        return
    scene_frame(spec, scenes[0], 0.0, 0.0, total).save(os.path.join(out_dir, "cover.jpg"), quality=92)
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, sc in enumerate(scenes):
            n = round((sc["end"] - sc["start"]) * FPS)
            part, tmpout = os.path.join(tmp, f"p{i}.mp4"), os.path.join(tmp, f"p{i}.tmp.mp4")
            p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                  "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                                  "-pix_fmt", "yuv420p", "-r", str(FPS), tmpout], stdin=subprocess.PIPE)
            for fr in range(n):
                lt = fr / FPS
                p.stdin.write(scene_frame(spec, sc, lt, sc["start"] + lt, total).tobytes())
            p.stdin.close()
            if p.wait() != 0:
                raise SystemExit(f"ffmpeg failed on {item['id']} scene {i}")
            os.replace(tmpout, part)
            parts.append(part)
        lst = os.path.join(tmp, "list.txt")
        open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
        out = os.path.join(out_dir, "reel.tmp.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                        "-movflags", "+faststart", out], check=True)
        os.replace(out, os.path.join(out_dir, "reel.mp4"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append")
    ap.add_argument("--frames", action="append", help="preview PNGs for this id")
    a = ap.parse_args()
    queue = json.load(open(os.path.join(ROOT, "queue.json"), encoding="utf-8"))
    by = {i["id"]: i for i in queue}
    specs = json.load(open(os.path.join(ROOT, "reels_v3", "specs.json"), encoding="utf-8"))
    for rid, spec in specs.items():
        if a.frames and rid not in a.frames: continue
        if a.only and rid not in a.only: continue
        item = by[rid]
        assert len(spec["scenes"]) == len(item["voice_scenes"]), rid
        render(item, spec, os.path.join(ROOT, "media", rid), preview=bool(a.frames))
        print("built" if not a.frames else "previewed", rid)


if __name__ == "__main__":
    main()
