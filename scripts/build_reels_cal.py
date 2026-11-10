#!/usr/bin/env python3
"""Capital Desk style reels for the Dec 2026 - Jan 2027 calendar (silent; revoice.yml adds the Sarvam voice).

Each scene: licensed Pexels b-roll under a 70% deep-green wash, CredNest header, CAPITAL DESK pill,
lime kicker, big title and the narration line. The final scene is a lime WhatsApp end card.
Stock files (reels_v2/stock_sources.json) must sit in <work-dir>/stock.
    python scripts/build_reels_cal.py --work-dir /tmp/cn [--only ID ...]
"""
import argparse, json, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageCms

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plans"))
import content_dec_jan as C

WD, HT, FPS = 1080, 1920, 30
INK, DEEP, PAPER, LIME, MINT = "#07150F", "#0D2119", "#F8F8F4", "#B8FF5A", "#9DF3C5"
FD = ROOT / "brand/03_Fonts"


def F(size, w="Extrabold"):
    return ImageFont.truetype(str(FD / f"Manrope-{w}.ttf"), size)


def wrap(d, text, face, width):
    lines, cur = [], ""
    for word in text.split():
        cand = (cur + " " + word).strip()
        if cur and d.textlength(cand, font=face) > width:
            lines.append(cur); cur = word
        else:
            cur = cand
    return lines + [cur]


def timings(scenes):
    out, t = [], 0.0
    for n, (_, _, line, _) in enumerate(scenes):
        dur = max(2.6, round(0.36 * len(line.split()) + 1.2, 1)) + (0.8 if n == len(scenes) - 1 else 0)
        out.append((round(t, 2), round(t + dur, 2)))
        t += dur
    return out


