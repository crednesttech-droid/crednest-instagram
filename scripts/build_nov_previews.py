#!/usr/bin/env python3
"""Build a reviewer gallery; never changes publishable media or queue entries."""
from pathlib import Path
import json
from PIL import Image, ImageCms, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PAPER, INK, FOREST = "#F8F8F4", "#07150F", "#315746"


def main():
    items = json.loads((ROOT / "batch_nov16_29/batch.json").read_text(encoding="utf-8"))["items"]
    items = [item for item in items if item["type"] != "reserved"]
    width, gap, tile_w, tile_h, title_h = 1200, 24, 270, 540, 86
    canvas = Image.new("RGB", (width, title_h + 3 * tile_h + gap), "#E6EBE3")
    draw = ImageDraw.Draw(canvas)
    fonts = ROOT / "brand/03_Fonts"
    heading = ImageFont.truetype(str(fonts / "Manrope-Extrabold.ttf"), 31)
    label = ImageFont.truetype(str(fonts / "Manrope-Bold.ttf"), 20)
    draw.text((gap, 20), "Nov 16–29 · @crednest.io · 12 covers", fill=INK, font=heading)
    for index, item in enumerate(items):
        x = gap + (index % 4) * (tile_w + gap)
        y = title_h + (index // 4) * tile_h
        filename = "cover.jpg" if item["type"] == "reel" else "01.jpg"
        path = ROOT / "media" / item["id"] / filename
        with Image.open(path) as image:
            thumb = ImageOps.contain(image.convert("RGB"), (tile_w, 480), Image.Resampling.LANCZOS)
        draw.rectangle((x, y, x + tile_w, y + 480), fill=PAPER)
        canvas.paste(thumb, (x + (tile_w - thumb.width) // 2, y + (480 - thumb.height) // 2))
        date = item["publish_at"][8:10] + " Nov"
        draw.text((x, y + 490), f"{item['id']} · {date} · {item['type']}", fill=INK, font=label)
    output = ROOT / "reports/nov16-29/covers.jpg"
    output.parent.mkdir(parents=True, exist_ok=True)
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    canvas.save(output, "JPEG", quality=94, subsampling=0, icc_profile=profile)
    print(output.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
