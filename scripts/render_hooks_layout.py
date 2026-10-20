"""Deterministic Manrope typesetting and original geometric topic illustrations.

All coordinates are in final-image pixels; drawing uses 2x supersampling.
The queue topic is the source of truth for every cover/card headline.
"""
import json
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageCms

ROOT = Path(__file__).resolve().parents[1]
W, H, S, M = 1080, 1350, 2, 88
INK, DEEP, FOREST = "#07150F", "#0D2119", "#315746"
PAPER, LIME, MINT = "#F8F8F4", "#B8FF5A", "#9DF3C5"
CONTACT = "crednest.io · WhatsApp +91 98199 99057"
DISCLAIMER = ("CredNest is a debt-capital facilitator, not a lender or NBFC. "
              "Loan approval and terms are at the lender's sole discretion.")
CASE_TAG = "Illustrative scenario, not a client case or testimonial."
THEMES = {
    "dark": (DEEP, PAPER, LIME, "#DCE6E0", "#315746", "#17372A"),
    "forest": (FOREST, PAPER, LIME, PAPER, "#6F9582", "#244737"),
    "paper": (PAPER, INK, FOREST, FOREST, "#CAD3CA", "#E5EBDD"),
    "lime": (LIME, INK, INK, "#1E3A2C", "#81B83B", "#A5E64E"),
}


@lru_cache(maxsize=None)
def font(size, weight="Extrabold"):
    return ImageFont.truetype(str(ROOT / "brand/03_Fonts" / f"Manrope-{weight}.ttf"), round(size * S))


