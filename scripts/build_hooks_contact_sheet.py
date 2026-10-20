"""Create the 13-pair Claude/v2 review sheet from the applied patch commit."""
import argparse
from io import BytesIO
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont
from render_hooks import SPECS

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_REF = "42a5f7c927c529ee32d1c1616a27521290bc62b3"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-ref", default=CLAUDE_REF)
    args = parser.parse_args()
    thumb_w, thumb_h, gap, label_h = 360, 450, 24, 54
    rows = (len(SPECS) + 1) // 2
    width = gap + 4 * (thumb_w + gap)
    sheet = Image.new("RGB", (width, 100 + rows * (thumb_h + label_h + gap)), "#E9ECE7")
    draw = ImageDraw.Draw(sheet)
    fonts = ROOT / "brand/03_Fonts"
    label = ImageFont.truetype(str(fonts / "Manrope-Bold.ttf"), 24)
    title = ImageFont.truetype(str(fonts / "Manrope-Extrabold.ttf"), 34)
    draw.text((gap, 22), "22 OCT – 12 NOV 2026  /  CLAUDE → PRODUCTION V2", font=title, fill="#07150F")
    for i, spec in enumerate(SPECS):
        row, pair = divmod(i, 2)
        path = f"media/{spec['id']}/01.jpg"
        before = Image.open(BytesIO(subprocess.check_output(["git", "show", f"{args.before_ref}:{path}"], cwd=ROOT)))
        after = Image.open(ROOT / path)
        for j, (caption, image) in enumerate((("CLAUDE", before), ("V2", after))):
            x = gap + (pair * 2 + j) * (thumb_w + gap)
            y = 100 + row * (thumb_h + label_h + gap)
            draw.text((x, y), f"{spec['id']} · {caption}", font=label, fill="#07150F")
            sheet.paste(image.convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS), (x, y + label_h))
    out = ROOT / "reports/hooks-refresh-v2/before-after.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, "JPEG", quality=92, optimize=True)
    print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