def overlay(it, n, scenes, total):
    kicker, title, line, _ = scenes[n]
    end = n == len(scenes) - 1
    im = Image.new("RGBA", (WD, HT), LIME if end else (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fg = INK if end else PAPER
    acc = INK if end else LIME
    t1 = timings(scenes)[n][1]
    d.rectangle((0, 0, WD, 8), fill=(7, 21, 15, 120) if end else (248, 248, 244, 50))
    d.rectangle((0, 0, round(WD * t1 / total), 8), fill=INK if end else LIME)
    logo = Image.open(ROOT / "brand/04_Logos/CredNest_Icon_Source_Transparent_120.png").convert("RGBA").resize((84, 84), Image.Resampling.LANCZOS)
    im.alpha_composite(logo, (88, 262))
    d.text((190, 304), "CredNest", font=F(46, "Bold"), fill=fg, anchor="lm")
    pill = F(24, "Bold")
    ptxt = it.get("pill", "CAPITAL DESK")
    pw = d.textlength(ptxt, font=pill) + 40
    d.rounded_rectangle((992 - pw, 282, 992, 326), radius=22, outline=acc, width=3)
    d.text((992 - pw / 2, 304), ptxt, font=pill, fill=fg, anchor="mm")
    d.text((88, 430), kicker.upper(), font=F(34, "Bold"), fill=acc)
    if end:
        y = 520
        for ln in wrap(d, line, F(104), 900):
            d.text((88, y), ln, font=F(104), fill=INK); y += 122
        d.rounded_rectangle((88, max(y + 90, 1050), 992, max(y + 90, 1050) + 160), radius=26, fill=INK)
        by = max(y + 90, 1050)
        d.text((128, by + 28), "WhatsApp “Hi”", font=F(36, "Bold"), fill=LIME)
        d.text((128, by + 76), "+91 98199 99057", font=F(56), fill=PAPER)
        d.text((88, by + 210), "Follow @crednest.io", font=F(40, "Bold"), fill=INK)
    else:
        size = 132
        while True:
            tl = wrap(d, title, F(size), 904)
            if len(tl) <= 2 or size <= 96:
                break
            size -= 6
        y = 500
        for ln in tl:
            d.text((88, y), ln, font=F(size), fill=LIME); y += int(size * 1.12)
        y += 50
        for ln in wrap(d, line, F(60, "Bold"), 904):
            d.text((88, y), ln, font=F(60, "Bold"), fill=PAPER); y += 76
        assert y < 1540, (it["id"], n, y)
    d.text((88, 1580), "crednest.io  ·  No advance fees", font=F(32, "Bold"), fill=fg)
    d.text((88, 1626), "Financing subject to independent lender assessment and approval.", font=F(24, "Medium"), fill=fg)
    return im


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def build(it, reg, work):
    scenes, times = it["scenes"], timings(it["scenes"])
    total = times[-1][1]
    out_dir = work / "renders" / it["id"]; out_dir.mkdir(parents=True, exist_ok=True)
    segs = []
    for n, ((s, e), sc) in enumerate(zip(times, scenes)):
        png = out_dir / f"ov{n}.png"; overlay(it, n, scenes, total).save(png)
        seg = out_dir / f"seg{n}.mp4"; dur = e - s
        if n == len(scenes) - 1:
            run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "30", "-i", str(png), "-t", f"{dur:.3f}",
                 "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-r", "30", str(seg)])
        else:
            a = reg[sc[3]]
            avail = max(0.0, a["duration_seconds"] - dur - 0.1)
            off = (n * 1.7 + len(it["id"]) * 0.37) % max(avail, 0.1)
            vf = ("[0:v]crop=trunc(ih*9/16/2)*2:ih:(iw-ow)/2:0,scale=1080:1920:flags=lanczos,fps=30,setsar=1,"
                  "gblur=sigma=0.8,drawbox=x=0:y=0:w=iw:h=ih:color=0x0D2119@0.70:t=fill[b];[b][1:v]overlay=0:0,format=yuv420p")
            src = work / "stock" / a["filename"]
            loop = ["-stream_loop", "-1"] if a["duration_seconds"] < dur + 0.2 else []
            run(["ffmpeg", "-y", "-v", "error", *loop, "-ss", f"{off:.2f}", "-i", str(src), "-loop", "1", "-i", str(png),
                 "-filter_complex", vf, "-t", f"{dur:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-r", "30", str(seg)])
        segs.append(seg)
    lst = out_dir / "list.txt"; lst.write_text("".join(f"file '{p}'\n" for p in segs))
    dest = ROOT / "media" / it["id"]; dest.mkdir(parents=True, exist_ok=True)
    mp4 = dest / "reel.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-an", "-c:v", "libx264", "-preset", "medium",
         "-crf", "18", "-maxrate", "6000k", "-bufsize", "12000k", "-pix_fmt", "yuv420p", "-r", "30", "-t", f"{total:.3f}",
         "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", str(mp4)])
    assert mp4.stat().st_size < 8_000_000
    frame = out_dir / "cover.png"
    run(["ffmpeg", "-y", "-v", "error", "-ss", "1.5", "-i", str(mp4), "-frames:v", "1", str(frame)])
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    Image.open(frame).convert("RGB").save(dest / "cover.jpg", "JPEG", quality=95, subsampling=0, icc_profile=srgb)
    vs = [{"start": s, "end": e, "text": sc[2]} for (s, e), sc in zip(times, scenes)]
    print(it["id"], f"{total:.1f}s", f"{mp4.stat().st_size/1e6:.1f} MB", flush=True)
    return vs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    reg = {x["name"]: x for x in json.loads((ROOT / "reels_v2/stock_sources.json").read_text())["assets"]}
    res = {}
    for it in C.ITEMS + getattr(C, "FESTIVALS", []):
        if it["type"] == "reel" and it.get("scenes") and (not a.only or it["id"] in a.only):
            res[it["id"]] = build(it, reg, a.work_dir.resolve())
    (a.work_dir / "voice_scenes.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
