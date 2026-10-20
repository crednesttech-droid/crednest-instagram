"""Render hook-first cover slides and single-image cards in the CredNest layout.

Usage: python scripts/render_hooks.py            # renders every spec in SPECS
       python scripts/render_hooks.py D20-feed   # renders one

Writes media/<id>/01.jpg (1080 x 1350, JPEG). Other carousel slides are untouched.
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "brand/03_Fonts"
LOGO = ROOT / "brand/04_Logos/CredNest_Icon_Source_Transparent_120.png"
W, H, M = 1080, 1350, 88

LIME, INK, DEEP, FOREST, PAPER, MINT = "#B8FF5A", "#07150F", "#0D2119", "#315746", "#F8F8F4", "#9DF3C5"
THEMES = {
    "dark":   dict(bg=DEEP,  head=PAPER, kicker=LIME,   sub="#C9D4CE", body=PAPER, rule="#24402F", ring=FOREST, bar=LIME, bar_text=INK, foot="#9FB2A8"),
    "forest": dict(bg=FOREST, head=PAPER, kicker=LIME,  sub="#DCE6E0", body=PAPER, rule="#4B7361", ring="#5C8572", bar=LIME, bar_text=INK, foot="#C9D8D0"),
    "paper":  dict(bg=PAPER, head=INK,   kicker=FOREST, sub=FOREST,    body=INK,   rule="#E1E4DD", ring=FOREST, bar=INK, bar_text=PAPER, foot=FOREST),
    "lime":   dict(bg=LIME,  head=INK,   kicker=INK,    sub="#1E3A2C", body=INK,   rule="#9ED24A", ring="#8FCC3F", bar=INK, bar_text=LIME, foot="#1E3A2C"),
}
DISCLAIMER = "CredNest is a debt-capital facilitator, not a lender or NBFC.\nLoan approval and terms are at the lender's sole discretion."


def f(size, weight="Extrabold"):
    return ImageFont.truetype(str(FONTS / f"Manrope-{weight}.ttf"), size)


def wrap(draw, text, face, width):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split():
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=face) <= width or not cur:
                cur = t
            else:
                lines.append(cur); cur = w
        lines.append(cur)
    return lines


def fit_headline(draw, text, width, max_lines, start=104, floor=64):
    size = start
    while size >= floor:
        face = f(size)
        lines = wrap(draw, text, face, width)
        if len(lines) <= max_lines:
            return face, lines, size
        size -= 4
    return face, lines, size


def render(spec):
    th = THEMES[spec["theme"]]
    im = Image.new("RGB", (W, H), th["bg"])
    d = ImageDraw.Draw(im)

    # decorative rings (bottom right), drawn first so text sits on top
    cx, cy = (1080, 1060) if spec["layout"] == "cover" else (1050, 915)
    for r in ((300, 230, 160) if spec["layout"] == "cover" else (190, 135, 80)):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=th["ring"], width=10)
    if spec["layout"] == "card":  # keep rings to the right edge strip only
        d.rectangle([0, 760, 830, 1080], fill=th["bg"])

    logo = Image.open(LOGO).convert("RGBA").resize((72, 72), Image.LANCZOS)
    im.paste(logo, (M, 88), logo)
    d.text((M + 92, 124), "CredNest", font=f(44, "Bold"), fill=th["head"], anchor="lm")
    d.line([M, 196, W - M, 196], fill=th["rule"], width=2)

    d.text((M, 236), spec["kicker"].upper(), font=f(24, "Bold"), fill=th["kicker"])

    cover = spec["layout"] == "cover"
    y = 330 if cover else 300
    face, lines, size = fit_headline(d, spec["headline"], W - 2 * M, 4 if cover else 3,
                                     start=124 if cover else 100)
    lh = int(size * 1.08)
    for ln in lines:
        d.text((M, y), ln, font=face, fill=th["head"]); y += lh
    y += 34
    for ln in wrap(d, spec["sub"], f(34, "Medium"), W - 2 * M):
        d.text((M, y), ln, font=f(34, "Medium"), fill=th["sub"]); y += 46

    if spec["layout"] == "card":
        y = y + 44
        for n, item in enumerate(spec["points"], 1):
            d.text((M, y), f"0{n}", font=f(26, "Bold"), fill=th["kicker"])
            d.text((M + 60, y - 4), item, font=f(32, "Semibold"), fill=th["body"]); y += 66
        bar_y = 1110
    else:
        bar_y = 1110 if spec.get("bar") else None

    if spec.get("case_tag"):
        d.text((M, 1158 if cover else 1072), "Illustrative scenario, not a client case or testimonial.", font=f(22, "Medium"), fill=th["foot"])
    if not cover:
        assert y <= 1070, f"{spec['id']}: points overflow ({y})"
    if bar_y and spec.get("bar"):
        d.rounded_rectangle([M, bar_y, W - M, bar_y + 60], radius=12, fill=th["bar"])
        d.text((M + 32, bar_y + 30), spec["bar"], font=f(30, "Bold"), fill=th["bar_text"], anchor="lm")
    if spec.get("swipe"):
        d.text((M, 1108), "Swipe →", font=f(32, "Bold"), fill=th["kicker"])

    d.line([M, 1200, W - M, 1200], fill=th["rule"], width=2)
    d.text((M, 1222), "crednest.io  ·  WhatsApp +91 98199 99057", font=f(26, "Bold"), fill=th["head"])
    yy = 1266
    for ln in DISCLAIMER.split("\n"):
        d.text((M, yy), ln, font=f(20, "Medium"), fill=th["foot"]); yy += 26

    out = ROOT / "media" / spec["id"] / "01.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, "JPEG", quality=92, optimize=True)
    return out


SPECS = [
    # carousels: cover only, hook first
    dict(id="D09-feed", layout="cover", theme="dark", kicker="LC & BG", swipe=True, case_tag=True,
         headline="Contract won. Bank guarantee needed first?",
         sub="What to organise before the LC or BG discussion."),
    dict(id="D10-feed", layout="cover", theme="forest", kicker="Loan against property", swipe=True,
         headline="Loan against property? Keep these papers ready first.",
         sub="Ownership, income, banking and existing EMIs, in one file."),
    dict(id="D16-feed", layout="cover", theme="forest", kicker="Project finance", swipe=True,
         headline="New project. CMA or DPR: what does the lender need?",
         sub="Save this before the project-finance meeting."),
    dict(id="D20-feed", layout="cover", theme="paper", kicker="Myth vs fact", swipe=True,
         headline="Property de di. Loan pakka? Nahi.",
         sub="Security and repayment are assessed separately."),
    dict(id="D21-feed", layout="cover", theme="dark", kicker="Credit preparation", swipe=True, case_tag=True,
         headline="Bank statement says one thing. ITR says another?",
         sub="Make the numbers tell one story before the lender asks."),
    # single images: full card
    dict(id="D13-feed", layout="card", theme="paper", kicker="Personal loan",
         headline="New personal loan? Add up your EMIs first.",
         sub="A new repayment must fit next to the ones you already pay.",
         points=["Monthly take-home income", "Every existing EMI and card due", "Purpose of the new loan"],
         bar="WhatsApp \"Hi\" to +91 98199 99057"),
    dict(id="D18-feed", layout="card", theme="lime", kicker="Loan against property",
         headline="Property hai. Repayment plan hai?",
         sub="Owning property is not the same as repayment ability.",
         points=["Purpose of the funds", "Income and ITR records", "Existing EMIs and limits"],
         bar="WhatsApp \"Hi\" to +91 98199 99057"),
    dict(id="D19-new", layout="card", theme="dark", kicker="Existing debt",
         headline="Already paying a loan on your property?",
         sub="Review the current commitment before any top-up or transfer.",
         points=["Outstanding and tenure left", "Business cash flow today", "What the change should solve"],
         bar="Comment CHECKLIST for the free list"),
    dict(id="D22-new", layout="card", theme="paper", kicker="Business loans",
         headline="Next business loan? Put every EMI on one page.",
         sub="Lenders read your existing debt before your new request.",
         points=["Each facility and lender", "Outstanding and monthly outgo", "Use of the new funds"],
         bar="Comment CHECKLIST for the free list"),
    dict(id="D23-new", layout="card", theme="forest", kicker="Working capital",
         headline="CC renewal in 60 days? Start here.",
         sub="Renewal files move faster when these are ready early.",
         points=["Latest financials and GST returns", "12 months of banking", "Debtor and creditor ageing"],
         bar="Comment CHECKLIST for the free list"),
    dict(id="D25-new", layout="card", theme="dark", kicker="Loan against property",
         headline="Business ke liye LAP? Purpose pehle, property baad mein.",
         sub="The use of funds drives the structure, not the other way round.",
         points=["What the money will do", "How it gets repaid", "Property and title records"],
         bar="WhatsApp \"Hi\" to +91 98199 99057"),
    dict(id="D27-feed", layout="card", theme="paper", kicker="Loan against property", case_tag=True,
         headline="Property worth crores. Collections slow. Now what?",
         sub="Property value and repayment ability are different questions.",
         points=["Title and valuation", "Cash flow and collections", "Existing obligations"],
         bar="Comment CHECKLIST for the free list"),
    dict(id="D30-new", layout="card", theme="lime", kicker="Start a conversation",
         headline="Funding chahiye? Purpose aur timeline bhejo.",
         sub="One WhatsApp message. We come back with the next step.",
         points=["What the funds will support", "Amount range and timeline", "City and business type"],
         bar="WhatsApp \"Hi\" to +91 98199 99057"),
]

if __name__ == "__main__":
    only = set(sys.argv[1:])
    for s in SPECS:
        if not only or s["id"] in only:
            print("rendered", render(s).relative_to(ROOT))
