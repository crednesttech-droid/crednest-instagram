"""Rebuild the 13 hook visuals with the supplied copy and original brand assets.

python scripts/render_hooks.py                  # 13 covers / single images
python scripts/render_hooks.py D09-feed          # one item
python scripts/render_hooks.py --all-slides      # include matching carousel interiors

Does not change captions, scheduling, status or publication state.
"""
import sys
from render_hooks_layout import render, render_interiors

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
    interiors = "--all-slides" in sys.argv
    only = set(sys.argv[1:]) - {"--all-slides"}
    unknown = only - {s["id"] for s in SPECS}
    if unknown:
        raise SystemExit(f"Unknown item(s): {sorted(unknown)}")
    for spec in SPECS:
        if not only or spec["id"] in only:
            print("rendered", render(spec))
            if interiors and spec["layout"] == "cover":
                for path in render_interiors(spec):
                    print("rendered", path)