class Canvas:
    def __init__(self, theme):
        self.bg, self.fg, self.accent, self.sub, self.rule, self.panel = THEMES[theme]
        self.im = Image.new("RGB", (W * S, H * S), self.bg)
        self.d = ImageDraw.Draw(self.im)

    def text(self, xy, text, size, fill=None, weight="Extrabold"):
        self.d.text(tuple(round(v * S) for v in xy), text, font=font(size, weight), fill=fill or self.fg, anchor="lt")

    def width(self, text, size, weight="Extrabold"):
        return self.d.textlength(text, font=font(size, weight)) / S

    def line(self, xy, fill=None, width=2):
        self.d.line([round(v * S) for v in xy], fill=fill or self.rule, width=round(width * S), joint="curve")

    def rect(self, box, fill=None, outline=None, width=2, radius=0):
        box = [round(v * S) for v in box]
        if radius:
            self.d.rounded_rectangle(box, radius=round(radius * S), fill=fill, outline=outline, width=round(width * S))
        else:
            self.d.rectangle(box, fill=fill, outline=outline, width=round(width * S))

    def circle(self, box, fill=None, outline=None, width=2):
        self.d.ellipse([round(v * S) for v in box], fill=fill, outline=outline, width=round(width * S))

    def wrap(self, text, size, width, weight="Medium"):
        result = []
        for para in text.split("\n"):
            line = ""
            for word in para.split():
                candidate = (line + " " + word).strip()
                if line and self.width(candidate, size, weight) > width:
                    result.append(line)
                    line = word
                else:
                    line = candidate
            result.append(line)
        assert all(self.width(line, size, weight) <= width for line in result), text
        return result

    def lines(self, xy, lines, size, leading, fill=None, weight="Medium"):
        x, y = xy
        for line in lines:
            self.text((x, y), line, size, fill, weight)
            y += leading
        return y

    def save(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        self.im.resize((W, H), Image.Resampling.LANCZOS).save(path, "JPEG", quality=95, optimize=True, subsampling=0, icc_profile=srgb)
        assert path.stat().st_size < 8 * 1024 * 1024
        return path.relative_to(ROOT).as_posix()


def header(c, kicker, index=None):
    # Use the supplied mark, unchanged and proportionally scaled.
    logo = Image.open(ROOT / "brand/04_Logos/CredNest_Icon_Source_Transparent_120.png").convert("RGBA")
    logo = logo.resize((72 * S, 72 * S), Image.Resampling.LANCZOS)
    c.im.paste(logo, (M * S, 72 * S), logo)
    c.text((182, 89), "CredNest", 42, weight="Bold")
    c.line((M, 176, W - M, 176))
    c.text((M, 211), kicker.upper(), 25, c.accent, "Bold")
    if index:
        c.text((900, 102), index, 25, c.sub, "Bold")


def footer(c):
    # All footer ink stays above y=1230, leaving the bottom 120px clear.
    c.line((M, 1096, W - M, 1096))
    c.text((M, 1113), CONTACT, 30, weight="Bold")
    lines = c.wrap(DISCLAIMER, 32, W - 2 * M, "Medium")
    assert len(lines) <= 2
    end = c.lines((M, 1158), lines, 32, 35, c.fg, "Medium")
    assert end <= 1228  # final line ink ends above y=1230


def document(c, x, y, w, h, label=None, color=None, fill=None):
    color = color or c.accent
    c.rect((x, y, x + w, y + h), fill=fill or c.panel, outline=color, width=3, radius=10)
    c.line((x + 18, y + 22, x + w - 18, y + 22), color, 5)
    if label:
        c.text((x + 18, y + 44), label, min(36, w * .21), color, "Bold")
    for dy, frac in ((.60, .72), (.74, .55), (.87, .66)):
        c.line((x + 18, y + h * dy, x + w * frac, y + h * dy), color, 3)


def house(c, x, y, w, h, color=None):
    color = color or c.accent
    c.line((x, y + h * .40, x + w * .5, y, x + w, y + h * .40), color, 5)
    c.line((x + w * .12, y + h * .35, x + w * .12, y + h, x + w * .88, y + h, x + w * .88, y + h * .35), color, 5)
    c.rect((x + w * .40, y + h * .62, x + w * .60, y + h), outline=color, width=4)
    c.rect((x + w * .21, y + h * .48, x + w * .32, y + h * .63), outline=color, width=3)
    c.rect((x + w * .68, y + h * .48, x + w * .79, y + h * .63), outline=color, width=3)


def anchor(c, item_id, box):
    """Topic diagrams, with no people, lender identity or approval iconography."""
    x, y, w, h = box
    c.rect((x, y, x + w, y + h), fill=c.panel, radius=18)
    if item_id == "D09-feed":
        document(c, x + 45, y + 26, 133, h - 52, "BG")
        c.text((x + 223, y + 38), "LC / BG", 66, c.accent)
        for n in range(3):
            xx = x + 225 + n * 195
            c.text((xx, y + 126), f"0{n + 1}", 36, c.fg, "Bold")
            c.line((xx, y + 183, xx + 148, y + 183), c.accent, 4)
    elif item_id == "D10-feed":
        for n in range(3):
            document(c, x + 92 + n * 240, y + 40 - n * 8, 190, h - 70, f"0{n + 1}")
    elif item_id == "D16-feed":
        document(c, x + 100, y + 26, 250, h - 52, "CMA")
        c.text((x + 415, y + 82), "/", 68, c.accent)
        document(c, x + 545, y + 26, 250, h - 52, "DPR")
    elif item_id == "D20-feed":
        house(c, x + 88, y + 35, 220, h - 65)
        c.line((x + 448, y + 35, x + 448, y + h - 35), c.accent, 2)
        document(c, x + 590, y + 28, 220, h - 56, "₹")
    elif item_id == "D21-feed":
        document(c, x + 100, y + 26, 250, h - 52, "BANK")
        # Unequal line lengths evoke a reconciliation, without a fictitious figure.
        c.line((x + 410, y + 82, x + 494, y + 82), c.accent, 4)
        c.line((x + 410, y + 117, x + 466, y + 117), c.accent, 4)
        c.line((x + 410, y + 152, x + 494, y + 152), c.accent, 4)
        document(c, x + 545, y + 26, 250, h - 52, "ITR")


def mini(c, item_id):
    """A compact topic anchor in the header, clear of all copy."""
    x, y = 838, 45
    if item_id == "D23-new":
        c.rect((x, y, 992, 161), fill=c.panel, radius=10)
        c.text((x + 20, y + 10), "60", 66, c.accent)
        c.text((x + 23, y + 82), "DAYS", 19, c.fg, "Bold")
    elif item_id in {"D18-feed", "D19-new", "D25-new", "D27-feed"}:
        house(c, x + 10, y + 9, 130, 102)
    elif item_id == "D30-new":
        c.rect((x, y + 5, 986, y + 100), fill=c.panel, outline=c.accent, width=3, radius=14)
        c.line((x + 20, y + 100, x + 20, y + 116, x + 43, y + 100), c.accent, 3)
        for n in range(3):
            c.circle((x + 27 + n * 38, y + 42, x + 36 + n * 38, y + 51), fill=c.accent)
    else:
        document(c, x + 12, y, 128, 114, "₹")


def headline(c, text, y=270, start=104):
    for size in range(start, 89, -2):
        lines = c.wrap(text, size, W - 2 * M, "Extrabold")
        if len(lines) <= 4:
            assert " ".join(lines) == " ".join(text.split())
            return c.lines((M, y), lines, size, int(size * 1.04), c.fg, "Extrabold"), size, lines
    raise ValueError(f"Headline cannot fit at >=90px and <=4 lines: {text}")


def render(spec):
    queue = {item["id"]: item for item in json.loads((ROOT / "queue.json").read_text(encoding="utf-8"))}
    item = queue[spec["id"]]
    assert spec["headline"] == item["topic"], f"Spec / topic mismatch: {item['id']}"
    c = Canvas(spec["theme"])
    header(c, spec["kicker"], "01 / 05" if spec["layout"] == "cover" else None)
    end, size, lines = headline(c, item["topic"], start=104 if spec["layout"] == "cover" else 96)
    sub_lines = c.wrap(spec["sub"], 33, W - 2 * M, "Medium")
    sub_end = c.lines((M, end + 22), sub_lines, 33, 42, c.sub)
    assert len(sub_lines) <= 2 and sub_end <= 826
    if spec["layout"] == "cover":
        # Anchor fills the space after the hook; never sits behind the text.
        ay = max(735, sub_end + 30)
        ah = 1000 - ay
        assert ah >= 170
        anchor(c, spec["id"], (M, ay, W - 2 * M, ah))
        c.text((M, 1042), "Swipe →", 30, c.accent, "Bold")
        if spec.get("case_tag"):
            c.text((305, 1046), CASE_TAG, 22, c.fg, "Medium")
    else:
        mini(c, spec["id"])
        # Expand the list into the available middle area on shorter hooks.
        # Long four-line hooks retain the compact grid without reducing type.
        y = max(620, sub_end + 28)
        step = (968 - y) / 3
        assert step >= 54
        point_size = 36 if step >= 75 else 33
        number_size = 42 if step >= 75 else 29
        for n, point in enumerate(spec["points"], 1):
            c.line((M, y - 14, W - M, y - 14))
            c.text((M, y), f"0{n}", number_size, c.accent, "Bold")
            assert c.width(point, point_size, "Semibold") <= W - M - 180
            c.text((180, y + 3), point, point_size, c.fg, "Semibold")
            y += step
        if spec.get("case_tag"):
            c.text((M, 972), CASE_TAG, 22, c.fg, "Medium")
        cta_bg, cta_fg = (INK, PAPER) if spec["theme"] in {"paper", "lime"} else (LIME, INK)
        c.rect((M, 1010, W - M, 1072), fill=cta_bg, radius=10)
        assert c.width(spec["bar"], 31, "Bold") < W - 2 * M - 48
        c.text((M + 24, 1027), spec["bar"], 31, cta_fg, "Bold")
    footer(c)
    return c.save(ROOT / item["media"][0])


# Content transcribed from the existing slides, preserving educational meaning.
# Scenario labels move out of the headline into the small, explicit tag.
INTERIORS = {
    "D09-feed": [
        ("A supply contract. An obligation first.", ["The business has a contractual performance obligation.", "This is not a client case or testimonial."]),
        ("Start with the underlying documents.", ["Contract, parties and payment terms.", "The exact obligation the instrument supports."]),
        ("Match the instrument to the requirement.", ["LC and BG discussions serve different commercial purposes.", "The structure and documents depend on lender assessment."]),
        ("Save this with your contract checklist.", []),
    ],
    "D10-feed": [
        ("Property and identity.", ["Ownership and title information.", "KYC and records relevant to the property."]),
        ("Income and existing commitments.", ["Income or business financial information.", "Banking and existing repayment obligations."]),
        ("Use of funds and repayment.", ["Explain what the borrowing will support.", "Ask which case-specific documents the lender requires."]),
        ("Save the LAP document checklist.", []),
    ],
    "D16-feed": [
        ("Build the project explanation.", ["Purpose, implementation milestones and costs.", "Sources of funds and repayment assumptions."]),
        ("CMA and DPR answer different questions.", ["CMA information supports financial projections.", "A DPR explains the project, implementation and assumptions."]),
        ("Make the records consistent.", ["Connect estimates to supporting evidence.", "Ask what your project and lender require."]),
        ("Save the project-finance preparation checklist.", []),
    ],
    "D20-feed": [
        ("Property is not the whole assessment.", ["Income and repayment capacity still matter.", "Existing obligations need a clear explanation."]),
        ("Security has its own checks.", ["Ownership, title and valuation.", "Documents depend on the property and the lender."]),
        ("Prepare both parts of the file.", ["Explain the use of funds and cash-flow context.", "The lender decides the overall case."]),
        ("Save this before a LAP discussion.", []),
    ],
    "D21-feed": [
        ("One manufacturer. Different records.", ["Banking, financial records and projections tell different stories.", "This is not a client case or testimonial."]),
        ("Identify the gaps.", ["Check operating assumptions against supporting records.", "Explain differences in a consistent credit brief."]),
        ("Preparation is the outcome.", ["Organise the information before lender engagement.", "No financing result is claimed."]),
        ("Share this with the team preparing your credit file.", []),
    ],
}


def render_interiors(spec):
    paths = []
    for n, (title, points) in enumerate(INTERIORS[spec["id"]], 2):
        c = Canvas("lime" if n == 5 else "paper")
        header(c, spec["kicker"], f"0{n} / 05")
        end, _, _ = headline(c, title, start=96)
        if points:
            y = max(650, end + 65)
            for k, point in enumerate(points, 1):
                c.line((M, y - 25, W - M, y - 25))
                c.text((M, y), f"0{k}", 30, c.accent, "Bold")
                rows = c.wrap(point, 36, W - M - 158, "Medium")
                y = c.lines((158, y), rows, 36, 47, c.fg)
                y += 55
            assert y < 1030
            if spec.get("case_tag"):
                c.text((M, 1046), CASE_TAG, 22, c.fg, "Medium")
        else:
            anchor(c, spec["id"], (M, max(735, end + 40), W - 2 * M, 235))
            if spec.get("case_tag"):
                c.text((M, 1046), CASE_TAG, 22, c.fg, "Medium")
        footer(c)
        paths.append(c.save(ROOT / "media" / spec["id"] / f"{n:02}.jpg"))
    return paths
